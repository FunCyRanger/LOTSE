#pragma once

#include <stdint.h>
#include <stdbool.h>

#define MAX_SCRIPT_LEN      2048
#define MAX_WIFI_SSID_LEN   32
#define MAX_WIFI_PASS_LEN   64
#define MAX_TASMOTA_IP_LEN  16
#define MAX_CLIENT_ID_LEN   64
#define MAX_TOPIC_LEN       128
#define MAX_METERS          5
#define MAX_MAPPINGS        24
#define MAX_MQTT_CLIENTS    8
#define MQTT_BROKER_PORT    1883
#define WEB_SERVER_PORT     80
#define LOTSE_KEY_LEN       8
#define TASMOTA_VAR_LEN     32

typedef enum {
    WIFI_STATE_INIT,
    WIFI_STATE_AP,
    WIFI_STATE_CONNECTING,
    WIFI_STATE_STATION,
    WIFI_STATE_FAILED
} wifi_state_t;

typedef struct {
    char var_name[TASMOTA_VAR_LEN];
    char lotse_key[LOTSE_KEY_LEN];
    char unit[8];
    char label[32];
} var_mapping_t;

typedef struct {
    bool configured;
    char wifi_ssid[MAX_WIFI_SSID_LEN];
    char wifi_pass[MAX_WIFI_PASS_LEN];
    char tasmota_ip[MAX_TASMOTA_IP_LEN];
    int  tasmota_port;
    char tasmota_topic[64];
    char region[16];
    uint32_t node_decimal;
    char script[MAX_SCRIPT_LEN];
    var_mapping_t mappings[MAX_MAPPINGS];
    int  mapping_count;
    int  gpio_rx;
    int  gpio_tx;
    int  send_interval;
    char node_hash[16];
    // Config metadata (sent over mesh as registration)
    float battery_capacity;   // kWh, 0 = unknown
    float solar_peak;         // kWp, 0 = unknown
    int   panel_angle;        // degrees from horizontal, -1 = unknown
    int   panel_azimuth;      // degrees from north, -1 = unknown
} hub_config_t;

typedef enum {
    LOTSE_KEY_GP, LOTSE_KEY_GIP, LOTSE_KEY_GEP,
    LOTSE_KEY_GP1, LOTSE_KEY_GP2, LOTSE_KEY_GP3,
    LOTSE_KEY_GV1, LOTSE_KEY_GV2, LOTSE_KEY_GV3,
    LOTSE_KEY_GEI, LOTSE_KEY_GEO,
    LOTSE_KEY_SP, LOTSE_KEY_SE,
    LOTSE_KEY_BP, LOTSE_KEY_BS, LOTSE_KEY_BEI, LOTSE_KEY_BEO,
    LOTSE_KEY_WP, LOTSE_KEY_WE, LOTSE_KEY_WS,
    // Config keys (static metadata, not measurement data)
    LOTSE_KEY_BC, LOTSE_KEY_SK, LOTSE_KEY_SA, LOTSE_KEY_SZ,
    LOTSE_KEY_COUNT
} lotse_key_t;

extern const char *LOTSE_KEY_NAMES[LOTSE_KEY_COUNT];
