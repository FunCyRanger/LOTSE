# AGENTS.md

Three codebases:
- **Root**: HA Jinja templates, YAML blueprints, Python tests
- **`config-hub/`**: ESP-IDF project (C) — Tasmota SML → MQTT → transform → Meshtastic envelope
- **`custom_components/lotse_forecast/`**: HA integration (`integration_type: service`) providing `async_get_solar_forecast` for Energy Dashboard

## Critical gotchas

| Gotcha | Detail |
|--------|--------|
| **NativeEnvironment** | HA auto-parses via `ast.literal_eval`. Tests use standard `Environment`, need **2x `json.loads`** (envelope + inner `payload`). |
| **MQTT topic node format** | Blueprint publishes to `msh/{region}/2/json/mqtt/{node}` where `node` is **decimal** number. Config-hub publishes to `msh/{region}/2/json/mqtt/{hash}` where `hash` is **hex** like `!acaad598`. Auto-discovery extracts `sender` (hex from topic) and `from` (decimal from JSON). Both work — Meshtastic routes by node. |
| **Meshtastic MQTT channel root** | Configure Meshtastic's MQTT channel topic as `msh/{region}/2/json/mqtt/` — trailing `/` required in Meshtastic config itself. The code's publish topics always append a node suffix. |
| **Random jitter** | Blueprint: `range(0,60)|random` delay. Config-hub: `esp_random() % min(interval*1e6/10, 10e6)` jitter. Both prevent mesh flooding. |
| **evaluate_payload** | Must be `false` on all `mqtt.publish` calls. |
| **Payload limits** | Inner ≤220 bytes; envelope ≤4096 bytes. |
| **Envelope format** | `{"from": <int>, "type": "sendtext", "payload": "<json_string>", "channel": 1}`. |
| **Receiver payload type** | Heltec V3 echoes `payload` as **string**. Auto-discovery handles both: `{% if ... is mapping %}...{% else %}...\|from_json({}){% endif %}`. Config-hub has echo fix that reparses string to object. |
| **Config retain** | Config envelopes `retain: true`, measurement envelopes `retain: false`. |
| **Unit mismatch** | kWh sensor in kW slot → key silently omitted. Energy/power units are mutually exclusive. |
| **Case-sensitive units** | Jinja: all `.lower()` normalized. Dict keys lowercase. C: `strcasecmp`/`strcasestr`. |

## Testing

```bash
pip install -r tests/requirements.txt    # pyyaml, jinja2, paho-mqtt

python3 tests/test_mesh.py               # 49 template + roundtrip tests
python3 tests/test_schema.py             # 11 schema tests
python3 tests/test_e2e_mqtt.py           # requires Docker, auto-skipped
python3 tests/check_installation.py --ha-url <url> --token <token>

make -C config-hub/tests run             # 57 transform/parse/GPIO/envelope C tests
```

Test infra: `ha_environment()` — standard Jinja `Environment`, custom `to_json`/`from_json`/`float`/`int` filters, mock `states`/`state_attr`/`expand` globals. Both `test_mesh.py` and `test_schema.py` share the same mocks. C tests use vendored Unity (no cmock, just core assertions) and vendored cJSON.

## YAML validation

```bash
python3 -c "
import yaml, pathlib
yaml.FullLoader.add_constructor('!input', lambda loader, node: node.value)
for f in sorted(pathlib.Path().rglob('*.yaml')):
    yaml.load(f.read_text(), Loader=yaml.FullLoader)
"
```

## CI (`.github/workflows/test.yml`)

Two jobs:
- **test** — Push/PR to `main`. Docker Mosquitto → C tests → Python tests → YAML validation.
- **build** — Tag `v*` only. ESP-IDF v5.4, builds `esp32` + `esp32s3`, creates GitHub Release with `lotse_config_hub-*.bin`.

## HA YAML files

