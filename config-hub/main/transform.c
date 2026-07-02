#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include "esp_log.h"
#include "cJSON.h"
#include "transform.h"

static const char *TAG = "transform";

static bool key_already_used(const var_mapping_t *mappings, int count, const char *key)
{
    for (int i = 0; i < count; i++) {
        if (strcmp(mappings[i].lotse_key, key) == 0) return true;
    }
    return false;
}

static const char *first_unused_slot(const char *pool[], const var_mapping_t *mappings, int count)
{
    for (int i = 0; pool[i]; i++) {
        if (!key_already_used(mappings, count, pool[i])) return pool[i];
    }
    return NULL;
}

int transform_parse_script(const char *script, var_mapping_t *mappings, int max)
{
    static const char *power_slots[] = {"gP", "gP1", "gP2", "gP3", NULL};
    static const char *energy_slots[] = {"gEI", "gEO", NULL};
    static const char *voltage_slots[] = {"gV1", "gV2", "gV3", NULL};
    static const char *current_slots[] = {"gA1", "gA2", "gA3", NULL};

    int count = 0;
    const char *p = script;

    while (p && *p && count < max) {
        while (*p == ' ' || *p == '\t') p++;
        if (strncmp(p, "1,", 2) != 0) {
            p = strchr(p, '\n');
            if (!p) break;
            p++;
            continue;
        }

        const char *line_end = strchr(p, '\n');
        if (!line_end) line_end = p + strlen(p);

        // Extract the last field (variable name) before the precision number
        // Format: M,decoder@scale,label,unit,varname,precision
        const char *last_comma = NULL;
        const char *scan = p;
        int comma_count = 0;
        while (scan < line_end) {
            if (*scan == ',') { last_comma = scan; comma_count++; }
            scan++;
        }

        if (!last_comma || comma_count < 5) { p = line_end + 1; continue; }

        // Find the field before last comma (var name)
        const char *var_start = last_comma - 1;
        while (var_start > p && *var_start != ',') var_start--;
        if (*var_start == ',') var_start++;

        char varname[32] = {0};
        int vlen = (last_comma - var_start);
        if (vlen > 31) vlen = 31;
        strncpy(varname, var_start, vlen);

        // Find label (third field: between comma 2 and comma 3)
        const char *l1 = p;
        int lcnt = 0;
        const char *l_start = NULL, *l_end = NULL;
        while (l1 < line_end && lcnt < 3) {
            if (*l1 == ',') {
                lcnt++;
                if (lcnt == 2) l_start = l1 + 1;
                if (lcnt == 3) l_end = l1;
            }
            l1++;
        }

        // Find unit (fourth field: between comma 3 and comma 4)
        const char *u1 = p;
        int ucnt = 0;
        const char *u_start = NULL, *u_end = NULL;
        while (u1 < line_end && ucnt < 4) {
            if (*u1 == ',') {
                ucnt++;
                if (ucnt == 3) u_start = u1 + 1;
                if (ucnt == 4) u_end = u1;
            }
            u1++;
        }

        int parsed_ok = (varname[0] && u_start && u_end);
        if (parsed_ok) {
            strncpy(mappings[count].var_name, varname, sizeof(mappings[count].var_name)-1);
            int ulen = u_end - u_start;
            if (ulen > 7) ulen = 7;
            strncpy(mappings[count].unit, u_start, ulen);
            mappings[count].unit[ulen] = 0;

            if (l_start && l_end) {
                int llen = l_end - l_start;
                if (llen > 31) llen = 31;
                strncpy(mappings[count].label, l_start, llen);
                mappings[count].label[llen] = 0;
            }

            // Auto-suggest LOTSE key — phase-aware for power/voltage, cycle for others
            const char *assigned = NULL;
            if (strcasecmp(mappings[count].unit, "W") == 0 || strcasecmp(mappings[count].unit, "kW") == 0) {
                const char *nm = mappings[count].label;
                if (!nm[0]) nm = mappings[count].var_name;
                if      (strstr(nm, "L1")) assigned = key_already_used(mappings, count, "gP1") ? NULL : "gP1";
                else if (strstr(nm, "L2")) assigned = key_already_used(mappings, count, "gP2") ? NULL : "gP2";
                else if (strstr(nm, "L3")) assigned = key_already_used(mappings, count, "gP3") ? NULL : "gP3";
                else                       assigned = first_unused_slot(power_slots, mappings, count);
            } else if (strcasestr(mappings[count].unit, "Wh")) {
                assigned = first_unused_slot(energy_slots, mappings, count);
            } else if (strcasestr(mappings[count].unit, "V") && strlen(mappings[count].unit) <= 2) {
                const char *nm = mappings[count].label;
                if (!nm[0]) nm = mappings[count].var_name;
                if      (strstr(nm, "L1")) assigned = key_already_used(mappings, count, "gV1") ? NULL : "gV1";
                else if (strstr(nm, "L2")) assigned = key_already_used(mappings, count, "gV2") ? NULL : "gV2";
                else if (strstr(nm, "L3")) assigned = key_already_used(mappings, count, "gV3") ? NULL : "gV3";
                else                       assigned = first_unused_slot(voltage_slots, mappings, count);
            } else if (strcmp(mappings[count].unit, "%") == 0) {
                assigned = key_already_used(mappings, count, "bS") ? NULL : "bS";
            } else if (strcmp(mappings[count].unit, "A") == 0) {
                const char *nm = mappings[count].label;
                if (!nm[0]) nm = mappings[count].var_name;
                if      (strstr(nm, "L1")) assigned = key_already_used(mappings, count, "gA1") ? NULL : "gA1";
                else if (strstr(nm, "L2")) assigned = key_already_used(mappings, count, "gA2") ? NULL : "gA2";
                else if (strstr(nm, "L3")) assigned = key_already_used(mappings, count, "gA3") ? NULL : "gA3";
                else                       assigned = first_unused_slot(current_slots, mappings, count);
            } else if (strcmp(mappings[count].unit, "Hz") == 0) {
                assigned = key_already_used(mappings, count, "gF") ? NULL : "gF";
            } else if (mappings[count].unit[0] == 0 && strcasestr(mappings[count].label, "Power factor")) {
                assigned = key_already_used(mappings, count, "gPF") ? NULL : "gPF";
            }

            if (assigned) {
                strncpy(mappings[count].lotse_key, assigned, LOTSE_KEY_LEN - 1);
            } else {
                mappings[count].lotse_key[0] = 0;
            }

            count++;
        }

        p = line_end;
        if (*p) p++;
    }

    return count;
}

