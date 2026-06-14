#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_http_server.h"
#include "cJSON.h"
#include "web_server.h"
#include "html.h"
#include "config_store.h"
#include "wifi_manager.h"
#include "mqtt_broker.h"
#include "tasmota_client.h"
#include "transform.h"

static const char *TAG = "web_server";
static hub_config_t *g_cfg = NULL;
static httpd_handle_t s_server = NULL;

static esp_err_t handle_static_file(httpd_req_t *req);

static esp_err_t get_header_str(httpd_req_t *req, const char *key, char *buf, size_t len)
{
    return httpd_req_get_hdr_value_str(req, key, buf, len);
}

static esp_err_t read_post_data(httpd_req_t *req, char **out, size_t *out_len)
{
    int total = req->content_len;
    if (total <= 0) return ESP_FAIL;
    char *buf = calloc(1, total + 1);
    if (!buf) return ESP_ERR_NO_MEM;
    int received = 0;
    while (received < total) {
        int r = httpd_req_recv(req, buf + received, total - received);
        if (r <= 0) { free(buf); return ESP_FAIL; }
        received += r;
    }
    buf[total] = 0;
    *out = buf;
    *out_len = total;
    return ESP_OK;
}

static esp_err_t send_json(httpd_req_t *req, const char *json, int status)
{
    httpd_resp_set_status(req, status == 200 ? "200 OK" : "400 Bad Request");
    httpd_resp_set_type(req, "application/json");
    return httpd_resp_send(req, json, strlen(json));
}

static esp_err_t send_json_obj(httpd_req_t *req, cJSON *obj)
{
    char *json = cJSON_PrintUnformatted(obj);
    esp_err_t err = send_json(req, json, 200);
    free(json);
    return err;
}

static esp_err_t serve_file(httpd_req_t *req, const char *path)
{
    const struct { const char *path; const char *data; size_t len; const char *type; } files[] = {
        {"/",          HTML_INDEX_HTML, HTML_INDEX_HTML_LEN, HTML_INDEX_HTML_TYPE},
        {"/index.html", HTML_INDEX_HTML, HTML_INDEX_HTML_LEN, HTML_INDEX_HTML_TYPE},
    };
    for (int i = 0; i < sizeof(files)/sizeof(files[0]); i++) {
        if (strcmp(path, files[i].path) == 0) {
            httpd_resp_set_type(req, files[i].type);
            httpd_resp_send(req, files[i].data, files[i].len);
            return ESP_OK;
        }
    }
    httpd_resp_set_status(req, "404 Not Found");
    httpd_resp_send(req, "Not Found", 9);
    return ESP_OK;
}

static esp_err_t handle_get_root(httpd_req_t *req)
{
    return serve_file(req, "/");
}

static esp_err_t handle_get_status(httpd_req_t *req)
{
    cJSON *resp = cJSON_CreateObject();
    wifi_state_t ws = wifi_manager_get_state();
    const char *state_str = "INIT";
    switch (ws) {
        case WIFI_STATE_INIT: state_str = "INIT"; break;
        case WIFI_STATE_AP: state_str = "AP"; break;
        case WIFI_STATE_CONNECTING: state_str = "CONNECTING"; break;
        case WIFI_STATE_STATION: state_str = "STATION"; break;
        case WIFI_STATE_FAILED: state_str = "FAILED"; break;
    }
    cJSON_AddStringToObject(resp, "wifi_state", state_str);
    cJSON_AddStringToObject(resp, "ip", wifi_manager_get_ip() ? wifi_manager_get_ip() : "");
    cJSON_AddNumberToObject(resp, "mqtt_clients", mqtt_broker_client_count());
    if (g_cfg) cJSON_AddBoolToObject(resp, "tasmota_connected",
        g_cfg->tasmota_ip[0] ? tasmota_discover(g_cfg->tasmota_ip, g_cfg->tasmota_port ? g_cfg->tasmota_port : 80) : false);
    return send_json_obj(req, resp);
}

static esp_err_t handle_broker_log(httpd_req_t *req)
{
    char *json = mqtt_broker_get_log_json();
    if (!json) return send_json(req, "[]", 200);
    esp_err_t err = send_json(req, json, 200);
    free(json);
    return err;
}