| File | Key details |
|------|-------------|
| `sender-blueprint.yaml` | Unit conversion: W→kW (*0.001), MW→kW (*1000), mV→V (*0.001), kV→V (*1000), Wh→kWh (*0.001), MWh→kWh (*1000). Clamping: power ±500, energy ≥0, bS/wS 0-100 int. Skips `unavailable`/`unknown`/`none`/`NaN`/`inf`/`-inf`. Config envelope on boot + daily via `lotse/config/{node}/<key>` direct topic (`retain: true`). Measurement topic: `msh/{region}/2/json/mqtt/{node}`. `mode: single`. |
| `auto-discovery-automation.yaml` | Trigger: `msh/+/2/json/mqtt/+`. Extracts `from` (decimal from JSON), `sender` (hex from topic), `region`. Universal payload handler for dict/string. Config keys use `lotse/config/{from}/<key>` state_topic. `mode: queued`. |
| `mesh-combined-template.yaml` | HA package template sensors (sums, averages); 18+ derived sensors via regex `node_\d+_gp$` etc. into `sensor.combined_mesh_*`. Includes `combined_mesh_gv1_max` (max neighbor voltage), `combined_mesh_export_ratio` (gep/sp, clamped ≥0), `solar_roughness_index` (CV% of solar power, cross-validated r=-0.957), and `forecast_correction_factor` (actual/forecast ratio with 0.7 EMA decay). Also defines EMA-smoothed forecast inputs (`*_forecast` sensors, α=0.1) to prevent jumps when nodes join/leave. Monotonic clean energy sensor `combined_mesh_se_clean`. |
| `mesh-combined-sensors.yaml` | Additional sensor definitions (weighted SOC, derived). Split into `mesh-combined-*.yaml` package. |
| `mesh-combined-rest.yaml` | Rest sensor for `api.forecast.solar` (aggregate PV forecast per neighborhood). |
| `lotse-dashboard.yaml` | HA dashboard YAML for the "LOTSE Neighborhood" view. |
| `solarforecast-blueprint.yaml` | Template blueprint for per-household PV hourly forecast (uses weather entity, not forecast.solar). |

## config-hub ESP-IDF project

Custom MQTT 3.1.1 broker (select-based, QoS 0, max 8 clients) on raw LWIP sockets — **no external broker needed**. Data paths: (1) MQTT `SENSOR` callback, (2) HTTP poll fallback (600s interval).

Key files:
- `main/main.c` — Init → NVS → WiFi → MQTT broker → HTTP server. Echo fix (parses own-node `payload` string → object). GPIO0=factory reset. `send_interval` minimum 60s. SNTP sync on boot.
- `main/transform.c` — SMI script parser, Tasmota JSON→LOTSE transform, envelope/config-envelope builder.
- `main/lotse_config.{c,h}` — 29-key enum (`LOTSE_KEY_GP`..`LOTSE_KEY_SZ`), 20 measurement + 5 grid quality (`gA1`/`gA2`/`gA3` current, `gF` frequency, `gPF` power factor) + 4 config keys.
- `main/mqtt_broker.c` — Minimal MQTT 3.1.1 broker.
- `main/tasmota_client.c` — HTTP client for Tasmota `/cm`.
- `main/web_server.c` — HTTP server with embedded SPA (`webui/index.html` → `scripts/embed_webui.py` → `main/html.h`).
- `main/config_store.c` — NVS JSON persistence.
- `main/ota.{c,h}` — HTTP firmware OTA.
- `main/wifi_manager.{c,h}` — WiFi station/AP management.

Build targets (CI): `esp32`, `esp32s3`. `sdkconfig.esp32c3` also exists.

### Build & flash

```bash
cd config-hub/
idf.py set-target esp32 && idf.py build
idf.py -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.esp32s3" \
       -B build_esp32s3 set-target esp32s3 build
idf.py -p /dev/ttyUSB0 flash
python3 -c "import serial; ser=serial.Serial('/dev/ttyUSB0'); ser.setDTR(False); ser.setRTS(False); ser.close()"
idf.py -p /dev/ttyUSB0 monitor
```

Firmware version: `git describe --tags --always --dirty --match "v*"` → `LOTSE_VERSION` compile define.

### Tasmota requirements

- `SetOption19=ON` (blocks telemetry, only responds to `/cm`)
- GPIO parsing: `>D` section `GPIO<n>=<func>`, fallback `+<TX>,<RX>` format. Defaults: RX=3, TX=1.
- Unit auto-mapping: W→gP, kWh→gEI, V→gV1, A→gA1/gA2/gA3 (phase-aware L1/L2/L3), Hz→gF, %→bS, empty-unit+label containing "Power factor"→gPF.

## Known stale / non-code content

- `sender-blueprint-python.md` — AI-generated Node-RED guide (not real code)
- `archive/prototype-build.md` — references firmware never committed
- `archive/20260517 AI review/` — AI firmware reviews (may contain errors)
- `.opencode/plans/` — agent session scratch, not docs
- `.opencode/node_modules/` — auto-generated, gitignored

## Human-readable setup guides

- `ha-setup.md` — Full HA integration guide (importing blueprints, auto-discovery, sensors, Energy Dashboard)
- `mesh-setup.md` — Heltec V3 flashing, Meshtastic MQTT/channel config

## Security

- `.gitignore` excludes `*.log` (may contain device IDs, PSKs, credentials)
- All communication outbound-only (MQTT, no incoming ports)
- No firmware/build code committed; generated binaries must not be committed
