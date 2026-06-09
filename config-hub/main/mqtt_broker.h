#pragma once

#include "esp_err.h"

typedef void (*mqtt_publish_cb_t)(const char *topic, const char *payload, int payload_len);
typedef void (*mqtt_connect_cb_t)(const char *client_id);

esp_err_t mqtt_broker_start(void);
void mqtt_broker_set_publish_callback(mqtt_publish_cb_t cb);
void mqtt_broker_set_connect_callback(mqtt_connect_cb_t cb);
int  mqtt_broker_client_count(void);
esp_err_t mqtt_broker_publish(const char *topic, const char *payload, int retain);
char *mqtt_broker_get_log_json(void);  // caller must free()
