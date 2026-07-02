#include <string.h>
#include <stdlib.h>
#include <stdint.h>
#include "unity.h"
#include "cJSON.h"
#include "transform.h"
#include "lotse_config.h"
#include "smi_scripts.h"

/* ── helpers ──────────────────────────────────────────── */

static hub_config_t cfg;
static var_mapping_t mappings[MAX_MAPPINGS];
static lotse_payload_t payload;

static void clear_cfg(void)
{
    memset(&cfg, 0, sizeof(cfg));
    memset(mappings, 0, sizeof(mappings));
    memset(&payload, 0, sizeof(payload));
    cfg.mapping_count = 0;
}

/* ── transform_parse_script tests ─────────────────────── */

void test_parse_real_hichi(void)
{
    int n = transform_parse_script(SMI_3_LINE, mappings, MAX_MAPPINGS);
    TEST_ASSERT_EQUAL_INT(3, n);
    TEST_ASSERT_EQUAL_STRING("E_total", mappings[0].var_name);
    TEST_ASSERT_EQUAL_STRING("Wh", mappings[0].unit);
    TEST_ASSERT_EQUAL_STRING("Power", mappings[1].var_name);
    TEST_ASSERT_EQUAL_STRING("W", mappings[1].unit);
    TEST_ASSERT_EQUAL_STRING("Voltage_L1", mappings[2].var_name);
    TEST_ASSERT_EQUAL_STRING("V", mappings[2].unit);
}

void test_parse_auto_mapping(void)
{
    int n = transform_parse_script(SMI_3_LINE, mappings, MAX_MAPPINGS);
    TEST_ASSERT_EQUAL_INT(3, n);
    TEST_ASSERT_EQUAL_STRING("gEI", mappings[0].lotse_key);
    TEST_ASSERT_EQUAL_STRING("gP", mappings[1].lotse_key);
    TEST_ASSERT_EQUAL_STRING("gV1", mappings[2].lotse_key);
}

void test_parse_suggests_bs_for_percent(void)
{
    int n = transform_parse_script(SMI_WITH_BATTERY, mappings, MAX_MAPPINGS);
    TEST_ASSERT(n >= 4);
    TEST_ASSERT_EQUAL_STRING("bS", mappings[3].lotse_key);
}

void test_parse_amperage_maps_to_ga(void)
{
    int n = transform_parse_script(SMI_18_LINE, mappings, MAX_MAPPINGS);
    int found_a = 0;
    for (int i = 0; i < n; i++) {
        if (strcmp(mappings[i].unit, "A") == 0 &&
            strncmp(mappings[i].lotse_key, "gA", 2) == 0) {
            found_a++;
        }
    }
    TEST_ASSERT_EQUAL_INT(3, found_a);
    // Verify specific slot assignments
    for (int i = 0; i < n; i++) {
        if (strcmp(mappings[i].var_name, "Strom_L1") == 0)
            TEST_ASSERT_EQUAL_STRING("gA1", mappings[i].lotse_key);
        else if (strcmp(mappings[i].var_name, "Strom_L2") == 0)
            TEST_ASSERT_EQUAL_STRING("gA2", mappings[i].lotse_key);
        else if (strcmp(mappings[i].var_name, "Strom_L3") == 0)
            TEST_ASSERT_EQUAL_STRING("gA3", mappings[i].lotse_key);
    }
}

void test_parse_long_script(void)
{
    int n = transform_parse_script(SMI_18_LINE, mappings, MAX_MAPPINGS);
    TEST_ASSERT_EQUAL_INT(18, n);
}

void test_parse_empty_script(void)
{
    int n = transform_parse_script(SMI_EMPTY, mappings, MAX_MAPPINGS);
    TEST_ASSERT_EQUAL_INT(0, n);
}

void test_parse_malformed(void)
{
    int n = transform_parse_script(SMI_MALFORMED, mappings, MAX_MAPPINGS);
    TEST_ASSERT_EQUAL_INT(0, n);
}

void test_parse_no_unit(void)
{
    int n = transform_parse_script(SMI_NO_UNIT, mappings, MAX_MAPPINGS);
    TEST_ASSERT_EQUAL_INT(1, n);
    TEST_ASSERT_EQUAL_STRING("CosPhi", mappings[0].var_name);
    TEST_ASSERT_EQUAL_STRING("", mappings[0].unit);
    TEST_ASSERT_EQUAL_STRING("gPF", mappings[0].lotse_key);
}

