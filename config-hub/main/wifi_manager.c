#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include "lwip/ip4_addr.h"
#include "wifi_manager.h"

static const char *TAG = "wifi_mgr";

#define WIFI_CONNECTED_BIT  BIT0
#define WIFI_FAIL_BIT       BIT1
#define MAX_RETRIES         5

static EventGroupHandle_t s_wifi_event_group;
static wifi_state_t s_state = WIFI_STATE_INIT;
static char s_ip_str[16] = {0};
static wifi_callback_t s_callback = NULL;
static int s_retry_count = 0;
static bool s_ap_active = false;

static wifi_scan_result_t s_scan_results[MAX_SCAN_RESULTS];
static int s_scan_count = 0;

static void set_state(wifi_state_t state)
{
    s_state = state;
    if (s_callback) s_callback(state);
}

static void event_handler(void *arg, esp_event_base_t event_base,
                          int32_t event_id, void *event_data)
{
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_AP_START) {
        set_state(WIFI_STATE_AP);
    }
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    }
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        s_retry_count++;
        if (s_retry_count > MAX_RETRIES) {
            ESP_LOGE(TAG, "STA failed after %d retries, starting AP", MAX_RETRIES);
            set_state(WIFI_STATE_FAILED);
            if (!s_ap_active) {
                wifi_manager_start_ap();
            }
        } else {
            set_state(WIFI_STATE_CONNECTING);
            esp_wifi_connect();
        }
    }
    if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *event = (ip_event_got_ip_t *)event_data;
        esp_ip4addr_ntoa(&event->ip_info.ip, s_ip_str, sizeof(s_ip_str));
        s_retry_count = 0;
        set_state(WIFI_STATE_STATION);
        xEventGroupSetBits(s_wifi_event_group, WIFI_CONNECTED_BIT);
        if (s_ap_active) {
            wifi_manager_stop_ap();
        }
    }
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_SCAN_DONE) {
        uint16_t count = 0;
        esp_wifi_scan_get_ap_num(&count);
        ESP_LOGI(TAG, "Scan event received, count = %d", count);
        if (count > MAX_SCAN_RESULTS) count = MAX_SCAN_RESULTS;
        wifi_ap_record_t *records = malloc(count * sizeof(wifi_ap_record_t));
        if (!records) {
            ESP_LOGE(TAG, "Failed to allocate memory for scan records");
        } else {
            ESP_LOGI(TAG, "Allocating %d scan records", count);
            esp_wifi_scan_get_ap_records(&count, records);
            s_scan_count = 0;
            for (int i = 0; i < count && s_scan_count < MAX_SCAN_RESULTS; i++) {
                memset(&s_scan_results[s_scan_count], 0, sizeof(wifi_scan_result_t));
                memcpy(s_scan_results[s_scan_count].ssid, records[i].ssid, sizeof(records[i].ssid));
                s_scan_results[s_scan_count].rssi = records[i].rssi;
                s_scan_results[s_scan_count].authmode = records[i].authmode;
                if (s_scan_results[s_scan_count].ssid[0])
                    s_scan_count++;
            }
            ESP_LOGI(TAG, "Scan done: %d networks found", s_scan_count);
            free(records);
        }
    }
}

esp_err_t wifi_manager_init(void)
{
    s_wifi_event_group = xEventGroupCreate();
    s_ap_active = false;

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_ap();
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT,
        ESP_EVENT_ANY_ID, &event_handler, NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT,
        IP_EVENT_STA_GOT_IP, &event_handler, NULL, NULL));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_start());

    return ESP_OK;
}

esp_err_t wifi_manager_start(const char *ssid, const char *pass)
{
    if (!ssid || !ssid[0]) {
        ESP_LOGE(TAG, "Empty SSID");
        set_state(WIFI_STATE_AP);
        return ESP_ERR_INVALID_ARG;
    }

    wifi_config_t sta = {0};
    strncpy((char *)sta.sta.ssid, ssid, sizeof(sta.sta.ssid) - 1);
    strncpy((char *)sta.sta.password, pass, sizeof(sta.sta.password) - 1);
    sta.sta.scan_method = WIFI_ALL_CHANNEL_SCAN;
    sta.sta.sort_method = WIFI_CONNECT_AP_BY_SIGNAL;
    sta.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;
    sta.sta.pmf_cfg.capable = true;
    sta.sta.pmf_cfg.required = false;

    s_retry_count = 0;
    set_state(WIFI_STATE_CONNECTING);

    esp_err_t err = esp_wifi_set_config(WIFI_IF_STA, &sta);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to set STA config: %s", esp_err_to_name(err));
        wifi_manager_start_ap();
        return err;
    }

    err = esp_wifi_connect();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to connect: %s", esp_err_to_name(err));
        wifi_manager_start_ap();
        return err;
    }

    return ESP_OK;
}

esp_err_t wifi_manager_start_ap(void)
{
    esp_err_t err = esp_wifi_stop();
    if (err != ESP_OK) return err;

    esp_wifi_set_mode(WIFI_MODE_APSTA);

    wifi_config_t ap = {
        .ap = {
            .ssid_len = 0,
            .channel = 6,
            .max_connection = 4,
            .authmode = WIFI_AUTH_OPEN,
        },
    };
    uint8_t mac[6];
    esp_wifi_get_mac(WIFI_IF_AP, mac);
    snprintf((char *)ap.ap.ssid, sizeof(ap.ap.ssid),
             "LOTSE-%02X%02X%02X", mac[3], mac[4], mac[5]);
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &ap));
    ESP_ERROR_CHECK(esp_wifi_start());
    // Set AP config again after start (needed on some ESP-IDF versions)
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &ap));

    s_ap_active = true;
    ESP_LOGI(TAG, "AP started: %s", ap.ap.ssid);
    return ESP_OK;
}

esp_err_t wifi_manager_stop_ap(void)
{
    if (!s_ap_active) return ESP_OK;

    s_ap_active = false;
    s_retry_count = 0; // prevent momentary disconnect from counting as failure
    esp_err_t err = esp_wifi_stop();
    if (err != ESP_OK) return err;

    esp_wifi_set_mode(WIFI_MODE_STA);
    err = esp_wifi_start(); // triggers STA_START -> esp_wifi_connect()
    if (err == ESP_OK) {
        ESP_LOGI(TAG, "AP stopped, STA-only mode");
    }
    return err;
}

esp_err_t wifi_manager_scan_start(void)
{
    s_scan_count = 0;
    wifi_scan_config_t scan_config = {
        .ssid = NULL,
        .bssid = NULL,
        .channel = 0,
        .show_hidden = false,
    };
    return esp_wifi_scan_start(&scan_config, false);
}

int wifi_manager_scan_get_results(wifi_scan_result_t *results, int max)
{
    int count = s_scan_count < max ? s_scan_count : max;
    for (int i = 0; i < count; i++) {
        memcpy(&results[i], &s_scan_results[i], sizeof(wifi_scan_result_t));
    }
    return s_scan_count;
}

void wifi_manager_set_callback(wifi_callback_t cb)
{
    s_callback = cb;
}

wifi_state_t wifi_manager_get_state(void)
{
    return s_state;
}

const char *wifi_manager_get_ip(void)
{
    return s_state == WIFI_STATE_STATION ? s_ip_str : NULL;
}