static esp_err_t handle_get_config(httpd_req_t *req)
{
    if (!g_cfg) return send_json(req, "{}", 200);
    cJSON *root = cJSON_CreateObject();
    cJSON_AddBoolToObject(root, "configured", g_cfg->configured);
    cJSON_AddStringToObject(root, "wifi_ssid", g_cfg->wifi_ssid);
    cJSON_AddStringToObject(root, "tasmota_ip", g_cfg->tasmota_ip);
    cJSON_AddNumberToObject(root, "tasmota_port", g_cfg->tasmota_port);
    cJSON_AddStringToObject(root, "tasmota_topic", g_cfg->tasmota_topic);
    cJSON_AddStringToObject(root, "region", g_cfg->region);
    cJSON_AddNumberToObject(root, "node_decimal", g_cfg->node_decimal);
    cJSON_AddNumberToObject(root, "gpio_rx", g_cfg->gpio_rx);
    cJSON_AddNumberToObject(root, "gpio_tx", g_cfg->gpio_tx);
    cJSON_AddNumberToObject(root, "send_interval", g_cfg->send_interval);
    if (!g_cfg->node_hash[0] && g_cfg->node_decimal > 0) {
        char buf[16];
        snprintf(buf, sizeof(buf), "!%x", (unsigned int)g_cfg->node_decimal);
        cJSON_AddStringToObject(root, "node_hash", buf);
    } else {
        cJSON_AddStringToObject(root, "node_hash", g_cfg->node_hash);
    }
    cJSON_AddStringToObject(root, "script", g_cfg->script);

    cJSON *maps = cJSON_AddArrayToObject(root, "mappings");
    for (int i = 0; i < g_cfg->mapping_count; i++) {
        cJSON *m = cJSON_CreateObject();
        cJSON_AddStringToObject(m, "var_name", g_cfg->mappings[i].var_name);
        cJSON_AddStringToObject(m, "lotse_key", g_cfg->mappings[i].lotse_key);
        cJSON_AddStringToObject(m, "unit", g_cfg->mappings[i].unit);
        cJSON_AddStringToObject(m, "label", g_cfg->mappings[i].label);
        cJSON_AddItemToArray(maps, m);
    }
    return send_json_obj(req, root);
}

static esp_err_t handle_post_config(httpd_req_t *req)
{
    char *body = NULL;
    size_t blen = 0;
    if (read_post_data(req, &body, &blen) != ESP_OK)
        return send_json(req, "{\"error\":\"no body\"}", 400);

    cJSON *root = cJSON_Parse(body);
    free(body);
    if (!root) return send_json(req, "{\"error\":\"invalid json\"}", 400);

    cJSON *v;
    v = cJSON_GetObjectItem(root, "wifi_ssid");
    if (v && v->valuestring) strncpy(g_cfg->wifi_ssid, v->valuestring, sizeof(g_cfg->wifi_ssid)-1);
    v = cJSON_GetObjectItem(root, "wifi_pass");
    if (v && v->valuestring) strncpy(g_cfg->wifi_pass, v->valuestring, sizeof(g_cfg->wifi_pass)-1);
    v = cJSON_GetObjectItem(root, "tasmota_ip");
    if (v && v->valuestring) strncpy(g_cfg->tasmota_ip, v->valuestring, sizeof(g_cfg->tasmota_ip)-1);
    v = cJSON_GetObjectItem(root, "region");
    if (v && v->valuestring) strncpy(g_cfg->region, v->valuestring, sizeof(g_cfg->region)-1);
    v = cJSON_GetObjectItem(root, "node_decimal");
    if (v && cJSON_IsNumber(v)) g_cfg->node_decimal = (uint32_t)v->valuedouble;
    v = cJSON_GetObjectItem(root, "configured");
    if (v) g_cfg->configured = cJSON_IsTrue(v);
    v = cJSON_GetObjectItem(root, "gpio_rx");
    if (v && cJSON_IsNumber(v)) g_cfg->gpio_rx = v->valueint;
    v = cJSON_GetObjectItem(root, "gpio_tx");
    if (v && cJSON_IsNumber(v)) g_cfg->gpio_tx = v->valueint;
    v = cJSON_GetObjectItem(root, "send_interval");
    if (v && cJSON_IsNumber(v)) g_cfg->send_interval = v->valueint;
    if (g_cfg->send_interval < 60) g_cfg->send_interval = 60;
    v = cJSON_GetObjectItem(root, "node_hash");
    if (v && v->valuestring) strncpy(g_cfg->node_hash, v->valuestring, sizeof(g_cfg->node_hash)-1);
    v = cJSON_GetObjectItem(root, "node_hash");
    if (v && v->valuestring) {
        strncpy(g_cfg->node_hash, v->valuestring, sizeof(g_cfg->node_hash)-1);
    } else if (g_cfg->node_decimal > 0) {
        // Derive hash from decimal: "!<hex>"
        snprintf(g_cfg->node_hash, sizeof(g_cfg->node_hash), "!%x",
                 (unsigned int)g_cfg->node_decimal);
    }
    v = cJSON_GetObjectItem(root, "script");
    if (v && v->valuestring) strncpy(g_cfg->script, v->valuestring, sizeof(g_cfg->script)-1);

    cJSON *maps = cJSON_GetObjectItem(root, "mappings");
    if (maps && cJSON_IsArray(maps)) {
        g_cfg->mapping_count = 0;
        int cnt = cJSON_GetArraySize(maps);
        for (int i = 0; i < cnt && g_cfg->mapping_count < MAX_MAPPINGS; i++) {
            cJSON *m = cJSON_GetArrayItem(maps, i);
            if (!m) continue;
            cJSON *v_name = cJSON_GetObjectItem(m, "var_name");
            cJSON *v_key = cJSON_GetObjectItem(m, "lotse_key");
            cJSON *v_unit = cJSON_GetObjectItem(m, "unit");
            cJSON *v_label = cJSON_GetObjectItem(m, "label");

            const char *lk = (v_key && v_key->valuestring) ? v_key->valuestring : "";
            // Skip duplicate non-empty lotse_key (keep first)
            if (lk[0]) {
                bool dup = false;
                for (int j = 0; j < g_cfg->mapping_count; j++) {
                    if (strcmp(g_cfg->mappings[j].lotse_key, lk) == 0) {
                        ESP_LOGW(TAG, "config: duplicate lotse_key '%s' dropped (first kept)", lk);
                        dup = true;
                        break;
                    }
                }
                if (dup) continue;
            }

            int idx = g_cfg->mapping_count;
            if (v_name && v_name->valuestring)
                strncpy(g_cfg->mappings[idx].var_name, v_name->valuestring, sizeof(g_cfg->mappings[idx].var_name)-1);
            strncpy(g_cfg->mappings[idx].lotse_key, lk, LOTSE_KEY_LEN-1);
            if (v_unit && v_unit->valuestring)
                strncpy(g_cfg->mappings[idx].unit, v_unit->valuestring, sizeof(g_cfg->mappings[idx].unit)-1);
            if (v_label && v_label->valuestring)
                strncpy(g_cfg->mappings[idx].label, v_label->valuestring, sizeof(g_cfg->mappings[idx].label)-1);
            g_cfg->mapping_count++;
        }
    }

    config_store_save(g_cfg);
    cJSON_Delete(root);
    return send_json(req, "{\"ok\":true}", 200);
}

