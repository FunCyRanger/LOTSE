# Fix: tasmota_fetch_sync doesn't capture response body

## Bug

`tasmota_fetch_sync()` in `tasmota_client.c` calls `esp_http_client_perform()` without an event handler. ESP-IDF's `perform()` reads the full response body internally, firing `ON_DATA` events — but since no handler is registered, the data is silently discarded. After `perform()`, `esp_http_client_read()` returns 0 because there's nothing left buffered.

Result: `tasmota_fetch_sync()` returns an empty string → JSON parsing fails → `verified = false` → "Script unreachable or push failed".

## Changes

### `main/tasmota_client.c`

1. Add `fetch_buf_t` struct (data buffer with pos/cap) before `tasmota_fetch_sync()`
2. Add `fetch_handler()` event handler that appends `evt->data` to the buffer on `HTTP_EVENT_ON_DATA`
3. Rewrite `tasmota_fetch_sync()` to pass the handler + buffer via `.event_handler` / `.user_data` in the config, instead of reading after `perform()`
4. Keep `esp_http_client_get_status_code()` check for 200, use `fb.pos > 0` to confirm data was captured
5. Add `ESP_LOGI` logging of response size for debugging

### No other files changed

`tasmota_client.h`, `web_server.c`, `webui/index.html` — unchanged.

## Build & flash

```bash
. ~/esp/esp-idf/export.sh && idf.py build && idf.py -p /dev/ttyUSB0 flash
python3 -c "import serial; ser=serial.Serial('/dev/ttyUSB0'); ser.setDTR(False); ser.setRTS(False); ser.close()"
```
