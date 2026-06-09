#pragma once

#include <stdio.h>

#define ESP_LOGE(tag, fmt, ...) fprintf(stderr, "E/%s: " fmt "\n", tag, ##__VA_ARGS__)
#define ESP_LOGW(tag, fmt, ...) fprintf(stdout, "W/%s: " fmt "\n", tag, ##__VA_ARGS__)
#define ESP_LOGI(tag, fmt, ...) fprintf(stdout, "I/%s: " fmt "\n", tag, ##__VA_ARGS__)
#define ESP_LOGD(tag, fmt, ...) fprintf(stdout, "D/%s: " fmt "\n", tag, ##__VA_ARGS__)
#define ESP_LOGV(tag, fmt, ...) fprintf(stdout, "V/%s: " fmt "\n", tag, ##__VA_ARGS__)

typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_NO_MEM -2
#define ESP_ERR_NVS_NOT_FOUND -3
#define ESP_ERR_NVS_NO_FREE_PAGES -4
#define ESP_ERR_NVS_NEW_VERSION_FOUND -5

static inline const char *esp_err_to_name(int err) {
    (void)err;
    return "mock";
}