int transform_apply_mapping(const char *tasmota_json, const hub_config_t *cfg,
                            lotse_payload_t *out)
{
    out->count = 0;
    cJSON *root = cJSON_Parse(tasmota_json);
    if (!root) { ESP_LOGD(TAG, "map: JSON parse failed: %.100s", tasmota_json); return -1; }

    // Tasmota SMI publishes: {"SML1":{"Power":-1200, "E_in":1234.5, ...}}
    // Tasmota discovery publishes: {"sn":{"Time":"...","ACE0":{"Meter_id":0,...}}}
    // Find the first nested object (the meter data)
    cJSON *meter_obj = NULL;
    cJSON *child = root->child;
    while (child) {
        if (cJSON_IsObject(child)) { meter_obj = child; break; }
        child = child->next;
    }
    if (!meter_obj) { ESP_LOGD(TAG, "map: no nested object found"); cJSON_Delete(root); return -1; }

    // If the found object is "sn" (discovery), it contains further meter objects
    if (strcmp(meter_obj->string, "sn") == 0) {
        cJSON *sn_child = meter_obj->child;
        while (sn_child) {
            if (cJSON_IsObject(sn_child)) { meter_obj = sn_child; break; }
            sn_child = sn_child->next;
        }
    }
    if (!meter_obj) { ESP_LOGD(TAG, "map: no meter data inside 'sn' found"); cJSON_Delete(root); return -1; }

    ESP_LOGD(TAG, "map: found meter key '%s' with %d mappings", meter_obj->string, cfg->mapping_count);

    for (int i = 0; i < cfg->mapping_count; i++) {
        const char *var = cfg->mappings[i].var_name;
        const char *key = cfg->mappings[i].lotse_key;
        if (!var[0] || !key[0]) continue;

        cJSON *val = cJSON_GetObjectItem(meter_obj, var);
        if (!val) continue;

        double raw = cJSON_IsNumber(val) ? val->valuedouble : 0;
        const char *unit = cfg->mappings[i].unit;
        double converted = raw;

        // Convert to LOTSE standard units
        if (strcasecmp(unit, "W") == 0) converted = raw * 0.001;  // W → kW
        else if (strcasecmp(unit, "MW") == 0) converted = raw * 1000.0;
        else if (strcasecmp(unit, "Wh") == 0) converted = raw * 0.001;
        else if (strcasecmp(unit, "MWh") == 0) converted = raw * 1000.0;
        else if (strcasecmp(unit, "mV") == 0) converted = raw * 0.001;
        else if (strcasecmp(unit, "kV") == 0) converted = raw * 1000.0;

        // Clamp
        if (strcmp(key, "bS") == 0) {
            if (converted < 0) converted = 0;
            if (converted > 100) converted = 100;
        } else if (strcmp(key, "gIP") == 0 || strcmp(key, "gEP") == 0 ||
                   strcmp(key, "gEI") == 0 || strcmp(key, "gEO") == 0 ||
                   strcmp(key, "sE") == 0 || strcmp(key, "bEI") == 0 ||
                   strcmp(key, "bEO") == 0 || strcmp(key, "wE") == 0) {
            if (converted < 0) converted = 0;
        } else if (strcmp(key, "gP") == 0 || strcmp(key, "sP") == 0 ||
                   strcmp(key, "bP") == 0 || strcmp(key, "wP") == 0 ||
                   strcmp(key, "gP1") == 0 || strcmp(key, "gP2") == 0 || strcmp(key, "gP3") == 0) {
            if (converted > 500) converted = 500;
            if (converted < -500) converted = -500;
        } else if (strcmp(key, "gA1") == 0 || strcmp(key, "gA2") == 0 || strcmp(key, "gA3") == 0) {
            if (converted < 0) converted = 0;
        } else if (strcmp(key, "gF") == 0) {
            if (converted < 45) converted = 45;
            if (converted > 65) converted = 65;
        } else if (strcmp(key, "gPF") == 0) {
            if (converted < 0) converted = 0;
            if (converted > 1) converted = 1;
        }

        // Skip duplicate lotse_key — keep first occurrence
        bool dup = false;
        for (int j = 0; j < out->count; j++) {
            if (strcmp(out->values[j].lotse_key, key) == 0) {
                ESP_LOGW(TAG, "map: duplicate lotse_key '%s' for var '%s', skipping", key, var);
                dup = true;
                break;
            }
        }
        if (dup) continue;

        int idx = out->count;
        strncpy(out->values[idx].lotse_key, key, LOTSE_KEY_LEN-1);
        out->values[idx].value = converted;
        out->count++;
    }

    cJSON_Delete(root);
    return out->count;
}

