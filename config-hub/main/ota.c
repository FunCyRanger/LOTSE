#include <string.h>
#include <stdlib.h>
#include <time.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_ota_ops.h"
#include "esp_https_ota.h"
#include "esp_http_client.h"
#include "cJSON.h"
#include "nvs_flash.h"
#include "ota.h"
#include "wifi_manager.h"

static const char *TAG = "ota";

#define OTA_REPO "FunCyRanger/LOTSE"
#define OTA_NVS_NS "lotse_cfg"
#define OTA_NVS_VER "ota_version"

static char s_ota_status[48] = "idle";
static char s_current_ver[32] = "";
static volatile bool s_check_pending = false;

static void set_status(const char *s)
{
    strncpy(s_ota_status, s, sizeof(s_ota_status) - 1);
    s_ota_status[sizeof(s_ota_status) - 1] = 0;
    ESP_LOGI(TAG, "status: %s", s);
}

const char *ota_get_current_version(void)
{
    return s_current_ver;
}

const char *ota_get_status(void)
{
    return s_ota_status;
}

esp_err_t ota_request_check(void)
{
    if (strcmp(s_ota_status, "downloading") == 0)
        return ESP_ERR_INVALID_STATE;
    set_status("checking");
    s_check_pending = true;
    return ESP_OK;
}

static void load_version_from_nvs(void)
{
    nvs_handle_t nvs;
    if (nvs_open(OTA_NVS_NS, NVS_READONLY, &nvs) == ESP_OK) {
        size_t len = sizeof(s_current_ver);
        if (nvs_get_str(nvs, OTA_NVS_VER, s_current_ver, &len) != ESP_OK)
            s_current_ver[0] = 0;
        nvs_close(nvs);
    }
}

static void save_version_to_nvs(const char *ver)
{
    nvs_handle_t nvs;
    if (nvs_open(OTA_NVS_NS, NVS_READWRITE, &nvs) == ESP_OK) {
        nvs_set_str(nvs, OTA_NVS_VER, ver);
        nvs_commit(nvs);
        nvs_close(nvs);
    }
}

static esp_err_t fetch_latest_version(char *version_buf, size_t buf_size)
{
    char url[128];
    snprintf(url, sizeof(url), "https://api.github.com/repos/" OTA_REPO "/releases/latest");

    esp_http_client_config_t cfg = {
        .url = url,
        .user_agent = "LOTSE-Config-Hub/1.0",
        .timeout_ms = 10000,
    };

    esp_http_client_handle_t client = esp_http_client_init(&cfg);
    if (!client) return ESP_FAIL;

    esp_err_t err = esp_http_client_open(client, 0);
    if (err != ESP_OK) {
        esp_http_client_cleanup(client);
        return err;
    }

    int content_length = esp_http_client_fetch_headers(client);
    if (content_length <= 0) {
        esp_http_client_close(client);
        esp_http_client_cleanup(client);
        return ESP_FAIL;
    }

    char *buf = malloc(content_length + 1);
    if (!buf) {
        esp_http_client_close(client);
        esp_http_client_cleanup(client);
        return ESP_ERR_NO_MEM;
    }

    int total = 0;
    while (total < content_length) {
        int r = esp_http_client_read(client, buf + total, content_length - total);
        if (r <= 0) break;
        total += r;
    }
    buf[total] = 0;
    esp_http_client_close(client);
    esp_http_client_cleanup(client);

    if (total <= 0) {
        free(buf);
        return ESP_FAIL;
    }

    cJSON *root = cJSON_Parse(buf);
    free(buf);
    if (!root) return ESP_FAIL;

    cJSON *tag = cJSON_GetObjectItem(root, "tag_name");
    if (!tag || !tag->valuestring) {
        cJSON_Delete(root);
        return ESP_FAIL;
    }

    strncpy(version_buf, tag->valuestring, buf_size - 1);
    version_buf[buf_size - 1] = 0;
    cJSON_Delete(root);
    return ESP_OK;
}

