#pragma once
#include "esp_err.h"

esp_err_t ota_init(void);
esp_err_t ota_request_check(void);
const char *ota_get_current_version(void);
const char *ota_get_status(void);
