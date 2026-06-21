#include <string.h>
#include <stdlib.h>
#include <time.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "esp_sntp.h"
#include "driver/gpio.h"
#include "nvs_flash.h"
#include "config_store.h"
#include "wifi_manager.h"
#include "mqtt_broker.h"
#include "web_server.h"
#include "transform.h"
#include "tasmota_client.h"
#include "ota.h"
#include "cJSON.h"

static const char *TAG = "lotse_main";
static hub_config_t s_cfg;
static int64_t s_last_send_us = 0;

static void on_mqtt_connect(const char *client_id)
{
    ESP_LOGI(TAG, "MQTT client connected: %s", client_id);
}

static void on_mqtt_publish(const char *topic, const char *payload, int payload_len)
{
    ESP_LOGD(TAG, "mqtt pub: topic=%s, len=%d", topic, payload_len);
    // SENSOR path: build and publish sendtext envelope
    if (strstr(topic, "/SENSOR") || strstr(topic, "/sensors")) {
        if (!s_cfg.configured || !s_cfg.region[0]) {
            ESP_LOGW(TAG, "cb: missing config (conf=%d, region='%s')", s_cfg.configured, s_cfg.region);
            return;
        }
        int interval = s_cfg.send_interval;
        if (interval < 60) interval = 60;
        if (s_last_send_us > 0) {
            int64_t elapsed = esp_timer_get_time() - s_last_send_us;
            uint32_t jitter = (uint64_t)interval * 1000000ULL / 10;
            if (jitter > 10000000ULL) jitter = 10000000ULL;
            jitter = esp_random() % (jitter + 1);
            if (elapsed < (int64_t)interval * 1000000LL + jitter) { ESP_LOGD(TAG, "cb: rate-limited"); return; }
        }
        lotse_payload_t lp;
        int n = transform_apply_mapping(payload, &s_cfg, &lp);
        if (n <= 0) return;
        char topic_buf[128];
        snprintf(topic_buf, sizeof(topic_buf), "msh/%s/2/json/mqtt/%s", s_cfg.region, s_cfg.node_hash);
        char *envelope = transform_build_envelope(&lp, s_cfg.node_decimal, 1);
        if (!envelope) return;
        ESP_LOGI(TAG, "publishing envelope to %s", topic_buf);
        mqtt_broker_publish(topic_buf, envelope, 0);
        free(envelope);
        s_last_send_us = esp_timer_get_time();
        return;
    }

    // Echo fix: republish with payload as parsed object for HA compatibility.
    // Heltec V3 echoes our sendtext message verbatim (payload stays a JSON string).
    // HA receiver expects payload as a parsed dict (value_json.payload.gEI).
    // We detect this, parse the inner JSON string, and republish with payload as object + type "text".
    if (strstr(topic, "/json/mqtt/") && s_cfg.node_hash[0] && strstr(topic, s_cfg.node_hash)) {
        cJSON *root = cJSON_Parse(payload);
        if (!root) return;

        cJSON *payload_field = cJSON_GetObjectItem(root, "payload");
        if (!payload_field || !cJSON_IsString(payload_field)) {
            cJSON_Delete(root);
            return;
        }

        const char *inner_str = payload_field->valuestring;
        cJSON *inner = cJSON_Parse(inner_str);
        if (!inner) {
            cJSON_Delete(root);
            return;
        }

        cJSON *from_item = cJSON_GetObjectItem(root, "from");
        cJSON *channel_item = cJSON_GetObjectItem(root, "channel");

        cJSON *fixed = cJSON_CreateObject();
        if (from_item) cJSON_AddNumberToObject(fixed, "from", from_item->valuedouble);
        cJSON_AddStringToObject(fixed, "type", "text");
        cJSON_AddItemToObject(fixed, "payload", inner);  // inner ownership transferred to fixed
        if (channel_item) cJSON_AddNumberToObject(fixed, "channel", channel_item->valuedouble);

        char *fixed_str = cJSON_PrintUnformatted(fixed);
        if (fixed_str) {
            ESP_LOGI(TAG, "echo fix: republished %s payload as object", topic);
            mqtt_broker_publish(topic, fixed_str, 0);
            free(fixed_str);
        }
        cJSON_Delete(fixed);  // also frees inner
        cJSON_Delete(root);
    }
}

static void check_factory_reset(void)
{
    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL << GPIO_NUM_0),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    gpio_config(&io_conf);

    // Small delay to let the button state settle
    vTaskDelay(pdMS_TO_TICKS(100));

    if (gpio_get_level(GPIO_NUM_0) == 0) {
        ESP_LOGW(TAG, "GPIO0 held low — performing factory reset!");
        config_store_reset();
        memset(&s_cfg, 0, sizeof(s_cfg));
        s_cfg.gpio_rx = 3;
        s_cfg.gpio_tx = 1;
        s_cfg.send_interval = 300;
        ESP_LOGI(TAG, "Factory reset done. Device will boot in AP mode.");
    }
}

static void publish_config_task(void *arg)
{
    hub_config_t *cfg = (hub_config_t *)arg;
    // Wait for system startup + SNTP sync
    vTaskDelay(pdMS_TO_TICKS(60 * 1000));

    char topic_buf[128];
    snprintf(topic_buf, sizeof(topic_buf), "msh/%s/2/json/mqtt/%s",
             cfg->region, cfg->node_hash);

    int hour_counter = 0;
    while (1) {
        // Publish on boot (first iteration) and then every 24h
        if (hour_counter == 0) {
            char *env = transform_build_config_envelope(cfg, cfg->node_decimal, 1);
            if (env) {
                ESP_LOGI(TAG, "config: publishing registration to %s", topic_buf);
                mqtt_broker_publish(topic_buf, env, 0);
                free(env);
            }
        }
        vTaskDelay(pdMS_TO_TICKS(3600 * 1000)); // 1 hour
        hour_counter = (hour_counter + 1) % 24;
    }
}