void test_parse_unknown_unit_leaves_empty_key(void)
{
    int n = transform_parse_script(SMI_18_LINE, mappings, MAX_MAPPINGS);
    int found_hz = 0;
    for (int i = 0; i < n; i++) {
        if (strcmp(mappings[i].var_name, "Frequency") == 0) {
            found_hz = 1;
            TEST_ASSERT_EQUAL_STRING("Hz", mappings[i].unit);
            TEST_ASSERT_EQUAL_STRING("gF", mappings[i].lotse_key);
            break;
        }
    }
    TEST_ASSERT(found_hz);
}

/* ── transform_apply_mapping tests ────────────────────── */

void test_apply_basic(void)
{
    clear_cfg();
    cfg.mapping_count = 3;
    strcpy(cfg.mappings[0].var_name, "Total_Bezug");
    strcpy(cfg.mappings[0].unit, "Wh");
    strcpy(cfg.mappings[0].lotse_key, "gEI");
    strcpy(cfg.mappings[1].var_name, "Total_Wirkleistung");
    strcpy(cfg.mappings[1].unit, "W");
    strcpy(cfg.mappings[1].lotse_key, "gP");
    strcpy(cfg.mappings[2].var_name, "Spannung_L1");
    strcpy(cfg.mappings[2].unit, "V");
    strcpy(cfg.mappings[2].lotse_key, "gV1");

    int n = transform_apply_mapping(TASMOTA_JSON_BASIC, &cfg, &payload);
    TEST_ASSERT_EQUAL_INT(3, n);

    TEST_ASSERT_EQUAL_STRING("gEI", payload.values[0].lotse_key);
    TEST_ASSERT_FLOAT_WITHIN(0.001, 1.2345, payload.values[0].value);
    TEST_ASSERT_EQUAL_STRING("gP", payload.values[1].lotse_key);
    TEST_ASSERT_FLOAT_WITHIN(0.001, -1.200, payload.values[1].value);
    TEST_ASSERT_EQUAL_STRING("gV1", payload.values[2].lotse_key);
    TEST_ASSERT_FLOAT_WITHIN(0.001, 230.1, payload.values[2].value);
}

void test_apply_w_to_kw(void)
{
    clear_cfg();
    cfg.mapping_count = 1;
    strcpy(cfg.mappings[0].var_name, "Power");
    strcpy(cfg.mappings[0].unit, "W");
    strcpy(cfg.mappings[0].lotse_key, "gP");

    int n = transform_apply_mapping("{\"SML1\":{\"Power\":1200}}", &cfg, &payload);
    TEST_ASSERT_EQUAL_INT(1, n);
    TEST_ASSERT_FLOAT_WITHIN(0.001, 1.200, payload.values[0].value);
}

void test_apply_mw_to_kw(void)
{
    clear_cfg();
    cfg.mapping_count = 1;
    strcpy(cfg.mappings[0].var_name, "Power");
    strcpy(cfg.mappings[0].unit, "MW");
    strcpy(cfg.mappings[0].lotse_key, "gP");

    int n = transform_apply_mapping("{\"SML1\":{\"Power\":2.5}}", &cfg, &payload);
    TEST_ASSERT_EQUAL_INT(1, n);
    /* MW→kW = 2500 kW, then clamped to ±500 by gP clamp */
    TEST_ASSERT_FLOAT_WITHIN(0.001, 500.0, payload.values[0].value);
}

void test_apply_wh_to_kwh(void)
{
    clear_cfg();
    cfg.mapping_count = 1;
    strcpy(cfg.mappings[0].var_name, "E_in");
    strcpy(cfg.mappings[0].unit, "Wh");
    strcpy(cfg.mappings[0].lotse_key, "gEI");

    int n = transform_apply_mapping("{\"SML1\":{\"E_in\":2500}}", &cfg, &payload);
    TEST_ASSERT_EQUAL_INT(1, n);
    TEST_ASSERT_FLOAT_WITHIN(0.001, 2.500, payload.values[0].value);
}

void test_apply_mwh_to_kwh(void)
{
    clear_cfg();
    cfg.mapping_count = 1;
    strcpy(cfg.mappings[0].var_name, "E_in");
    strcpy(cfg.mappings[0].unit, "MWh");
    strcpy(cfg.mappings[0].lotse_key, "gEI");

    int n = transform_apply_mapping("{\"SML1\":{\"E_in\":1.5}}", &cfg, &payload);
    TEST_ASSERT_EQUAL_INT(1, n);
    TEST_ASSERT_FLOAT_WITHIN(0.001, 1500.0, payload.values[0].value);
}