static esp_err_t handle_script_parse(httpd_req_t *req)
{
    char *body = NULL;
    size_t blen = 0;
    if (read_post_data(req, &body, &blen) != ESP_OK)
        return send_json(req, "{\"error\":\"no body\"}", 400);

    cJSON *root = cJSON_Parse(body);
    free(body);
    if (!root) return send_json(req, "{\"error\":\"invalid json\"}", 400);

    cJSON *script = cJSON_GetObjectItem(root, "script");
    if (!script || !script->valuestring) {
        cJSON_Delete(root);
        return send_json(req, "{\"error\":\"no script\"}", 400);
    }

    var_mapping_t mappings[MAX_MAPPINGS];
    int count = transform_parse_script(script->valuestring, mappings, MAX_MAPPINGS);

    script_gpio_t gpio;
    transform_parse_gpio(script->valuestring, &gpio);

    cJSON *resp = cJSON_CreateObject();
    cJSON_AddNumberToObject(resp, "count", count);
    cJSON_AddNumberToObject(resp, "gpio_rx", gpio.gpio_rx);
    cJSON_AddNumberToObject(resp, "gpio_tx", gpio.gpio_tx);
    if (gpio.has_plus) {
        char type_str[2] = {gpio.meter_type, 0};
        cJSON_AddStringToObject(resp, "meter_type", type_str);
        cJSON_AddNumberToObject(resp, "flag", gpio.flag);
        cJSON_AddNumberToObject(resp, "baudrate", gpio.baudrate);
        cJSON_AddStringToObject(resp, "prefix", gpio.prefix);
    }
    cJSON *arr = cJSON_AddArrayToObject(resp, "mappings");
    for (int i = 0; i < count; i++) {
        cJSON *m = cJSON_CreateObject();
        cJSON_AddStringToObject(m, "var_name", mappings[i].var_name);
        cJSON_AddStringToObject(m, "lotse_key", mappings[i].lotse_key);
        cJSON_AddStringToObject(m, "unit", mappings[i].unit);
        cJSON_AddStringToObject(m, "label", mappings[i].label);
        cJSON_AddItemToArray(arr, m);
    }
    cJSON_Delete(root);
    return send_json_obj(req, resp);
}

