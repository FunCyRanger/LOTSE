#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include "esp_log.h"
#include "cJSON.h"
#include "transform.h"

static const char *TAG = "transform";

int transform_parse_script(const char *script, var_mapping_t *mappings, int max)
{
    int count = 0;
    const char *p = script;

    while (p && *p && count < max) {
        if (strncmp(p, "1,", 2) != 0) {
            p = strstr(p, "\n1,");
            if (!p) break;
            p++;
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

            // Auto-suggest LOTSE key based on unit
            if (strcmp(mappings[count].unit, "W") == 0)
                strcpy(mappings[count].lotse_key, "gP");
            else if (strcmp(mappings[count].unit, "kW") == 0)
                strcpy(mappings[count].lotse_key, "gP");
            else if (strstr(mappings[count].unit, "Wh") || strstr(mappings[count].unit, "kWh"))
                strcpy(mappings[count].lotse_key, "gEI");
            else if (strstr(mappings[count].unit, "V") && strlen(mappings[count].unit) <= 2)
                strcpy(mappings[count].lotse_key, "gV1");
            else if (strcmp(mappings[count].unit, "%") == 0)
                strcpy(mappings[count].lotse_key, "bS");
            else if (strcmp(mappings[count].unit, "A") == 0)
                strcpy(mappings[count].lotse_key, ""); // no LOTSE key for current
            else
                mappings[count].lotse_key[0] = 0;

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
    // Find the first nested object (the meter data)
    cJSON *meter_obj = NULL;
    cJSON *child = root->child;
    while (child) {
        if (cJSON_IsObject(child)) { meter_obj = child; break; }
        child = child->next;
    }
    if (!meter_obj) { ESP_LOGD(TAG, "map: no nested object found"); cJSON_Delete(root); return -1; }

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
        if (strcmp(unit, "W") == 0) converted = raw * 0.001;  // W → kW
        else if (strcmp(unit, "MW") == 0) converted = raw * 1000.0;
        else if (strcmp(unit, "Wh") == 0) converted = raw * 0.001;
        else if (strcmp(unit, "MWh") == 0) converted = raw * 1000.0;
        else if (strcmp(unit, "mV") == 0) converted = raw * 0.001;
        else if (strcmp(unit, "kV") == 0) converted = raw * 1000.0;

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
        }

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

static void parse_plus_line(const char *line, script_gpio_t *gpio)
{
    int tx, rx;
    if (sscanf(line, "+%d,%d", &tx, &rx) >= 2) {
        gpio->gpio_tx = tx;
        gpio->gpio_rx = rx;
    }
}

void transform_parse_gpio(const char *script, script_gpio_t *gpio)
{
    gpio->gpio_rx = -1;
    gpio->gpio_tx = -1;

    const char *d = strstr(script, ">D\n");
    if (!d) {
        d = strstr(script, ">D\r\n");
    }

    if (d) {
        d += 3;
        if (*d == '\r') d++;
        if (*d == '\n') d++;

        const char *section_end = strstr(d, "\n\n");
        if (!section_end) section_end = d + strlen(d);

        while (d < section_end) {
            const char *nl = strchr(d, '\n');
            if (!nl) nl = d + strlen(d);
            if (nl > section_end) nl = section_end;

            int pin = -1, func = -1;
            if (sscanf(d, "GPIO%d=%d", &pin, &func) >= 2) {
                if (func == 1) gpio->gpio_rx = pin;
                else if (func == 3) gpio->gpio_tx = pin;
            }

            d = nl;
            if (*d) d++;
        }
    }

    // If not found in >D section, try +<tx>,<rx> format
    if (gpio->gpio_rx < 0 || gpio->gpio_tx < 0) {
        const char *p = script;

        // Check if script starts with +
        if (*p == '+') {
            parse_plus_line(p, gpio);
        } else {
            while ((p = strchr(p, '\n')) != NULL) {
                p++;
                if (*p == '+') {
                    parse_plus_line(p, gpio);
                    break;
                }
            }
        }
    }
}

static void build_gpio_lines(char *buf, size_t size, int gpio_rx, int gpio_tx)
{
    snprintf(buf, size, ">D\nGPIO%d=1\nGPIO%d=3\n\n", gpio_rx, gpio_tx);
}

static char *update_plus_line(const char *script, int gpio_rx, int gpio_tx)
{
    const char *plus = NULL;

    if (*script == '+') {
        plus = script;
    } else {
        plus = strstr(script, "\n+");
        if (plus) plus++;
    }

    if (!plus) return NULL;

    int old_tx, old_rx;
    char mode[16] = {0};
    int baud = 0, interchar = 0;
    char serialcfg[32] = {0};
    int serialtype = 0, timeout = 0;
    char init[64] = {0};

    int n = sscanf(plus, "+%d,%d,%15[^,],%d,%d,%31[^,],%d,%d,%63s",
                  &old_tx, &old_rx, mode, &baud, &interchar,
                  serialcfg, &serialtype, &timeout, init);
    if (n < 3) return NULL;

    char new_line[128];
    snprintf(new_line, sizeof(new_line), "+%d,%d,%s,%d,%d,%s,%d,%d,%s",
             gpio_tx, gpio_rx, mode, baud, interchar,
             serialcfg, serialtype, timeout, init);

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

    const char *d = strstr(script, ">D\n");
    if (d) {
        const char *section_end = strstr(d, "\n\n");
        if (!section_end) section_end = d + strlen(d);
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

    const char *first_var = strstr(script, "1,");
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
