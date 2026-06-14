#include <string.h>
#include "esp_log.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "cJSON.h"
#include "config_store.h"

static const char *TAG = "config_store";
static const char *NVS_NS = "lotse_cfg";
static const char *NVS_KEY = "config_json";

static char *config_to_json(const hub_config_t *cfg)
{
    cJSON *root = cJSON_CreateObject();
    cJSON_AddBoolToObject(root, "configured", cfg->configured);
    cJSON_AddStringToObject(root, "wifi_ssid", cfg->wifi_ssid);
    cJSON_AddStringToObject(root, "wifi_pass", cfg->wifi_pass);
    cJSON_AddStringToObject(root, "tasmota_ip", cfg->tasmota_ip);
    cJSON_AddNumberToObject(root, "tasmota_port", cfg->tasmota_port);
    cJSON_AddStringToObject(root, "tasmota_topic", cfg->tasmota_topic);
    cJSON_AddStringToObject(root, "region", cfg->region);
    cJSON_AddNumberToObject(root, "node_decimal", cfg->node_decimal);
    cJSON_AddStringToObject(root, "script", cfg->script);

    cJSON *maps = cJSON_AddArrayToObject(root, "mappings");
    for (int i = 0; i < cfg->mapping_count; i++) {
        cJSON *m = cJSON_CreateObject();
        cJSON_AddStringToObject(m, "var", cfg->mappings[i].var_name);
        cJSON_AddStringToObject(m, "key", cfg->mappings[i].lotse_key);
        cJSON_AddStringToObject(m, "unit", cfg->mappings[i].unit);
        cJSON_AddStringToObject(m, "label", cfg->mappings[i].label);
        cJSON_AddItemToArray(maps, m);
    }
    cJSON_AddNumberToObject(root, "mapping_count", cfg->mapping_count);
    cJSON_AddNumberToObject(root, "gpio_rx", cfg->gpio_rx);
    cJSON_AddNumberToObject(root, "gpio_tx", cfg->gpio_tx);
    cJSON_AddNumberToObject(root, "send_interval", cfg->send_interval);
    cJSON_AddStringToObject(root, "node_hash", cfg->node_hash);

    char *json = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    return json;
}

