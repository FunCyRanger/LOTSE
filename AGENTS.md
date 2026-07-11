# AGENTS.md

Three codebases:
- **Root**: HA Jinja templates, YAML blueprints, Python tests
- **`config-hub/`**: ESP-IDF project (C) — Tasmota SML → MQTT → transform → Meshtastic envelope
- **`custom_components/lotse_forecast/`**: HA integration (`integration_type: hub`) providing everything: per-node sensor creation from MQTT mesh messages, combined aggregation sensors, `async_get_solar_forecast` for the Energy Dashboard, and auto-created LOTSE dashboard. Replaces `auto-discovery-automation.yaml`, `mesh-combined-template.yaml`, `mesh-combined-sensors.yaml`, and `lotse-dashboard.yaml` — no YAML files needed (v3.1+).

## Versioning

This project follows [Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`):

| Component | Meaning |
|-----------|---------|
| MAJOR | Breaking changes (integration replaces blueprints, removed YAML files) |
| MINOR | New features (dynamic dashboard, energy auto-link) |
| PATCH | Bug fixes (comma locale crash, registry revert) |

Tags follow the pattern `v3.5.2` and are pushed to GitHub on release.

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

python3 tests/test_mesh.py               # 57 template + roundtrip tests (incl. grid quality + config)
python3 tests/test_forecast_validation.py # 7 validation tests (formula + historical CSV)
python3 tests/test_schema.py             # 18 schema tests (incl. config blueprint + payload size + grid)
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
| `sender-blueprint.yaml` | **Only remaining measurement YAML** (cannot be integrated — user-configurable automation). 33 inputs (20 measurement + 13 grid quality). Unit conversion: W→kW, MW→kW, mV→V, kV→V, Wh→kWh, MWh→kWh. Clamping: power ±500, energy ≥0, bS/wS 0-100 int, grid quality raw pass-through. Skips `unavailable`/`unknown`/`none`/`NaN`/`inf`/`-inf`. gEI mandatory. Boot notification. Measurement topic: `msh/{region}/2/json/mqtt/{node}`. `mode: single`. |
| `sender-config-blueprint.yaml` | Config-only blueprint publishes bC/sK/sA/sZ on boot + daily + trigger. Direct topics `lotse/config/{node}/<key>` (`retain: true`). Boot notification. `mode: single`. |
| `solarforecast-blueprint.yaml` | Template blueprint for per-household PV hourly forecast (uses weather entity). |

**Deleted YAMLs** (functionality moved into integration `lotse_forecast` v3.1+):
- `auto-discovery-automation.yaml` — MQTT subscription + per-node sensor creation now in `__init__.py`
- `mesh-combined-template.yaml` — combined aggregation sensors now in `sensor.py` (`COMBINED_FNS` + `LOTSECombinedSensor`)
- `mesh-combined-sensors.yaml` — additional sensor defs merged into `sensor.py` + `const.py`
- `lotse-dashboard.yaml` — dashboard auto-created via lovelace storage API in `dashboard.py`

## config-hub ESP-IDF project

Custom MQTT 3.1.1 broker (select-based, QoS 0, max 8 clients) on raw LWIP sockets — **no external broker needed**. Data paths: (1) MQTT `SENSOR` callback, (2) HTTP poll fallback (600s interval).

Key files:
- `main/main.c` — Init → NVS → WiFi → MQTT broker → HTTP server. Echo fix (parses own-node `payload` string → object). GPIO0=factory reset. `send_interval` minimum 60s. SNTP sync on boot.
- `main/transform.c` — SMI script parser, Tasmota JSON→LOTSE transform, envelope/config-envelope builder.
- `main/lotse_config.{c,h}` — 37-key enum (`LOTSE_KEY_GP`..`LOTSE_KEY_SZ`), 20 measurement + 9 grid quality (`gA1`/`gA2`/`gA3` current, `gF` frequency, `gPF` power factor, `gQ`/`gQ1`/`gQ2`/`gQ3` reactive power) + 4 config keys + 4 apparent power (`gS`/`gS1`/`gS2`/`gS3`). MAX_MAPPINGS=37.
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