static void ota_perform_update(const char *latest_version)
{
    char download_url[256];
    snprintf(download_url, sizeof(download_url),
             "https://github.com/" OTA_REPO "/releases/latest/download/lotse_config_hub.bin");

    ESP_LOGI(TAG, "downloading %s", download_url);
    set_status("downloading");

    esp_http_client_config_t ota_cfg = {
        .url = download_url,
        .user_agent = "LOTSE-Config-Hub/1.0",
        .timeout_ms = 120000,
    };

    esp_https_ota_config_t ota_config = {
        .http_config = &ota_cfg,
    };

    esp_err_t err = esp_https_ota(&ota_config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "OTA failed: %s", esp_err_to_name(err));
        set_status("error:download");
        return;
    }

    save_version_to_nvs(latest_version);
    ESP_LOGI(TAG, "OTA done, rebooting to %s", latest_version);
    set_status("rebooting");
    vTaskDelay(pdMS_TO_TICKS(500));
    esp_restart();
}

static bool sntp_is_synced(void)
{
    time_t now = time(NULL);
    struct tm ti;
    localtime_r(&now, &ti);
    return ti.tm_year >= (2025 - 1900);
}

void ota_check_and_update(void)
{
    if (wifi_manager_get_state() != WIFI_STATE_STATION) {
        set_status("no_wifi");
        return;
    }

    set_status("checking");

    int sntp_waited = 0;
    while (!sntp_is_synced() && sntp_waited < 60) {
        vTaskDelay(pdMS_TO_TICKS(1000));
        sntp_waited++;
    }
    if (!sntp_is_synced()) {
        ESP_LOGW(TAG, "SNTP not synced after 60s, proceeding anyway");
    }

    char latest_ver[32] = "";
    esp_err_t err = fetch_latest_version(latest_ver, sizeof(latest_ver));
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "version check failed");
        set_status("error:check");
        return;
    }

    ESP_LOGI(TAG, "current=%s latest=%s", s_current_ver, latest_ver);

    if (strcmp(latest_ver, s_current_ver) == 0) {
        set_status("up_to_date");
        return;
    }

    ota_perform_update(latest_ver);
}

static void ota_task(void *arg)
{
    // Wait for WiFi station connection
    int waited = 0;
    while (wifi_manager_get_state() != WIFI_STATE_STATION && waited < 120) {
        vTaskDelay(pdMS_TO_TICKS(1000));
        waited++;
    }

    if (wifi_manager_get_state() != WIFI_STATE_STATION) {
        ESP_LOGW(TAG, "WiFi not available, OTA disabled");
        set_status("no_wifi");
        vTaskDelete(NULL);
        return;
    }

    int tick = 0;
    while (1) {
        if (tick % (24 * 60) == 0 || s_check_pending) {
            if (s_check_pending) {
                s_check_pending = false;
                tick = 0;
            }
            ota_check_and_update();
        }
        tick = (tick + 1) % (24 * 60);
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}

esp_err_t ota_init(void)
{
    load_version_from_nvs();

    // If no NVS version stored yet, use the compile-time built version
    if (!s_current_ver[0]) {
        strncpy(s_current_ver, LOTSE_VERSION, sizeof(s_current_ver) - 1);
        s_current_ver[sizeof(s_current_ver) - 1] = 0;
        save_version_to_nvs(s_current_ver);
    }

    // Mark app valid (cancel rollback if we booted from an OTA update)
    const esp_partition_t *running = esp_ota_get_running_partition();
    esp_ota_img_states_t state;
    if (esp_ota_get_state_partition(running, &state) == ESP_OK
        && state == ESP_OTA_IMG_PENDING_VERIFY) {
        ESP_LOGI(TAG, "confirming OTA boot");
        esp_ota_mark_app_valid_cancel_rollback();
    }

    xTaskCreate(ota_task, "ota_check", 8192, NULL, 2, NULL);
    return ESP_OK;
}