static esp_err_t handle_tasmota_diff(httpd_req_t *req)
{
    if (!g_cfg || !g_cfg->tasmota_ip[0])
        return send_json(req, "{\"reachable\":false,\"differences\":[]}", 200);

    const char *ip = g_cfg->tasmota_ip;
    int port = g_cfg->tasmota_port ? g_cfg->tasmota_port : 80;

    cJSON *resp = cJSON_CreateObject();
    cJSON *diffs = cJSON_AddArrayToObject(resp, "differences");

    // Fetch current states from Tasmota
    char *script_resp = tasmota_fetch_sync(ip, port, "Script%201");
    char *host_resp = tasmota_fetch_sync(ip, port, "MqttHost");
    char *port_resp = tasmota_fetch_sync(ip, port, "MqttPort");

    bool reachable = (script_resp != NULL || host_resp != NULL);
    cJSON_AddBoolToObject(resp, "reachable", reachable);

    // Script status
    bool script_running = false;
    if (script_resp) {
        cJSON *sr = cJSON_Parse(script_resp);
        if (sr) {
            cJSON *sf = cJSON_GetObjectItem(sr, "Script");
            if (sf && sf->valuestring && strcmp(sf->valuestring, "ON") == 0)
                script_running = true;
            cJSON_Delete(sr);
        }
        free(script_resp);
    }

    {
        cJSON *d = cJSON_CreateObject();
        cJSON_AddStringToObject(d, "item", "script");
        cJSON_AddStringToObject(d, "label", "SMI script");
        cJSON_AddStringToObject(d, "current", script_running ? "loaded and running" : "not running");
        char exp_script[64];
        if (g_cfg->script[0])
            snprintf(exp_script, sizeof(exp_script), "ready to push (%d chars)", (int)strlen(g_cfg->script));
        else
            snprintf(exp_script, sizeof(exp_script), "none stored");
        cJSON_AddStringToObject(d, "expected", exp_script);
        cJSON_AddBoolToObject(d, "needs_update", !script_running && g_cfg->script[0]);
        cJSON_AddItemToArray(diffs, d);
    }

    // MQTT host
    const char *my_ip = wifi_manager_get_ip();
    char cur_host[64] = "(unknown)";
    if (host_resp) {
        cJSON *hr = cJSON_Parse(host_resp);
        if (hr) {
            cJSON *hv = cJSON_GetObjectItem(hr, "MqttHost");
            if (hv && hv->valuestring) strncpy(cur_host, hv->valuestring, sizeof(cur_host)-1);
            cJSON_Delete(hr);
        }
        free(host_resp);
    }

    {
        cJSON *d = cJSON_CreateObject();
        cJSON_AddStringToObject(d, "item", "mqtt_host");
        cJSON_AddStringToObject(d, "label", "MQTT host");
        cJSON_AddStringToObject(d, "current", cur_host);
        cJSON_AddStringToObject(d, "expected", my_ip ? my_ip : "(no IP)");
        cJSON_AddBoolToObject(d, "needs_update", my_ip && strcmp(cur_host, my_ip) != 0);
        cJSON_AddItemToArray(diffs, d);
    }

    // MQTT port
    int cur_port = 0;
    if (port_resp) {
        cJSON *pr = cJSON_Parse(port_resp);
        if (pr) {
            cJSON *pv = cJSON_GetObjectItem(pr, "MqttPort");
            if (pv) cur_port = pv->valueint;
            cJSON_Delete(pr);
        }
        free(port_resp);
    }

    {
        char cur_port_str[16], exp_port_str[16];
        snprintf(cur_port_str, sizeof(cur_port_str), "%d", cur_port);
        snprintf(exp_port_str, sizeof(exp_port_str), "%d", MQTT_BROKER_PORT);

        cJSON *d = cJSON_CreateObject();
        cJSON_AddStringToObject(d, "item", "mqtt_port");
        cJSON_AddStringToObject(d, "label", "MQTT port");
        cJSON_AddStringToObject(d, "current", cur_port_str);
        cJSON_AddStringToObject(d, "expected", exp_port_str);
        cJSON_AddBoolToObject(d, "needs_update", cur_port != MQTT_BROKER_PORT);
        cJSON_AddItemToArray(diffs, d);
    }

    return send_json_obj(req, resp);
}

