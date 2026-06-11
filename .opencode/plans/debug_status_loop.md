# Debug: Tasmota STATUS message loop

## Problem

Tasmota publishes `stat/tasmota_A78FD6/STATUS` (full STATUS0-11 dump) every ~5 seconds after connecting to Config Hub's MQTT broker. TelePeriod = 300, so it's not normal telemetry. Source of the `Status` command is unknown.

## Change

### `main/mqtt_broker.c` — `handle_publish()`

Change `ESP_LOGD` to `ESP_LOGI` and include a short payload preview:

```c
static void handle_publish(mqtt_client_t *client, const uint8_t *buf, int len)
{
    if (len < 2) return;
    int topic_len = (buf[0] << 8) | buf[1];
    if (len < 2 + topic_len) return;

    char topic[128] = {0};
    int tlen = topic_len < 127 ? topic_len : 127;
    memcpy(topic, buf + 2, tlen);
    topic[tlen] = 0;

    int payload_len = len - 2 - topic_len;
    const uint8_t *payload = buf + 2 + topic_len;

    ESP_LOGI(TAG, "PUBLISH %s from %s (payload_len=%d)", topic, client->client_id, payload_len);
    if (payload_len > 0) {
        char preview[65];
        int plen = payload_len < 64 ? payload_len : 64;
        memcpy(preview, payload, plen);
        preview[plen] = 0;
        ESP_LOGI(TAG, "  payload: %s", preview);
    }

    forward_publish(topic, payload, payload_len, client);

    if (s_publish_cb) {
        char payload_str[512];
        int plen = payload_len < 511 ? payload_len : 511;
        memcpy(payload_str, payload, plen);
        payload_str[plen] = 0;
        s_publish_cb(topic, payload_str, payload_len);
    }
}
```

This logs every PUBLISH received by the broker, showing the topic, which client sent it, and the first 64 bytes of payload.

## Build & flash

```bash
. ~/esp/esp-idf/export.sh && idf.py build && idf.py -p /dev/ttyUSB0 flash
python3 -c "import serial; ser=serial.Serial('/dev/ttyUSB0'); ser.setDTR(False); ser.setRTS(False); ser.close()"
```

Then monitor serial output and copy the PUBLISH log lines when the STATUS messages fire.