void test_apply_mv_to_v(void)
{
    clear_cfg();
    cfg.mapping_count = 1;
    strcpy(cfg.mappings[0].var_name, "Voltage");
    strcpy(cfg.mappings[0].unit, "mV");
    strcpy(cfg.mappings[0].lotse_key, "gV1");

    int n = transform_apply_mapping("{\"SML1\":{\"Voltage\":230100}}", &cfg, &payload);
    TEST_ASSERT_EQUAL_INT(1, n);
    TEST_ASSERT_FLOAT_WITHIN(0.001, 230.100, payload.values[0].value);
}

void test_apply_kv_to_v(void)
{
    clear_cfg();
    cfg.mapping_count = 1;
    strcpy(cfg.mappings[0].var_name, "Voltage");
    strcpy(cfg.mappings[0].unit, "kV");
    strcpy(cfg.mappings[0].lotse_key, "gV1");

    int n = transform_apply_mapping("{\"SML1\":{\"Voltage\":0.4}}", &cfg, &payload);
    TEST_ASSERT_EQUAL_INT(1, n);
    TEST_ASSERT_FLOAT_WITHIN(0.001, 400.0, payload.values[0].value);
}

void test_apply_empty_key_skipped(void)
{
    clear_cfg();
    cfg.mapping_count = 2;
    strcpy(cfg.mappings[0].var_name, "Power");
    strcpy(cfg.mappings[0].unit, "W");
    cfg.mappings[0].lotse_key[0] = 0;
    strcpy(cfg.mappings[1].var_name, "E_in");
    strcpy(cfg.mappings[1].unit, "kWh");
    strcpy(cfg.mappings[1].lotse_key, "gEI");

    int n = transform_apply_mapping(
        "{\"SML1\":{\"Power\":1200,\"E_in\":1.5}}", &cfg, &payload);
    TEST_ASSERT_EQUAL_INT(1, n);
    TEST_ASSERT_EQUAL_STRING("gEI", payload.values[0].lotse_key);
}

void test_apply_missing_var_skipped(void)
{
    clear_cfg();
    cfg.mapping_count = 2;
    strcpy(cfg.mappings[0].var_name, "Power");
    strcpy(cfg.mappings[0].unit, "W");
    strcpy(cfg.mappings[0].lotse_key, "gP");
    strcpy(cfg.mappings[1].var_name, "MissingVar");
    strcpy(cfg.mappings[1].unit, "W");
    strcpy(cfg.mappings[1].lotse_key, "gP");

    int n = transform_apply_mapping("{\"SML1\":{\"Power\":1200}}", &cfg, &payload);
    TEST_ASSERT_EQUAL_INT(1, n);
    TEST_ASSERT_EQUAL_STRING("gP", payload.values[0].lotse_key);
}

void test_apply_bs_clamp_low(void)
{
    clear_cfg();
    cfg.mapping_count = 1;
    strcpy(cfg.mappings[0].var_name, "BatteryPct");
    strcpy(cfg.mappings[0].unit, "%");
    strcpy(cfg.mappings[0].lotse_key, "bS");

    int n = transform_apply_mapping(TASMOTA_JSON_BS_CLAMP, &cfg, &payload);
    TEST_ASSERT_EQUAL_INT(1, n);
    TEST_ASSERT_FLOAT_WITHIN(0.001, 0.0, payload.values[0].value);
}

void test_apply_bs_clamp_high(void)
{
    clear_cfg();
    cfg.mapping_count = 1;
    strcpy(cfg.mappings[0].var_name, "BatteryPct");
    strcpy(cfg.mappings[0].unit, "%");
    strcpy(cfg.mappings[0].lotse_key, "bS");

    int n = transform_apply_mapping(TASMOTA_JSON_BS_CLAMP_HIGH, &cfg, &payload);
    TEST_ASSERT_EQUAL_INT(1, n);
    TEST_ASSERT_FLOAT_WITHIN(0.001, 100.0, payload.values[0].value);
}

void test_apply_energy_nonnegative(void)
{
    clear_cfg();
    cfg.mapping_count = 1;
    strcpy(cfg.mappings[0].var_name, "E_in");
    strcpy(cfg.mappings[0].unit, "Wh");
    strcpy(cfg.mappings[0].lotse_key, "gEI");

    int n = transform_apply_mapping(TASMOTA_JSON_ENERGY_NEGATIVE, &cfg, &payload);
    TEST_ASSERT_EQUAL_INT(1, n);
    TEST_ASSERT_TRUE(payload.values[0].value >= 0);
}

