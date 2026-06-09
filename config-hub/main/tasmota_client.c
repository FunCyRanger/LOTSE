#include <string.h>
#include <stdlib.h>
#include "esp_log.h"
#include "esp_http_client.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "cJSON.h"
#include "tasmota_client.h"

static const char *TAG = "tasmota_cli";

typedef struct {
    tasmota_result_cb_t cb;
    char *url;
} tasmota_ctx_t;

static esp_err_t http_handler(esp_http_client_event_t *evt)
{
    if (evt->event_id == HTTP_EVENT_ON_DATA) {
        tasmota_ctx_t *ctx = (tasmota_ctx_t *)evt->user_data;
        if (ctx && ctx->cb) {
            char *resp = strndup(evt->data, evt->data_len);
            bool ok = (esp_http_client_get_status_code(evt->client) == 200);
            ctx->cb(ok, resp ? resp : "");
            free(resp);
        }
    }
    return ESP_OK;
}

static esp_err_t tasmota_request(const char *ip, int port,
                                  const char *path, const char *cmd,
                                  tasmota_result_cb_t cb)
{
    int url_len = snprintf(NULL, 0, "http://%s:%d/cm?cmnd=%s", ip, port, path) + 1;
    char *url = malloc(url_len);
    if (!url) return ESP_ERR_NO_MEM;
    snprintf(url, url_len, "http://%s:%d/cm?cmnd=%s", ip, port, path);

    tasmota_ctx_t *ctx = calloc(1, sizeof(tasmota_ctx_t));
    if (!ctx) {
        free(url);
        return ESP_ERR_NO_MEM;
    }
    ctx->cb = cb;
    ctx->url = strdup(url);

    esp_http_client_config_t config = {
        .url = url,
        .event_handler = http_handler,
        .user_data = ctx,
        .timeout_ms = 5000,
    };

    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (cmd) {
        esp_http_client_set_method(client, HTTP_METHOD_POST);
        esp_http_client_set_post_field(client, cmd, strlen(cmd));
    } else {
        esp_http_client_set_method(client, HTTP_METHOD_GET);
    }

    esp_err_t err = esp_http_client_perform(client);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "HTTP request failed: %s url=%s", esp_err_to_name(err), url);
        if (cb) cb(false, esp_err_to_name(err));
    }

    esp_http_client_cleanup(client);
    free(ctx->url);
    free(ctx);
    free(url);
    return err;
}

static char *url_encode(const char *s)
{
    if (!s) return NULL;
    int len = strlen(s);
    char *out = malloc(len * 3 + 1);
    if (!out) return NULL;
    int pos = 0;
    for (int i = 0; i < len; i++) {
        unsigned char c = s[i];
        if ((c >= '0' && c <= '9') || (c >= 'A' && c <= 'Z') ||
            (c >= 'a' && c <= 'z') || c == '-' || c == '_' || c == '.' || c == '~') {
            out[pos++] = c;
        } else {
            pos += snprintf(out + pos, 4, "%%%02X", c);
        }
    }
    out[pos] = 0;
    return out;
}

esp_err_t tasmota_push_script(const char *ip, int port,
                              const char *script,
                              tasmota_result_cb_t cb)
{
    char *encoded = url_encode(script);
    if (!encoded) return ESP_ERR_NO_MEM;

    // Short URL: http://ip:port/cm
    int url_len = snprintf(NULL, 0, "http://%s:%d/cm", ip, port) + 1;
    char *url = malloc(url_len);
    if (!url) {
        free(encoded);
        return ESP_ERR_NO_MEM;
    }
    snprintf(url, url_len, "http://%s:%d/cm", ip, port);

    // POST body: cmnd=Script%20<encoded>
    int body_len = snprintf(NULL, 0, "cmnd=Script%%20%s", encoded) + 1;
    char *body = malloc(body_len);
    if (!body) {
        free(encoded);
        free(url);
        return ESP_ERR_NO_MEM;
    }
    snprintf(body, body_len, "cmnd=Script%%20%s", encoded);
    free(encoded);

    esp_http_client_config_t config = {
        .url = url,
        .timeout_ms = 10000,
    };

    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (!client) {
        free(url);
        free(body);
        return ESP_ERR_NO_MEM;
    }

    esp_http_client_set_method(client, HTTP_METHOD_POST);
    esp_http_client_set_header(client, "Content-Type", "application/x-www-form-urlencoded");
    esp_http_client_set_post_field(client, body, strlen(body));

    esp_err_t err = esp_http_client_perform(client);
    int status = err == ESP_OK ? esp_http_client_get_status_code(client) : 0;

    if (err != ESP_OK) {
        ESP_LOGE(TAG, "push POST failed: %s url=%s", esp_err_to_name(err), url);
        if (cb) cb(false, esp_err_to_name(err));
    } else if (status != 200) {
        ESP_LOGW(TAG, "push POST returned status %d", status);
        if (cb) cb(false, "HTTP error");
    } else {
        if (cb) cb(true, "OK");
    }

    esp_http_client_cleanup(client);
    free(url);
    free(body);
    return err;
}