char *transform_build_envelope(const lotse_payload_t *payload, uint32_t node_decimal,
                               int channel)
{
    cJSON *inner = cJSON_CreateObject();
    for (int i = 0; i < payload->count; i++) {
        char key[LOTSE_KEY_LEN];
        strncpy(key, payload->values[i].lotse_key, LOTSE_KEY_LEN-1);
        cJSON_AddNumberToObject(inner, key, payload->values[i].value);
    }
    char *inner_str = cJSON_PrintUnformatted(inner);
    cJSON_Delete(inner);

    if (!inner_str) return NULL;

    cJSON *envelope = cJSON_CreateObject();
    cJSON_AddNumberToObject(envelope, "from", node_decimal);
    cJSON_AddStringToObject(envelope, "type", "sendtext");
    cJSON_AddStringToObject(envelope, "payload", inner_str);
    cJSON_AddNumberToObject(envelope, "channel", channel);
    free(inner_str);

    char *result = cJSON_PrintUnformatted(envelope);
    cJSON_Delete(envelope);
    return result;
}

char *transform_build_config_envelope(const hub_config_t *cfg, uint32_t node_decimal,
                                      int channel)
{
    // Build inner JSON object with only non-zero config keys
    cJSON *inner = cJSON_CreateObject();
    if (cfg->battery_capacity > 0)
        cJSON_AddNumberToObject(inner, "bC", cfg->battery_capacity);
    if (cfg->solar_peak > 0)
        cJSON_AddNumberToObject(inner, "sK", cfg->solar_peak);
    if (cfg->panel_angle >= 0)
        cJSON_AddNumberToObject(inner, "sA", cfg->panel_angle);
    if (cfg->panel_azimuth >= 0)
        cJSON_AddNumberToObject(inner, "sZ", cfg->panel_azimuth);

    char *inner_str = cJSON_PrintUnformatted(inner);
    cJSON_Delete(inner);
    if (!inner_str) return NULL;

    cJSON *envelope = cJSON_CreateObject();
    cJSON_AddNumberToObject(envelope, "from", node_decimal);
    cJSON_AddStringToObject(envelope, "type", "sendtext");
    cJSON_AddStringToObject(envelope, "payload", inner_str);
    cJSON_AddNumberToObject(envelope, "channel", channel);
    free(inner_str);

    char *result = cJSON_PrintUnformatted(envelope);
    cJSON_Delete(envelope);
    return result;
}