void test_apply_power_clamp_upper(void)
{
    clear_cfg();
    cfg.mapping_count = 1;
    strcpy(cfg.mappings[0].var_name, "Power");
    strcpy(cfg.mappings[0].unit, "W");
    strcpy(cfg.mappings[0].lotse_key, "gP");

    int n = transform_apply_mapping(TASMOTA_JSON_POWER_OVER, &cfg, &payload);
    TEST_ASSERT_EQUAL_INT(1, n);
    TEST_ASSERT_FLOAT_WITHIN(0.001, 500.0, payload.values[0].value);
}

void test_apply_power_clamp_lower(void)
{
    clear_cfg();
    cfg.mapping_count = 1;
    strcpy(cfg.mappings[0].var_name, "Power");
    strcpy(cfg.mappings[0].unit, "W");
    strcpy(cfg.mappings[0].lotse_key, "gP");

    int n = transform_apply_mapping(TASMOTA_JSON_POWER_UNDER, &cfg, &payload);
    TEST_ASSERT_EQUAL_INT(1, n);
    TEST_ASSERT_FLOAT_WITHIN(0.001, -500.0, payload.values[0].value);
}

void test_apply_no_nested_object(void)
{
    clear_cfg();
    int n = transform_apply_mapping(TASMOTA_JSON_NO_METER, &cfg, &payload);
    TEST_ASSERT_EQUAL_INT(-1, n);
}

void test_apply_invalid_json(void)
{
    clear_cfg();
    int n = transform_apply_mapping(TASMOTA_JSON_INVALID, &cfg, &payload);
    TEST_ASSERT_EQUAL_INT(-1, n);
}

/* ── transform_build_envelope tests ───────────────────── */

void test_envelope_valid_json(void)
{
    payload.count = 1;
    strcpy(payload.values[0].lotse_key, "gP");
    payload.values[0].value = -1.2;

    char *json = transform_build_envelope(&payload, 2892010904, 1);
    TEST_ASSERT_NOT_NULL(json);

    cJSON *root = cJSON_Parse(json);
    TEST_ASSERT_NOT_NULL(root);
    cJSON_Delete(root);
    free(json);
}

void test_envelope_fields(void)
{
    payload.count = 0;
    char *json = transform_build_envelope(&payload, 12345, 2);
    TEST_ASSERT_NOT_NULL(json);

    cJSON *root = cJSON_Parse(json);
    TEST_ASSERT_NOT_NULL(root);

    cJSON *from = cJSON_GetObjectItem(root, "from");
    TEST_ASSERT_NOT_NULL(from);
    TEST_ASSERT_TRUE(cJSON_IsNumber(from));

    cJSON *type = cJSON_GetObjectItem(root, "type");
    TEST_ASSERT_NOT_NULL(type);
    TEST_ASSERT_TRUE(cJSON_IsString(type));
    TEST_ASSERT_EQUAL_STRING("sendtext", type->valuestring);

    cJSON *payload_json = cJSON_GetObjectItem(root, "payload");
    TEST_ASSERT_NOT_NULL(payload_json);
    TEST_ASSERT_TRUE(cJSON_IsString(payload_json));

    cJSON *channel = cJSON_GetObjectItem(root, "channel");
    TEST_ASSERT_NOT_NULL(channel);
    TEST_ASSERT_TRUE(cJSON_IsNumber(channel));

    cJSON_Delete(root);
    free(json);
}

void test_envelope_from_value(void)
{
    payload.count = 0;
    char *json = transform_build_envelope(&payload, 2892010904, 1);
    TEST_ASSERT_NOT_NULL(json);

    cJSON *root = cJSON_Parse(json);
    TEST_ASSERT_NOT_NULL(root);

    cJSON *from = cJSON_GetObjectItem(root, "from");
    TEST_ASSERT_NOT_NULL(from);
    TEST_ASSERT_TRUE(cJSON_IsNumber(from));
    TEST_ASSERT_EQUAL_UINT32(2892010904, (uint32_t)from->valuedouble);

    cJSON_Delete(root);
    free(json);
}

void test_envelope_inner_roundtrip(void)
{
    payload.count = 2;
    strcpy(payload.values[0].lotse_key, "gP");
    payload.values[0].value = -1.234;
    strcpy(payload.values[1].lotse_key, "bS");
    payload.values[1].value = 85.0;

    char *json = transform_build_envelope(&payload, 12345, 1);
    TEST_ASSERT_NOT_NULL(json);

    cJSON *root = cJSON_Parse(json);
    TEST_ASSERT_NOT_NULL(root);

    cJSON *payload_str = cJSON_GetObjectItem(root, "payload");
    TEST_ASSERT_NOT_NULL(payload_str);
    TEST_ASSERT_TRUE(cJSON_IsString(payload_str));

    cJSON *inner = cJSON_Parse(payload_str->valuestring);
    TEST_ASSERT_NOT_NULL(inner);
    TEST_ASSERT_EQUAL_STRING("gP", cJSON_GetObjectItem(inner, "gP")->string);
    TEST_ASSERT_FLOAT_WITHIN(0.001, -1.234, cJSON_GetObjectItem(inner, "gP")->valuedouble);
    TEST_ASSERT_FLOAT_WITHIN(0.001, 85.0, cJSON_GetObjectItem(inner, "bS")->valuedouble);

    cJSON_Delete(inner);
    cJSON_Delete(root);
    free(json);
}