static esp_err_t handle_tasmota_configure(httpd_req_t *req)
{
    char *body = NULL;
    size_t blen = 0;
    if (read_post_data(req, &body, &blen) != ESP_OK)
        return send_json(req, "{\"error\":\"no body\"}", 400);

    cJSON *root = cJSON_Parse(body);
    free(body);
    if (!root) return send_json(req, "{\"error\":\"invalid json\"}", 400);

    cJSON *ip = cJSON_GetObjectItem(root, "tasmota_ip");
    cJSON *script = cJSON_GetObjectItem(root, "script");
    cJSON *mappings = cJSON_GetObjectItem(root, "mappings");
    cJSON *region = cJSON_GetObjectItem(root, "region");
    cJSON *node_dec = cJSON_GetObjectItem(root, "node_decimal");
    cJSON *gpio_rx = cJSON_GetObjectItem(root, "gpio_rx");
    cJSON *gpio_tx = cJSON_GetObjectItem(root, "gpio_tx");
    cJSON *actions = cJSON_GetObjectItem(root, "actions");

    if (!ip || !ip->valuestring || !script || !script->valuestring) {
        cJSON_Delete(root);
        return send_json(req, "{\"error\":\"missing fields\"}", 400);
    }

    int rx = gpio_rx && cJSON_IsNumber(gpio_rx) ? gpio_rx->valueint : g_cfg->gpio_rx;
    int tx = gpio_tx && cJSON_IsNumber(gpio_tx) ? gpio_tx->valueint : g_cfg->gpio_tx;
    if (rx <= 0) rx = 3;
    if (tx <= 0) tx = 1;

    // Parse actions — if absent, do everything (backward compatible)
    bool do_script = true;
    bool do_mqtt = true;
    if (actions && cJSON_IsArray(actions)) {
        do_script = false;
        do_mqtt = false;
        int acnt = cJSON_GetArraySize(actions);
        for (int i = 0; i < acnt; i++) {
            cJSON *a = cJSON_GetArrayItem(actions, i);
            if (a && a->valuestring) {
                if (strcmp(a->valuestring, "script") == 0) do_script = true;
                if (strcmp(a->valuestring, "mqtt") == 0) do_mqtt = true;
            }
        }
    }

    // Save to config (always)
    strncpy(g_cfg->tasmota_ip, ip->valuestring, sizeof(g_cfg->tasmota_ip)-1);
    g_cfg->gpio_rx = rx;
    g_cfg->gpio_tx = tx;
    g_cfg->tasmota_port = 80;
    if (region && region->valuestring)
        strncpy(g_cfg->region, region->valuestring, sizeof(g_cfg->region)-1);
    if (node_dec && cJSON_IsNumber(node_dec)) g_cfg->node_decimal = (uint32_t)node_dec->valuedouble;

    g_cfg->mapping_count = 0;
    if (mappings && cJSON_IsArray(mappings)) {
        int cnt = cJSON_GetArraySize(mappings);
        for (int i = 0; i < cnt && g_cfg->mapping_count < MAX_MAPPINGS; i++) {
            cJSON *m = cJSON_GetArrayItem(mappings, i);
            if (!m) continue;
            cJSON *v_name = cJSON_GetObjectItem(m, "var_name");
            cJSON *v_key = cJSON_GetObjectItem(m, "lotse_key");
            cJSON *v_unit = cJSON_GetObjectItem(m, "unit");
            cJSON *v_label = cJSON_GetObjectItem(m, "label");

            const char *lk = (v_key && v_key->valuestring) ? v_key->valuestring : "";
            // Skip duplicate non-empty lotse_key (keep first)
            if (lk[0]) {
                bool dup = false;
                for (int j = 0; j < g_cfg->mapping_count; j++) {
                    if (strcmp(g_cfg->mappings[j].lotse_key, lk) == 0) {
                        ESP_LOGW(TAG, "tasmota_configure: duplicate lotse_key '%s' dropped", lk);
                        dup = true;
                        break;
                    }
                }
                if (dup) continue;
            }

            int idx = g_cfg->mapping_count;
            if (v_name && v_name->valuestring)
                strncpy(g_cfg->mappings[idx].var_name, v_name->valuestring, sizeof(g_cfg->mappings[idx].var_name)-1);
            strncpy(g_cfg->mappings[idx].lotse_key, lk, LOTSE_KEY_LEN-1);
            if (v_unit && v_unit->valuestring)
                strncpy(g_cfg->mappings[idx].unit, v_unit->valuestring, sizeof(g_cfg->mappings[idx].unit)-1);
            if (v_label && v_label->valuestring)
                strncpy(g_cfg->mappings[idx].label, v_label->valuestring, sizeof(g_cfg->mappings[idx].label)-1);
            g_cfg->mapping_count++;
        }
    }

    // Inject GPIO lines
    char *injected = transform_inject_gpio(script->valuestring, rx, tx);
    if (injected) {
        strncpy(g_cfg->script, injected, sizeof(g_cfg->script)-1);
        free(injected);
    } else {
        strncpy(g_cfg->script, script->valuestring, sizeof(g_cfg->script)-1);
    }
    config_store_save(g_cfg);

    const char *my_ip = wifi_manager_get_ip();
    bool success = true;
    bool verified = false;
    bool match = false;
    int actions_taken = 0;

    if (my_ip) {
        if (do_script) {
            tasmota_send_command(g_cfg->tasmota_ip, g_cfg->tasmota_port, "Template%200", NULL);
            vTaskDelay(pdMS_TO_TICKS(200));
            tasmota_send_command(g_cfg->tasmota_ip, g_cfg->tasmota_port, "Module%200", NULL);
            vTaskDelay(pdMS_TO_TICKS(200));
            tasmota_send_command(g_cfg->tasmota_ip, g_cfg->tasmota_port, "SetOption84%201", NULL);
            vTaskDelay(pdMS_TO_TICKS(200));

            esp_err_t err = tasmota_push_script(g_cfg->tasmota_ip, g_cfg->tasmota_port,
                                                 g_cfg->script, NULL);
            if (err != ESP_OK) success = false;
            vTaskDelay(pdMS_TO_TICKS(500));

            char *vr = tasmota_fetch_sync(g_cfg->tasmota_ip, g_cfg->tasmota_port, "Script%201");
            if (vr) {
                cJSON *sr = cJSON_Parse(vr);
                if (sr) {
                    cJSON *sf = cJSON_GetObjectItem(sr, "Script");
                    if (sf && sf->valuestring) {
                        verified = true;
                        match = (strcmp(sf->valuestring, "ON") == 0);
                    }
                    cJSON_Delete(sr);
                }
                free(vr);
            }
            actions_taken++;
        }

        if (do_mqtt) {
            char cmd[128];
            snprintf(cmd, sizeof(cmd), "MQTTHost%%20%s", my_ip);
            tasmota_send_command(g_cfg->tasmota_ip, g_cfg->tasmota_port, cmd, NULL);
            vTaskDelay(pdMS_TO_TICKS(200));
            snprintf(cmd, sizeof(cmd), "MQTTPort%%201883");
            tasmota_send_command(g_cfg->tasmota_ip, g_cfg->tasmota_port, cmd, NULL);
            vTaskDelay(pdMS_TO_TICKS(200));
            tasmota_send_command(g_cfg->tasmota_ip, g_cfg->tasmota_port, "MqttUser%%20", NULL);
            vTaskDelay(pdMS_TO_TICKS(200));
            tasmota_send_command(g_cfg->tasmota_ip, g_cfg->tasmota_port, "MqttPassword%%20", NULL);
            vTaskDelay(pdMS_TO_TICKS(200));
            tasmota_send_command(g_cfg->tasmota_ip, g_cfg->tasmota_port, "MqttLwtTopic%%200", NULL);
            vTaskDelay(pdMS_TO_TICKS(200));
            tasmota_send_command(g_cfg->tasmota_ip, g_cfg->tasmota_port, "MqttLwtOffline%%200", NULL);
            vTaskDelay(pdMS_TO_TICKS(200));
            tasmota_send_command(g_cfg->tasmota_ip, g_cfg->tasmota_port, "MqttLwtOnline%%200", NULL);
            vTaskDelay(pdMS_TO_TICKS(200));
            tasmota_send_command(g_cfg->tasmota_ip, g_cfg->tasmota_port, "SetOption19%%201", NULL);
            vTaskDelay(pdMS_TO_TICKS(200));
            actions_taken++;
        }

        if (actions_taken > 0) {
            tasmota_send_command(g_cfg->tasmota_ip, g_cfg->tasmota_port, "Restart%%201", NULL);
        }
    }

    cJSON_Delete(root);

    cJSON *resp = cJSON_CreateObject();
    cJSON_AddBoolToObject(resp, "success", success);
    cJSON_AddBoolToObject(resp, "verified", verified);
    cJSON_AddBoolToObject(resp, "match", match);

    const char *msg;
    if (actions_taken == 0) {
        msg = "Nothing to send — Tasmota already up to date";
    } else if (do_script && do_mqtt && verified && match) {
        msg = "Script + MQTT sent, Tasmota rebooting";
    } else if (do_script && do_mqtt) {
        msg = "Script push attempted — check Tasmota console";
    } else if (do_script && verified && match) {
        msg = "Script sent, Tasmota rebooting";
    } else if (do_mqtt) {
        msg = "MQTT config sent, Tasmota rebooting";
    } else {
        msg = "Sent to Tasmota";
    }
    cJSON_AddStringToObject(resp, "message", msg);
    return send_json_obj(req, resp);
}