static const char *find_plus_line(const char *script)
{
    const char *p = script;
    while (*p == ' ' || *p == '\t') p++;
    if (*p == '+') return p;

    while ((p = strchr(p, '\n')) != NULL) {
        p++;
        while (*p == ' ' || *p == '\t') p++;
        if (*p == '+') return p;
    }
    return NULL;
}

static void parse_plus_line(const char *line, script_gpio_t *gpio)
{
    // +<M>,<rxGPIO>,<type>,<flag>,<baudrate>,<jsonPrefix>{,<txGPIO>,<txPeriod>,<cmdTelegram>}
    int meter, rx = -1, tx = -1, flag = 0, baud = 0, period = 0;
    char mode[16] = {0}, prefix[16] = {0}, cmd[64] = {0};

    int n = sscanf(line, "+%d,%d,%15[^,],%d,%d,%15[^,],%d,%d,%63s",
                   &meter, &rx, mode, &flag, &baud, prefix, &tx, &period, cmd);

    gpio->gpio_rx = (rx >= 0) ? rx : -1;
    gpio->gpio_tx = (tx >= 0) ? tx : -1;
    gpio->has_plus = true;
    gpio->meter_type = (n >= 3 && mode[0]) ? mode[0] : 0;
    gpio->flag = (n >= 4) ? flag : 0;
    gpio->baudrate = (n >= 5) ? baud : 0;
    if (n >= 6) {
        strncpy(gpio->prefix, prefix, sizeof(gpio->prefix) - 1);
    } else {
        gpio->prefix[0] = 0;
    }
}

void transform_parse_gpio(const char *script, script_gpio_t *gpio)
{
    gpio->gpio_rx = -1;
    gpio->gpio_tx = -1;
    gpio->has_plus = false;
    gpio->meter_type = 0;
    gpio->flag = 0;
    gpio->baudrate = 0;
    gpio->prefix[0] = 0;

    // Find >D followed by optional spaces/tabs then \n
    const char *d = strstr(script, ">D");
    if (d) {
        const char *after = d + 2;
        while (*after == ' ' || *after == '\t') after++;
        if (*after == '\r') after++;
        if (*after == '\n') {
            after++;
            const char *section_end = strstr(after, "\n\n");
            if (!section_end) section_end = after + strlen(after);

            while (after < section_end) {
                const char *nl = strchr(after, '\n');
                if (!nl) nl = after + strlen(after);
                if (nl > section_end) nl = section_end;

                int pin = -1, func = -1;
                if (sscanf(after, "GPIO%d=%d", &pin, &func) >= 2) {
                    if (func == 1) gpio->gpio_rx = pin;
                    else if (func == 3) gpio->gpio_tx = pin;
                }
                after = nl;
                if (*after) after++;
            }
        }
    }

    // Fallback: try + line format
    if (gpio->gpio_rx < 0 || gpio->gpio_tx < 0) {
        const char *plus = find_plus_line(script);
        if (plus) {
            parse_plus_line(plus, gpio);
        }
    }
}

static void build_gpio_lines(char *buf, size_t size, int gpio_rx, int gpio_tx)
{
    snprintf(buf, size, ">D\nGPIO%d=1\nGPIO%d=3\n\n", gpio_rx, gpio_tx);
}