void test_envelope_empty_payload(void)
{
    payload.count = 0;
    char *json = transform_build_envelope(&payload, 999, 1);
    TEST_ASSERT_NOT_NULL(json);

    cJSON *root = cJSON_Parse(json);
    TEST_ASSERT_NOT_NULL(root);

    cJSON *payload_str = cJSON_GetObjectItem(root, "payload");
    TEST_ASSERT_NOT_NULL(payload_str);
    TEST_ASSERT_TRUE(cJSON_IsString(payload_str));

    cJSON *inner = cJSON_Parse(payload_str->valuestring);
    TEST_ASSERT_NOT_NULL(inner);
    TEST_ASSERT_EQUAL_INT(0, cJSON_GetArraySize(inner));

    cJSON_Delete(inner);
    cJSON_Delete(root);
    free(json);
}

/* ── GPIO tests ─────────────────────────────────────────── */

void test_parse_gpio_default(void)
{
    script_gpio_t gpio;
    transform_parse_gpio(SMI_WITH_GPIO, &gpio);
    TEST_ASSERT_EQUAL_INT(3, gpio.gpio_rx);
    TEST_ASSERT_EQUAL_INT(1, gpio.gpio_tx);
}

void test_parse_gpio_alternate(void)
{
    script_gpio_t gpio;
    transform_parse_gpio(SMI_WITH_DIFFERENT_GPIO, &gpio);
    TEST_ASSERT_EQUAL_INT(13, gpio.gpio_rx);
    TEST_ASSERT_EQUAL_INT(15, gpio.gpio_tx);
}

void test_parse_gpio_not_found(void)
{
    script_gpio_t gpio;
    transform_parse_gpio(SMI_NO_GPIO, &gpio);
    TEST_ASSERT_EQUAL_INT(-1, gpio.gpio_rx);
    TEST_ASSERT_EQUAL_INT(-1, gpio.gpio_tx);
}

void test_parse_gpio_plus_format(void)
{
    script_gpio_t gpio;
    transform_parse_gpio(SMI_WITH_PLUS_GPIO, &gpio);
    TEST_ASSERT_EQUAL_INT(3, gpio.gpio_rx);
    TEST_ASSERT_EQUAL_INT(1, gpio.gpio_tx);
}

void test_parse_gpio_plus_format_alternate(void)
{
    script_gpio_t gpio;
    transform_parse_gpio(SMI_WITH_PLUS_GPIO_ALT, &gpio);
    TEST_ASSERT_EQUAL_INT(15, gpio.gpio_rx);
    TEST_ASSERT_EQUAL_INT(1, gpio.gpio_tx);  // txGPIO is field 7, not M
}

void test_inject_gpio_into_script_without_section(void)
{
    char *result = transform_inject_gpio(SMI_NO_GPIO, 3, 1);
    TEST_ASSERT_NOT_NULL(result);
    TEST_ASSERT_EQUAL_STRING(">D\nGPIO3=1\nGPIO1=3\n\n1,1@1,Strombezug gesamt,Wh,E_total,0\n",
                             result);
    free(result);
}

void test_inject_gpio_replaces_existing(void)
{
    char *result = transform_inject_gpio(SMI_WITH_DIFFERENT_GPIO, 3, 1);
    TEST_ASSERT_NOT_NULL(result);
    TEST_ASSERT(strstr(result, "GPIO3=1") != NULL);
    TEST_ASSERT(strstr(result, "GPIO1=3") != NULL);
    TEST_ASSERT(strstr(result, "GPIO13=1") == NULL);
    TEST_ASSERT(strstr(result, "GPIO15=3") == NULL);
    TEST_ASSERT(strstr(result, "1,1@1,Strombezug gesamt") != NULL);
    free(result);
}