static esp_err_t handle_tasmota_discover(httpd_req_t *req)
{
    char *body = NULL;
    size_t blen = 0;
    if (read_post_data(req, &body, &blen) != ESP_OK)
        return send_json(req, "{\"error\":\"no body\"}", 400);

    cJSON *root = cJSON_Parse(body);
    free(body);
    if (!root) return send_json(req, "{\"error\":\"invalid json\"}", 400);

    cJSON *ip = cJSON_GetObjectItem(root, "ip");
    bool found = ip && ip->valuestring && tasmota_discover(ip->valuestring, 80);
    cJSON_Delete(root);

    cJSON *resp = cJSON_CreateObject();
    cJSON_AddBoolToObject(resp, "success", found);
    return send_json_obj(req, resp);
}

static esp_err_t handle_tasmota_verify(httpd_req_t *req)
{
    if (!g_cfg || !g_cfg->tasmota_ip[0])
        return send_json(req, "{\"error\":\"no tasmota configured\"}", 400);

    cJSON *resp = cJSON_CreateObject();

    // On Tasmota 13.x "Script" no longer returns content, only status.
    // "Script 1" returns {"Script":"ON","StopOnError":"ON","Free":7948}
    char *response = tasmota_fetch_sync(g_cfg->tasmota_ip,
                                         g_cfg->tasmota_port ? g_cfg->tasmota_port : 80,
                                         "Script%201");

    if (!response) {
        cJSON_AddBoolToObject(resp, "reachable", false);
        return send_json_obj(req, resp);
    }

    cJSON *sr = cJSON_Parse(response);
    if (!sr) {
        cJSON_AddBoolToObject(resp, "reachable", false);
        free(response);
        return send_json_obj(req, resp);
    }

    cJSON *sf = cJSON_GetObjectItem(sr, "Script");
    bool running = sf && sf->valuestring && strcmp(sf->valuestring, "ON") == 0;

    cJSON_AddBoolToObject(resp, "reachable", true);
    cJSON_AddBoolToObject(resp, "script_running", running);
    // On Tasmota 13.x we cannot read back the script content for comparison
    // Assume match if script is running (it was successfully loaded)
    cJSON_AddBoolToObject(resp, "match", running);

    cJSON_Delete(sr);
    free(response);
    return send_json_obj(req, resp);
}

