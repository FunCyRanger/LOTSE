#pragma once

#include "esp_err.h"

typedef void (*tasmota_result_cb_t)(bool success, const char *msg);

esp_err_t tasmota_push_script(const char *ip, int port,
                              const char *script,
                              tasmota_result_cb_t cb);
esp_err_t tasmota_send_command(const char *ip, int port,
                               const char *command,
                               tasmota_result_cb_t cb);
bool tasmota_discover(const char *ip, int port);
char *tasmota_fetch_sync(const char *ip, int port, const char *command);
bool tasmota_wait_online(const char *ip, int port, int timeout_ms);