void test_inject_gpio_into_trailing_ws_section(void)
{
    // SMI_WITH_GPIO_TRAILING_WS has >D  \n (trailing spaces) and no + line
    char *result = transform_inject_gpio(SMI_WITH_GPIO_TRAILING_WS, 13, 15);
    TEST_ASSERT_NOT_NULL(result);
    // Should replace the existing >D section (with trailing space)
    TEST_ASSERT(strstr(result, ">D\nGPIO13=1\nGPIO15=3\n\n") != NULL);
    // Old values replaced
    TEST_ASSERT(strstr(result, "GPIO3=1") == NULL);
    TEST_ASSERT(strstr(result, "GPIO1=3") == NULL);
    // Data line with leading whitespace preserved
    TEST_ASSERT(strstr(result, "    1,1@1,Strombezug gesamt") != NULL);
    free(result);
}

void test_inject_gpio_updates_plus_format(void)
{
    char *result = transform_inject_gpio(SMI_WITH_PLUS_GPIO_ALT, 3, 1);
    TEST_ASSERT_NOT_NULL(result);
    // Preserves M=13, updates rx to 3
    TEST_ASSERT(strstr(result, "+13,3,") != NULL);
    // Preserves rest of the line
    TEST_ASSERT(strstr(result, "o,16,300") != NULL);
    TEST_ASSERT(strstr(result, "1,1@1,Strombezug gesamt") != NULL);
    free(result);
}

/* ── Leading whitespace tests ─────────────────────────────── */

void test_parse_leading_whitespace(void)
{
    int n = transform_parse_script(SMI_LEADING_WS, mappings, MAX_MAPPINGS);
    TEST_ASSERT_EQUAL_INT(18, n);
    // Verify a few known values parse correctly despite leading whitespace
    TEST_ASSERT_EQUAL_STRING("Total_Bezug", mappings[0].var_name);
    TEST_ASSERT_EQUAL_STRING("Wh", mappings[0].unit);
    TEST_ASSERT_EQUAL_STRING("Frequency", mappings[16].var_name);
    TEST_ASSERT_EQUAL_STRING("Hz", mappings[16].unit);
    TEST_ASSERT_EQUAL_STRING("CosPhi", mappings[17].var_name);
    TEST_ASSERT_EQUAL_STRING("", mappings[17].unit);
}

void test_parse_gpio_trailing_ws(void)
{
    script_gpio_t gpio;
    transform_parse_gpio(SMI_WITH_GPIO_TRAILING_WS, &gpio);
    TEST_ASSERT_EQUAL_INT(3, gpio.gpio_rx);
    TEST_ASSERT_EQUAL_INT(1, gpio.gpio_tx);
}

void test_parse_gpio_plus_leading_ws(void)
{
    script_gpio_t gpio;
    transform_parse_gpio(SMI_WITH_PLUS_LEADING_WS, &gpio);
    TEST_ASSERT_EQUAL_INT(3, gpio.gpio_rx);
    TEST_ASSERT_EQUAL_INT(1, gpio.gpio_tx);
    TEST_ASSERT(gpio.has_plus);
    TEST_ASSERT_EQUAL_INT('o', gpio.meter_type);
    TEST_ASSERT_EQUAL_INT(16, gpio.flag);
    TEST_ASSERT_EQUAL_INT(300, gpio.baudrate);
    TEST_ASSERT_EQUAL_STRING("ACE0", gpio.prefix);
}

void test_inject_gpio_into_leading_ws(void)
{
    char *result = transform_inject_gpio(SMI_LEADING_WS, 3, 1);
    TEST_ASSERT_NOT_NULL(result);
    // Script has + line, so it gets updated instead of >D section
    TEST_ASSERT(strstr(result, "+1,3,s,1,9600,SML") != NULL);
    // Data lines preserved
    TEST_ASSERT(strstr(result, "1,1@1,Bezug Total Wirkarbeit Wh") != NULL);
    free(result);
}

void test_parse_plus_line_baudrate(void)
{
    // Test with SMI_WITH_PLUS_GPIO which uses the standard format
    script_gpio_t gpio;
    transform_parse_gpio(SMI_WITH_PLUS_GPIO, &gpio);
    TEST_ASSERT(gpio.has_plus);
    TEST_ASSERT_EQUAL_INT('o', gpio.meter_type);
    TEST_ASSERT_EQUAL_INT(16, gpio.flag);
    TEST_ASSERT_EQUAL_INT(300, gpio.baudrate);
    TEST_ASSERT_EQUAL_STRING("ACE0", gpio.prefix);
}

void test_update_plus_line_preserves_meter(void)
{
    char *result = transform_inject_gpio(SMI_WITH_PLUS_GPIO_ALT, 3, 1);
    TEST_ASSERT_NOT_NULL(result);
    // M=13 should be preserved, rx updated to 3, tx stays 1
    TEST_ASSERT(strstr(result, "+13,3,o,16,300,ACE0,1,600,2F3F210D0A") != NULL);
    free(result);
}

