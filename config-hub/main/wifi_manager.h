#pragma once

#include "esp_err.h"
#include "lotse_config.h"

#define MAX_SCAN_RESULTS 32

typedef struct {
    char ssid[33];
    int8_t rssi;
    uint8_t authmode; // 0=open, 1=WEP, 2=WPA_PSK, 3=WPA2_PSK, 4=WPA_WPA2_PSK, 5=WPA2_ENTERPRISE, 6=WPA3_PSK, 7=WPA2_WPA3_PSK
} wifi_scan_result_t;

typedef void (*wifi_callback_t)(wifi_state_t state);

esp_err_t wifi_manager_init(void);
esp_err_t wifi_manager_start(const char *ssid, const char *pass);
esp_err_t wifi_manager_start_ap(void);
esp_err_t wifi_manager_stop_ap(void);
void     wifi_manager_set_callback(wifi_callback_t cb);
wifi_state_t wifi_manager_get_state(void);
const char *wifi_manager_get_ip(void);
esp_err_t wifi_manager_scan_start(void);
int      wifi_manager_scan_get_results(wifi_scan_result_t *results, int max);