static int json_to_config(const char *json, hub_config_t *cfg)
{
    memset(cfg, 0, sizeof(*cfg));
    cJSON *root = cJSON_Parse(json);
    if (!root) return -1;

    cJSON *v;
    v = cJSON_GetObjectItem(root, "configured");
    if (v) cfg->configured = cJSON_IsTrue(v);

    v = cJSON_GetObjectItem(root, "wifi_ssid");
    if (v && v->valuestring) strncpy(cfg->wifi_ssid, v->valuestring, sizeof(cfg->wifi_ssid)-1);

    v = cJSON_GetObjectItem(root, "wifi_pass");
    if (v && v->valuestring) strncpy(cfg->wifi_pass, v->valuestring, sizeof(cfg->wifi_pass)-1);

    v = cJSON_GetObjectItem(root, "tasmota_ip");
    if (v && v->valuestring) strncpy(cfg->tasmota_ip, v->valuestring, sizeof(cfg->tasmota_ip)-1);

    v = cJSON_GetObjectItem(root, "tasmota_port");
    if (v) cfg->tasmota_port = v->valueint;

    v = cJSON_GetObjectItem(root, "tasmota_topic");
    if (v && v->valuestring) strncpy(cfg->tasmota_topic, v->valuestring, sizeof(cfg->tasmota_topic)-1);

    v = cJSON_GetObjectItem(root, "region");
    if (v && v->valuestring) {
        strncpy(cfg->region, v->valuestring, sizeof(cfg->region)-1);
    } else {
        // Default region if none configured
        strncpy(cfg->region, "EU_868", sizeof(cfg->region)-1);
    }

    v = cJSON_GetObjectItem(root, "node_decimal");
    if (v && cJSON_IsNumber(v)) cfg->node_decimal = (uint32_t)v->valuedouble;

    v = cJSON_GetObjectItem(root, "script");
    if (v && v->valuestring) strncpy(cfg->script, v->valuestring, sizeof(cfg->script)-1);

    v = cJSON_GetObjectItem(root, "gpio_rx");
    if (v && cJSON_IsNumber(v)) cfg->gpio_rx = v->valueint;
    v = cJSON_GetObjectItem(root, "gpio_tx");
    if (v && cJSON_IsNumber(v)) cfg->gpio_tx = v->valueint;
    v = cJSON_GetObjectItem(root, "send_interval");
    if (v && cJSON_IsNumber(v)) cfg->send_interval = v->valueint;
    if (cfg->send_interval < 60) cfg->send_interval = 60;

    v = cJSON_GetObjectItem(root, "node_hash");
    if (v && v->valuestring) strncpy(cfg->node_hash, v->valuestring, sizeof(cfg->node_hash)-1);

    cJSON *maps = cJSON_GetObjectItem(root, "mappings");
    if (maps) {
        int cnt = cJSON_GetArraySize(maps);
        for (int i = 0; i < cnt && i < MAX_MAPPINGS; i++) {
            cJSON *m = cJSON_GetArrayItem(maps, i);
            if (!m) continue;
            v = cJSON_GetObjectItem(m, "var");
            if (v && v->valuestring) strncpy(cfg->mappings[i].var_name, v->valuestring, sizeof(cfg->mappings[i].var_name)-1);
            v = cJSON_GetObjectItem(m, "key");
            if (v && v->valuestring) strncpy(cfg->mappings[i].lotse_key, v->valuestring, sizeof(cfg->mappings[i].lotse_key)-1);
            v = cJSON_GetObjectItem(m, "unit");
            if (v && v->valuestring) strncpy(cfg->mappings[i].unit, v->valuestring, sizeof(cfg->mappings[i].unit)-1);
            v = cJSON_GetObjectItem(m, "label");
            if (v && v->valuestring) strncpy(cfg->mappings[i].label, v->valuestring, sizeof(cfg->mappings[i].label)-1);
            cfg->mapping_count = i + 1;
        }
    }

    cJSON_Delete(root);
    return 0;
}

esp_err_t config_store_init(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    return err;
}

esp_err_t config_store_load(hub_config_t *cfg)
{
    nvs_handle_t handle;
    esp_err_t err = nvs_open(NVS_NS, NVS_READONLY, &handle);
    if (err != ESP_OK) {
        memset(cfg, 0, sizeof(*cfg));
        return err;
    }

    size_t len = 0;
    err = nvs_get_blob(handle, NVS_KEY, NULL, &len);
    if (err != ESP_OK || len == 0) {
        nvs_close(handle);
        memset(cfg, 0, sizeof(*cfg));
        return ESP_ERR_NVS_NOT_FOUND;
    }

    char *buf = malloc(len + 1);
    if (!buf) { nvs_close(handle); return ESP_ERR_NO_MEM; }

    err = nvs_get_blob(handle, NVS_KEY, buf, &len);
    nvs_close(handle);
    if (err != ESP_OK) { free(buf); memset(cfg, 0, sizeof(*cfg)); return err; }
    buf[len] = 0;

    int rc = json_to_config(buf, cfg);
    free(buf);
    return rc == 0 ? ESP_OK : ESP_FAIL;
}

esp_err_t config_store_save(const hub_config_t *cfg)
{
    char *json = config_to_json(cfg);
    if (!json) return ESP_ERR_NO_MEM;

    nvs_handle_t handle;
    esp_err_t err = nvs_open(NVS_NS, NVS_READWRITE, &handle);
    if (err != ESP_OK) { free(json); return err; }

    err = nvs_set_blob(handle, NVS_KEY, json, strlen(json));
    if (err == ESP_OK) err = nvs_commit(handle);
    nvs_close(handle);
    free(json);
    return err;
}

esp_err_t config_store_reset(void)
{
    nvs_handle_t handle;
    esp_err_t err = nvs_open(NVS_NS, NVS_READWRITE, &handle);
    if (err != ESP_OK) return err;
    err = nvs_erase_all(handle);
    if (err == ESP_OK) err = nvs_commit(handle);
    nvs_close(handle);
    return err;
}