/* ── Phase-aware auto-mapping tests ────────────────────────── */

void test_parse_phase_aware_power(void)
{
    int n = transform_parse_script(SMI_PHASE_SCRIPT, mappings, MAX_MAPPINGS);
    TEST_ASSERT_EQUAL_INT(11, n);
    // Leistung_L3 is index 6, check phase-aware assignment
    int leistung_l1 = -1, leistung_l2 = -1, leistung_l3 = -1, leistung_summe = -1;
    for (int i = 0; i < n; i++) {
        if (strcmp(mappings[i].var_name, "Watt_L1") == 0) leistung_l1 = i;
        else if (strcmp(mappings[i].var_name, "Watt_L2") == 0) leistung_l2 = i;
        else if (strcmp(mappings[i].var_name, "Watt_L3") == 0) leistung_l3 = i;
        else if (strcmp(mappings[i].var_name, "Watt_Summe") == 0) leistung_summe = i;
    }
    TEST_ASSERT(leistung_l1 >= 0);
    TEST_ASSERT(leistung_l2 >= 0);
    TEST_ASSERT(leistung_l3 >= 0);
    TEST_ASSERT(leistung_summe >= 0);
    TEST_ASSERT_EQUAL_STRING("gP1", mappings[leistung_l1].lotse_key);
    TEST_ASSERT_EQUAL_STRING("gP2", mappings[leistung_l2].lotse_key);
    TEST_ASSERT_EQUAL_STRING("gP3", mappings[leistung_l3].lotse_key);
    TEST_ASSERT_EQUAL_STRING("gP", mappings[leistung_summe].lotse_key);
}

void test_parse_phase_aware_voltage(void)
{
    int n = transform_parse_script(SMI_PHASE_SCRIPT, mappings, MAX_MAPPINGS);
    TEST_ASSERT_EQUAL_INT(11, n);
    int spannung_l1 = -1, spannung_l2 = -1, spannung_l3 = -1;
    for (int i = 0; i < n; i++) {
        if (strcmp(mappings[i].var_name, "Volt_L1") == 0) spannung_l1 = i;
        else if (strcmp(mappings[i].var_name, "Volt_L2") == 0) spannung_l2 = i;
        else if (strcmp(mappings[i].var_name, "Volt_L3") == 0) spannung_l3 = i;
    }
    TEST_ASSERT(spannung_l1 >= 0);
    TEST_ASSERT(spannung_l2 >= 0);
    TEST_ASSERT(spannung_l3 >= 0);
    TEST_ASSERT_EQUAL_STRING("gV1", mappings[spannung_l1].lotse_key);
    TEST_ASSERT_EQUAL_STRING("gV2", mappings[spannung_l2].lotse_key);
    TEST_ASSERT_EQUAL_STRING("gV3", mappings[spannung_l3].lotse_key);
}

/* ── Dedup tests ─────────────────────────────────────────── */

void test_parse_auto_dedup_3power(void)
{
    int n = transform_parse_script(SMI_3_POWER, mappings, MAX_MAPPINGS);
    TEST_ASSERT_EQUAL_INT(3, n);
    TEST_ASSERT_EQUAL_STRING("gP",  mappings[0].lotse_key);
    TEST_ASSERT_EQUAL_STRING("gP1", mappings[1].lotse_key);
    TEST_ASSERT_EQUAL_STRING("gP2", mappings[2].lotse_key);
}

void test_parse_auto_dedup_overflow(void)
{
    int n = transform_parse_script(SMI_5_POWER, mappings, MAX_MAPPINGS);
    TEST_ASSERT_EQUAL_INT(5, n);
    TEST_ASSERT_EQUAL_STRING("gP",  mappings[0].lotse_key);
    TEST_ASSERT_EQUAL_STRING("gP1", mappings[1].lotse_key);
    TEST_ASSERT_EQUAL_STRING("gP2", mappings[2].lotse_key);
    TEST_ASSERT_EQUAL_STRING("gP3", mappings[3].lotse_key);
    TEST_ASSERT_EQUAL_STRING("",    mappings[4].lotse_key);
}

void test_parse_auto_dedup_energy(void)
{
    int n = transform_parse_script(SMI_2_ENERGY, mappings, MAX_MAPPINGS);
    TEST_ASSERT_EQUAL_INT(2, n);
    TEST_ASSERT_EQUAL_STRING("gEI", mappings[0].lotse_key);
    TEST_ASSERT_EQUAL_STRING("gEO", mappings[1].lotse_key);
}