static void poll_tasmota_sensor_task(void *arg)
{
    hub_config_t *cfg = (hub_config_t *)arg;
    while (1) {
        // HTTP fallback poll runs at a fixed slow rate (600s = 10 min)
        // independent of send_interval. MQTT SENSOR is the primary data path.
        vTaskDelay(pdMS_TO_TICKS(600 * 1000));

        if (!cfg->configured || !cfg->tasmota_ip[0] || !cfg->region[0])
            continue;

        char *resp = tasmota_fetch_sync(cfg->tasmota_ip, cfg->tasmota_port, "Status%208");
        if (!resp) {
            ESP_LOGW(TAG, "poll: HTTP Status 8 failed");
            continue;
        }

        cJSON *root = cJSON_Parse(resp);
        free(resp);
        if (!root) continue;

        cJSON *sns = cJSON_GetObjectItem(root, "StatusSNS");
        if (!sns || !cJSON_IsObject(sns)) {
            cJSON_Delete(root);
            continue;
        }

        cJSON_DeleteItemFromObject(sns, "Time");

        char *inner = cJSON_PrintUnformatted(sns);
        cJSON_Delete(root);
        if (!inner) continue;

        lotse_payload_t lp;
        int n = transform_apply_mapping(inner, cfg, &lp);
        free(inner);
        if (n <= 0) continue;

        char topic_buf[128];
        snprintf(topic_buf, sizeof(topic_buf), "msh/%s/2/json/mqtt/%s", cfg->region, cfg->node_hash);

        char *envelope = transform_build_envelope(&lp, cfg->node_decimal, 1);
        if (!envelope) continue;

        ESP_LOGI(TAG, "poll: publishing %d values to %s", n, topic_buf);
        mqtt_broker_publish(topic_buf, envelope, 0);
        free(envelope);
    }
}

static void sntp_sync_task(void *arg)
{
    // Wait for WiFi station connection
    while (wifi_manager_get_state() != WIFI_STATE_STATION) {
        vTaskDelay(pdMS_TO_TICKS(1000));
    }

    ESP_LOGI(TAG, "starting SNTP time sync");
    sntp_setoperatingmode(SNTP_OPMODE_POLL);
    sntp_setservername(0, "pool.ntp.org");
    sntp_init();

    setenv("TZ", "CET-1CEST,M3.5.0,M10.5.0/3", 1);
    tzset();

    struct tm timeinfo = {0};
    int retry = 0;
    while (timeinfo.tm_year < (2024 - 1900) && retry < 30) {
        vTaskDelay(pdMS_TO_TICKS(2000));
        time_t now = time(NULL);
        localtime_r(&now, &timeinfo);
        retry++;
    }

    if (timeinfo.tm_year >= (2024 - 1900)) {
        ESP_LOGI(TAG, "SNTP synced: %04d-%02d-%02d %02d:%02d:%02d",
                 timeinfo.tm_year + 1900, timeinfo.tm_mon + 1,
                 timeinfo.tm_mday, timeinfo.tm_hour,
                 timeinfo.tm_min, timeinfo.tm_sec);
    } else {
        ESP_LOGW(TAG, "SNTP sync failed after %d retries", retry);
    }
    vTaskDelete(NULL);
}

void app_main(void)
{
    // Note: nvs_flash_init() is called inside config_store_init()
    config_store_init();
    memset(&s_cfg, 0, sizeof(s_cfg));
    s_cfg.gpio_rx = 3;
    s_cfg.gpio_tx = 1;
    s_cfg.send_interval = 300;
    config_store_load(&s_cfg);
    if (s_cfg.gpio_rx <= 0) s_cfg.gpio_rx = 3;
    if (s_cfg.gpio_tx <= 0) s_cfg.gpio_tx = 1;
    if (s_cfg.send_interval < 60) s_cfg.send_interval = 60;

    wifi_manager_init();
    check_factory_reset();

    // Reload config after potential factory reset
    config_store_load(&s_cfg);
    if (s_cfg.gpio_rx <= 0) s_cfg.gpio_rx = 3;
    if (s_cfg.gpio_tx <= 0) s_cfg.gpio_tx = 1;
    if (s_cfg.send_interval < 60) s_cfg.send_interval = 60;

    if (s_cfg.configured && s_cfg.wifi_ssid[0]) {
        wifi_manager_start(s_cfg.wifi_ssid, s_cfg.wifi_pass);
    } else {
        wifi_manager_start_ap();
    }

    mqtt_broker_start();
    mqtt_broker_set_publish_callback(on_mqtt_publish);
    mqtt_broker_set_connect_callback(on_mqtt_connect);

    web_server_start(&s_cfg);
    xTaskCreate(poll_tasmota_sensor_task, "poll_sensor", 8192, &s_cfg, 5, NULL);
    xTaskCreate(sntp_sync_task, "sntp_sync", 4096, NULL, 5, NULL);
    xTaskCreate(publish_config_task, "pub_config", 4096, &s_cfg, 3, NULL);
    ota_init();

    ESP_LOGI(TAG, "LOTSE Config Hub initialized");
}