static char *update_plus_line(const char *script, int gpio_rx, int gpio_tx)
{
    const char *plus = find_plus_line(script);
    if (!plus) return NULL;

    // +<M>,<rxGPIO>,<type>,<flag>,<baudrate>,<jsonPrefix>{,<txGPIO>,<txPeriod>,<cmdTelegram>}
    int meter, old_rx = -1, old_tx = -1, flag = 0, baud = 0, period = 0;
    char mode[16] = {0}, prefix[16] = {0}, cmd[64] = {0};

    int n = sscanf(plus, "+%d,%d,%15[^,],%d,%d,%15[^,],%d,%d,%63s",
                   &meter, &old_rx, mode, &flag, &baud, prefix, &old_tx, &period, cmd);
    if (n < 3) return NULL;

    char new_line[128];
    if (n >= 7) {
        snprintf(new_line, sizeof(new_line), "+%d,%d,%s,%d,%d,%s,%d,%d,%s",
                 meter, gpio_rx, mode, flag, baud, prefix, gpio_tx, period, cmd);
    } else if (n >= 6) {
        snprintf(new_line, sizeof(new_line), "+%d,%d,%s,%d,%d,%s",
                 meter, gpio_rx, mode, flag, baud, prefix);
    } else {
        snprintf(new_line, sizeof(new_line), "+%d,%d,%s,%d,%d",
                 meter, gpio_rx, mode, flag, baud);
    }

    const char *line_end = strchr(plus, '\n');
    if (!line_end) line_end = plus + strlen(plus);

    size_t before_len = plus - script;
    size_t after_len = strlen(line_end);
    size_t new_line_len = strlen(new_line);

    char *result = malloc(before_len + new_line_len + after_len + 1);
    if (!result) return NULL;
    memcpy(result, script, before_len);
    memcpy(result + before_len, new_line, new_line_len);
    memcpy(result + before_len + new_line_len, line_end, after_len + 1);
    return result;
}

char *transform_inject_gpio(const char *script, int gpio_rx, int gpio_tx)
{
    // First try to update a + line if present
    char *result = update_plus_line(script, gpio_rx, gpio_tx);
    if (result) return result;

    char gpio_lines[64];
    build_gpio_lines(gpio_lines, sizeof(gpio_lines), gpio_rx, gpio_tx);
    size_t gpio_len = strlen(gpio_lines);

    // Find >D followed by optional spaces/tabs then \n
    const char *d = strstr(script, ">D");
    if (d) {
        const char *after_marker = d + 2;
        while (*after_marker == ' ' || *after_marker == '\t') after_marker++;
        if (*after_marker == '\r') after_marker++;
        if (*after_marker == '\n') {
            after_marker++;
            const char *section_end = strstr(after_marker, "\n\n");
            if (!section_end) section_end = after_marker + strlen(after_marker);
            const char *after = section_end;
            while (*after == '\n') after++;

            size_t before_len = d - script;
            size_t after_len = strlen(after);
            result = malloc(before_len + gpio_len + after_len + 1);
            if (!result) return NULL;
            memcpy(result, script, before_len);
            memcpy(result + before_len, gpio_lines, gpio_len);
            memcpy(result + before_len + gpio_len, after, after_len + 1);
            return result;
        }
    }

    // Find first 1, line (with optional leading whitespace)
    const char *first_var = NULL;
    {
        const char *scan = script;
        while (*scan) {
            while (*scan == ' ' || *scan == '\t') scan++;
            if (strncmp(scan, "1,", 2) == 0) { first_var = scan; break; }
            scan = strchr(scan, '\n');
            if (!scan) break;
            scan++;
        }
    }
    if (first_var) {
        size_t before_len = first_var - script;
        size_t after_len = strlen(first_var);
        result = malloc(before_len + gpio_len + after_len + 1);
        if (!result) return NULL;
        memcpy(result, script, before_len);
        memcpy(result + before_len, gpio_lines, gpio_len);
        memcpy(result + before_len + gpio_len, first_var, after_len + 1);
        return result;
    }

    size_t slen = strlen(script);
    result = malloc(gpio_len + slen + 1);
    if (!result) return NULL;
    memcpy(result, gpio_lines, gpio_len);
    memcpy(result + gpio_len, script, slen + 1);
    return result;
}
