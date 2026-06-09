#pragma once

#include "lotse_config.h"

esp_err_t config_store_init(void);
esp_err_t config_store_load(hub_config_t *cfg);
esp_err_t config_store_save(const hub_config_t *cfg);
esp_err_t config_store_reset(void);