void test_parse_auto_dedup_voltage(void)
{
    int n = transform_parse_script(SMI_3_VOLTAGE, mappings, MAX_MAPPINGS);
    TEST_ASSERT_EQUAL_INT(3, n);
    TEST_ASSERT_EQUAL_STRING("gV1", mappings[0].lotse_key);
    TEST_ASSERT_EQUAL_STRING("gV2", mappings[1].lotse_key);
    TEST_ASSERT_EQUAL_STRING("gV3", mappings[2].lotse_key);
}

void test_apply_dedup_collision(void)
{
    clear_cfg();
    cfg.mapping_count = 2;
    strcpy(cfg.mappings[0].var_name, "Power");
    strcpy(cfg.mappings[0].unit, "W");
    strcpy(cfg.mappings[0].lotse_key, "gP");
    strcpy(cfg.mappings[1].var_name, "OtherPower");
    strcpy(cfg.mappings[1].unit, "W");
    strcpy(cfg.mappings[1].lotse_key, "gP");

    int n = transform_apply_mapping(TASMOTA_JSON_DEDUP, &cfg, &payload);
    TEST_ASSERT_EQUAL_INT(1, n);
    TEST_ASSERT_EQUAL_STRING("gP", payload.values[0].lotse_key);
    // First var (Power=1200) should win: 1200 W → 1.2 kW
    TEST_ASSERT_FLOAT_WITHIN(0.001, 1.2, payload.values[0].value);
}

/* ── runner ────────────────────────────────────────────── */

void setUp(void) { }
void tearDown(void) { }

int main(void)
{
    UNITY_BEGIN();

    RUN_TEST(test_parse_real_hichi);
    RUN_TEST(test_parse_auto_mapping);
    RUN_TEST(test_parse_suggests_bs_for_percent);
    RUN_TEST(test_parse_amperage_maps_to_ga);
    RUN_TEST(test_parse_long_script);
    RUN_TEST(test_parse_empty_script);
    RUN_TEST(test_parse_malformed);
    RUN_TEST(test_parse_no_unit);
    RUN_TEST(test_parse_unknown_unit_leaves_empty_key);

    RUN_TEST(test_apply_basic);
    RUN_TEST(test_apply_w_to_kw);
    RUN_TEST(test_apply_mw_to_kw);
    RUN_TEST(test_apply_wh_to_kwh);
    RUN_TEST(test_apply_mwh_to_kwh);
    RUN_TEST(test_apply_mv_to_v);
    RUN_TEST(test_apply_kv_to_v);
    RUN_TEST(test_apply_empty_key_skipped);
    RUN_TEST(test_apply_missing_var_skipped);
    RUN_TEST(test_apply_bs_clamp_low);
    RUN_TEST(test_apply_bs_clamp_high);
    RUN_TEST(test_apply_energy_nonnegative);
    RUN_TEST(test_apply_power_clamp_upper);
    RUN_TEST(test_apply_power_clamp_lower);
    RUN_TEST(test_apply_no_nested_object);
    RUN_TEST(test_apply_invalid_json);

    RUN_TEST(test_envelope_valid_json);
    RUN_TEST(test_envelope_fields);
    RUN_TEST(test_envelope_from_value);
    RUN_TEST(test_envelope_inner_roundtrip);
    RUN_TEST(test_envelope_empty_payload);

    RUN_TEST(test_parse_gpio_default);
    RUN_TEST(test_parse_gpio_alternate);
    RUN_TEST(test_parse_gpio_not_found);
    RUN_TEST(test_parse_gpio_plus_format);
    RUN_TEST(test_parse_gpio_plus_format_alternate);
    RUN_TEST(test_inject_gpio_into_script_without_section);
    RUN_TEST(test_inject_gpio_replaces_existing);
    RUN_TEST(test_inject_gpio_into_trailing_ws_section);
    RUN_TEST(test_inject_gpio_updates_plus_format);

    RUN_TEST(test_parse_leading_whitespace);
    RUN_TEST(test_parse_gpio_trailing_ws);
    RUN_TEST(test_parse_gpio_plus_leading_ws);
    RUN_TEST(test_inject_gpio_into_leading_ws);
    RUN_TEST(test_parse_plus_line_baudrate);
    RUN_TEST(test_update_plus_line_preserves_meter);

    RUN_TEST(test_parse_phase_aware_power);
    RUN_TEST(test_parse_phase_aware_voltage);

    RUN_TEST(test_parse_auto_dedup_3power);
    RUN_TEST(test_parse_auto_dedup_overflow);
    RUN_TEST(test_parse_auto_dedup_energy);
    RUN_TEST(test_parse_auto_dedup_voltage);
    RUN_TEST(test_apply_dedup_collision);

    return UNITY_END();
}
