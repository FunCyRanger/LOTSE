#pragma once

#include "lotse_config.h"

typedef struct {
    char lotse_key[LOTSE_KEY_LEN];
    double value;
} lotse_value_t;

typedef struct {
    lotse_value_t values[MAX_MAPPINGS];
    int count;
} lotse_payload_t;

int transform_parse_script(const char *script, var_mapping_t *mappings, int max);
int transform_apply_mapping(const char *tasmota_json, const hub_config_t *cfg,
                            lotse_payload_t *out);
char *transform_build_envelope(const lotse_payload_t *payload, uint32_t node_decimal,
                               int channel);

typedef struct {
    int gpio_rx;
    int gpio_tx;
} script_gpio_t;

void transform_parse_gpio(const char *script, script_gpio_t *gpio);
char *transform_inject_gpio(const char *script, int gpio_rx, int gpio_tx);