esp_err_t tasmota_send_command(const char *ip, int port,
                               const char *command,
                               tasmota_result_cb_t cb)
{
    char path[128];
    snprintf(path, sizeof(path), "%s", command);
    return tasmota_request(ip, port, path, NULL, cb);
}

bool tasmota_discover(const char *ip, int port)
{
    char url[64];
    snprintf(url, sizeof(url), "http://%s:%d/", ip, port);

    esp_http_client_config_t config = {
        .url = url,
        .timeout_ms = 3000,
    };

    esp_http_client_handle_t client = esp_http_client_init(&config);
    esp_err_t err = esp_http_client_perform(client);
    int status = esp_http_client_get_status_code(client);
    esp_http_client_cleanup(client);

    return (err == ESP_OK && status == 200);
}

typedef struct {
    char *data;
    int pos;
    int cap;
} fetch_buf_t;

static esp_err_t fetch_handler(esp_http_client_event_t *evt)
{
    if (evt->event_id == HTTP_EVENT_ON_DATA) {
        fetch_buf_t *fb = (fetch_buf_t *)evt->user_data;
        int avail = evt->data_len;
        while (fb->pos + avail >= fb->cap - 1) {
            fb->cap *= 2;
            char *tmp = realloc(fb->data, fb->cap);
            if (!tmp) return ESP_ERR_NO_MEM;
            fb->data = tmp;
        }
        memcpy(fb->data + fb->pos, evt->data, avail);
        fb->pos += avail;
        fb->data[fb->pos] = 0;
    }
    return ESP_OK;
}

char *tasmota_fetch_sync(const char *ip, int port, const char *command)
{
    int url_len = snprintf(NULL, 0, "http://%s:%d/cm?cmnd=%s", ip, port, command) + 1;
    char *url = malloc(url_len);
    if (!url) return NULL;
    snprintf(url, url_len, "http://%s:%d/cm?cmnd=%s", ip, port, command);

    fetch_buf_t fb = {0};
    fb.cap = 4096;
    fb.data = malloc(fb.cap);
    if (!fb.data) {
        free(url);
        return NULL;
    }
    fb.data[0] = 0;

    esp_http_client_config_t config = {
        .url = url,
        .event_handler = fetch_handler,
        .user_data = &fb,
        .timeout_ms = 8000,
    };

    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (!client) {
        free(url);
        free(fb.data);
        return NULL;
    }

    esp_err_t err = esp_http_client_perform(client);
    char *result = NULL;

    if (err == ESP_OK && esp_http_client_get_status_code(client) == 200 && fb.pos > 0) {
        result = fb.data;
        ESP_LOGI(TAG, "fetch '%s' returned %d bytes", command, fb.pos);
    } else {
        ESP_LOGW(TAG, "fetch '%s': err=%s status=%d bytes=%d",
                 command, esp_err_to_name(err),
                 esp_http_client_get_status_code(client), fb.pos);
        free(fb.data);
    }

    esp_http_client_cleanup(client);
    free(url);
    return result;
}

bool tasmota_wait_online(const char *ip, int port, int timeout_ms)
{
    int waited = 0;
    while (waited < timeout_ms) {
        if (tasmota_discover(ip, port)) return true;
        vTaskDelay(pdMS_TO_TICKS(500));
        waited += 500;
    }
    return false;
}