static esp_err_t handle_wifi_connect(httpd_req_t *req)
{
    wifi_manager_start(g_cfg->wifi_ssid, g_cfg->wifi_pass);
    return send_json(req, "{\"ok\":true}", 200);
}

#define JSON_ERROR "{\"error\":\"scan failed\"}"
#define JSON_SCANNING "{\"scanning\":true}"

static esp_err_t handle_wifi_scan(httpd_req_t *req)
{
    ESP_LOGI(TAG, "handle_wifi_scan called");
    esp_err_t err = wifi_manager_scan_start();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "wifi_manager_scan_start failed: %s", esp_err_to_name(err));
        return send_json(req, "{\"error\":\"scan failed\"}", 500);
    }
    return send_json(req, "{\"scanning\":true}", 200);
}


static esp_err_t handle_wifi_networks(httpd_req_t *req)
{
    wifi_scan_result_t results[MAX_SCAN_RESULTS];
    int count = wifi_manager_scan_get_results(results, MAX_SCAN_RESULTS);
    
    ESP_LOGI(TAG, "handle_wifi_networks: count = %d", count);
    
    cJSON *root = cJSON_CreateObject();
    cJSON_AddNumberToObject(root, "count", count);
    cJSON *arr = cJSON_AddArrayToObject(root, "networks");
    
    for (int i = 0; i < count; i++) {
        cJSON *n = cJSON_CreateObject();
        ESP_LOGI(TAG, "Adding network: %s, rssi=%d, auth=%d", results[i].ssid, results[i].rssi, results[i].authmode);
        cJSON_AddStringToObject(n, "ssid", results[i].ssid);
        cJSON_AddNumberToObject(n, "rssi", results[i].rssi);
        cJSON_AddNumberToObject(n, "auth", results[i].authmode);
        cJSON_AddItemToArray(arr, n);
    }
    
    return send_json_obj(req, root);
}

