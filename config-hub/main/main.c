#include <string.h>
#include <stdlib.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "driver/gpio.h"
#include "nvs_flash.h"
#include "config_store.h"
#include "wifi_manager.h"
#include "mqtt_broker.h"
#include "web_server.h"
#include "transform.h"
#include "tasmota_client.h"
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
    // SENSOR path: build and publish sendtext envelope
    if (strstr(topic, "/SENSOR")) {
        if (!s_cfg.configured || !s_cfg.region[0]) { ESP_LOGD(TAG, "cb: not configured"); return; }
        int interval = s_cfg.send_interval;
        if (interval < 60) interval = 300;
        if (s_last_send_us > 0) {
            int64_t elapsed = esp_timer_get_time() - s_last_send_us;
            if (elapsed < (int64_t)interval * 1000000LL) { ESP_LOGD(TAG, "cb: rate-limited"); return; }
        }
        lotse_payload_t lp;
        int n = transform_apply_mapping(payload, &s_cfg, &lp);
        if (n <= 0) return;
        char topic_buf[128];
        if (s_cfg.node_hash[0])
            snprintf(topic_buf, sizeof(topic_buf), "msh/%s/2/json/mqtt/%s", s_cfg.region, s_cfg.node_hash);
        else
            snprintf(topic_buf, sizeof(topic_buf), "msh/%s/2/json/mqtt/", s_cfg.region);
        char *envelope = transform_build_envelope(&lp, s_cfg.node_decimal, 1);
        if (!envelope) return;
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

static void poll_tasmota_sensor_task(void *arg)
{
    hub_config_t *cfg = (hub_config_t *)arg;
    while (1) {
        int interval = cfg->send_interval;
        if (interval < 60) interval = 300;
        vTaskDelay(pdMS_TO_TICKS(interval * 1000));

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
        if (cfg->node_hash[0])
            snprintf(topic_buf, sizeof(topic_buf), "msh/%s/2/json/mqtt/%s", cfg->region, cfg->node_hash);
        else
            snprintf(topic_buf, sizeof(topic_buf), "msh/%s/2/json/mqtt/", cfg->region);

        char *envelope = transform_build_envelope(&lp, cfg->node_decimal, 1);
        if (!envelope) continue;

        ESP_LOGI(TAG, "poll: publishing %d values to %s", n, topic_buf);
        mqtt_broker_publish(topic_buf, envelope, 0);
        free(envelope);
    }
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
    if (s_cfg.send_interval < 60) s_cfg.send_interval = 300;

    wifi_manager_init();
    check_factory_reset();

    // Reload config after potential factory reset
    config_store_load(&s_cfg);
    if (s_cfg.gpio_rx <= 0) s_cfg.gpio_rx = 3;
    if (s_cfg.gpio_tx <= 0) s_cfg.gpio_tx = 1;
    if (s_cfg.send_interval < 60) s_cfg.send_interval = 300;

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

    ESP_LOGI(TAG, "LOTSE Config Hub initialized");
}