static esp_err_t handle_mesh_discover(httpd_req_t *req)
{
    (void)req;
    char *json = mqtt_broker_get_log_json();
    cJSON *log = cJSON_Parse(json ? json : "[]");
    free(json);

    cJSON *result = cJSON_CreateObject();
    cJSON *nodes = cJSON_AddArrayToObject(result, "nodes");

    if (log) {
        int cnt = cJSON_GetArraySize(log);
        for (int i = 0; i < cnt; i++) {
            cJSON *entry = cJSON_GetArrayItem(log, i);
            if (!entry) continue;
            cJSON *t = cJSON_GetObjectItem(entry, "topic");
            if (!t || !t->valuestring) continue;
            const char *topic = t->valuestring;
            // Match msh/{region}/2/{ch}/mqtt/!xxxxxxxx
            const char *hash = strstr(topic, "/mqtt/!");
            if (!hash) continue;
            hash += 6; // skip "/mqtt/"
            // Check if hash looks valid (! followed by 8 hex chars)
            if (strlen(hash) < 9) continue;
            // Check for duplicate
            bool dup = false;
            int ncnt = cJSON_GetArraySize(nodes);
            for (int j = 0; j < ncnt; j++) {
                cJSON *n = cJSON_GetArrayItem(nodes, j);
                cJSON *h = cJSON_GetObjectItem(n, "hash");
                if (h && h->valuestring && strcmp(h->valuestring, hash) == 0)
                    { dup = true; break; }
            }
            if (dup) continue;
            cJSON *n = cJSON_CreateObject();
            cJSON_AddStringToObject(n, "hash", hash);
            // Extract region from topic
            const char *rstart = topic + 4; // skip "msh/"
            const char *rend = strchr(rstart, '/');
            char region[16] = {0};
            if (rend && (size_t)(rend - rstart) < sizeof(region)) {
                memcpy(region, rstart, rend - rstart);
                cJSON_AddStringToObject(n, "region", region);
            }
            cJSON_AddItemToArray(nodes, n);
        }
        cJSON_Delete(log);
    }
    esp_err_t err = send_json_obj(req, result);
    cJSON_Delete(result);
    return err;
}

esp_err_t web_server_start(hub_config_t *cfg)
{
    g_cfg = cfg;

    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.max_uri_handlers = 16;
    config.stack_size = 8192;
    config.lru_purge_enable = true;

    esp_err_t err = httpd_start(&s_server, &config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to start HTTP server: %s", esp_err_to_name(err));
        return err;
    }

    httpd_uri_t uris[] = {
        {.uri = "/",             .method = HTTP_GET,    .handler = handle_get_root},
        {.uri = "/index.html",   .method = HTTP_GET,    .handler = handle_static_file},
        {.uri = "/api/status",   .method = HTTP_GET,    .handler = handle_get_status},
        {.uri = "/api/broker/log", .method = HTTP_GET,  .handler = handle_broker_log},
        {.uri = "/api/config",   .method = HTTP_GET,    .handler = handle_get_config},
        {.uri = "/api/config",   .method = HTTP_POST,   .handler = handle_post_config},
        {.uri = "/api/script/parse", .method = HTTP_POST, .handler = handle_script_parse},
        {.uri = "/api/tasmota/configure", .method = HTTP_POST, .handler = handle_tasmota_configure},
        {.uri = "/api/tasmota/diff", .method = HTTP_GET,  .handler = handle_tasmota_diff},
        {.uri = "/api/tasmota/discover", .method = HTTP_POST, .handler = handle_tasmota_discover},
        {.uri = "/api/tasmota/verify", .method = HTTP_GET,  .handler = handle_tasmota_verify},
        {.uri = "/api/wifi/connect", .method = HTTP_POST, .handler = handle_wifi_connect},
        {.uri = "/api/wifi/scan",    .method = HTTP_GET,  .handler = handle_wifi_scan},
        {.uri = "/api/wifi/networks",.method = HTTP_GET,  .handler = handle_wifi_networks},
        {.uri = "/api/mesh/discover",.method = HTTP_GET,  .handler = handle_mesh_discover},
    };

    for (int i = 0; i < sizeof(uris)/sizeof(uris[0]); i++) {
        httpd_register_uri_handler(s_server, &uris[i]);
    }

    ESP_LOGI(TAG, "Web server started on port %d", config.server_port);
    return ESP_OK;
}

static esp_err_t handle_static_file(httpd_req_t *req)
{
    return serve_file(req, req->uri);
}
