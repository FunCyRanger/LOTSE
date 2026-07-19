# AGENTS.md

## Three codebases

| Area | Language | Entrypoint / Purpose |
|------|----------|----------------------|
| Root | Jinja/YAML/Python | HA blueprints (`sender-blueprint.yaml`, `sender-config-blueprint.yaml`), Python tests |
| `config-hub/` | C (ESP-IDF v5.4) | Tasmota SML → MQTT → transform → Meshtastic envelope. Builds `esp32` + `esp32s3`. |
| `custom_components/lotse_forecast/` | Python (HA integration) | Per-node + combined sensors, Energy Dashboard forecast, auto-dashboard, self-calibrating model. `integration_type: hub`, `config_flow: true`, depends on `mqtt`. |

## Versioning

Tags `vMAJOR.MINOR.PATCH` (latest: `v3.7.12`). Pushed to GitHub on release. Firmware version: `git describe --tags --always --dirty --match "v*"` → `LOTSE_VERSION` compile define.

## Critical gotchas

| Gotcha | Detail |
|--------|--------|
| **NativeEnvironment** | HA auto-parses via `ast.literal_eval`. Tests use standard `Environment`, need **2x `json.loads`** (envelope + inner `payload`). |
| **MQTT topic node format** | Blueprint publishes `msh/{region}/2/json/mqtt/{node}` with decimal `{node}`. Config-hub publishes hex like `!acaad598`. Auto-discovery extracts `sender` (hex from topic) and `from` (decimal from JSON). Both work. |
| **Meshtastic MQTT channel root** | Configure as `msh/{region}/2/json/mqtt/` — trailing `/` required. Code always appends node suffix. |
| **Random jitter** | Blueprint: `range(0,60)|random` delay. Config-hub: `esp_random() % min(interval*1e6/10, 10e6)`. Prevents mesh flooding. |
| **evaluate_payload** | Must be `false` on all `mqtt.publish` calls. |
| **Payload limits** | Inner ≤220 bytes; envelope ≤4096 bytes. |
| **Envelope format** | `{"from": <int>, "type": "sendtext", "payload": "<json_string>", "channel": 1}`. |
| **Receiver payload type** | Heltec V3 echoes `payload` as string. Auto-discovery handles both (`{% if ... is mapping %}...{% else %}...\|from_json({}){% endif %}`). Config-hub has echo fix. |
| **Config retain** | Config envelopes `retain: true`, measurement `retain: false`. |
| **Unit mismatch** | kWh sensor in kW slot → key silently omitted. Energy/power units mutually exclusive. |
| **Case-insensitive units** | Jinja: all `.lower()` normalized. Dict keys lowercase. C: `strcasecmp`/`strcasestr`. |
| **37 key limit** | `NODE_KEY_META` in `const.py` has 37 entries. Matches `MAX_MAPPINGS=37` in C enum `lotse_key_t`. |

## Testing

```bash
pip install -r tests/requirements.txt    # pyyaml, jinja2, paho-mqtt

# Custom run_all() runners (not pytest):
python3 tests/test_mesh.py               # template + roundtrip (grid quality + config + combined)
python3 tests/test_schema.py             # schema compliance (envelope, payload size, grid)
python3 tests/test_forecast_validation.py # formula + historical CSV + parameter sweep
python3 tests/test_e2e_mqtt.py           # requires Docker Mosquitto, auto-skipped

# Pytest-based:
python3 -m pytest tests/test_calibration.py -v -k "not slow"   # 51+ tests, @pytest.mark.slow excluded
python3 -m pytest tests/test_forecast_integration.py -v         # energy.py backfill integration

make -C config-hub/tests run             # C tests (gcc, no ESP-IDF needed; vendored Unity + cJSON)
make -C config-hub/tests clean           # remove test binary
```

**Test infra:** Tests **mock HA** by inserting `MagicMock()` into `sys.modules` before importing real code (e.g. `test_forecast_integration.py:19-30`). `test_calibration.py` loads `calibration.py` via `importlib` to avoid triggering `__init__.py` (which imports `homeassistant`). `ha_environment()` is a standard Jinja `Environment` with `to_json`/`from_json`/`float`/`int` filters and mock `states`/`state_attr`/`expand` globals.

## YAML validation

```bash
python3 -c "
import yaml, pathlib
yaml.FullLoader.add_constructor('!input', lambda loader, node: node.value)
yaml.FullLoader.add_constructor('!include', lambda loader, node: node.value)
for f in sorted(pathlib.Path().rglob('*.yaml')):
    yaml.load(f.read_text(), Loader=yaml.FullLoader)
"
```

## CI (`.github/workflows/test.yml`)

- **test** — Push/PR to `main`. Docker Mosquitto → `apt install build-essential` → C tests → Python tests → YAML validation.
- **build** — Tag `v*` only. ESP-IDF v5.4, targets `esp32,esp32s3`, creates GitHub Release with `softprops/action-gh-release`, artifacts: `lotse_config_hub-{target}.bin`.

## Blueprints (YAML)

- `sender-blueprint.yaml` — **Only measurement blueprint** (user-configurable, cannot be integrated). 33 inputs (20 measurement + 13 grid quality). Mode: single. Topic: `msh/{region}/2/json/mqtt/{node}`.
- `sender-config-blueprint.yaml` — Config-only. Publishes bC/sK/sA/sZ on boot + daily + trigger to `lotse/config/{node}/<key>` (`retain: true`).
- `solarforecast-blueprint.yaml` — Template blueprint for hourly PV forecast (weather entity). Domain: template.

## config-hub: build & flash

```bash
cd config-hub/
idf.py set-target esp32 && idf.py build
idf.py -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.esp32s3" -B build_esp32s3 set-target esp32s3 build
idf.py -p /dev/ttyUSB0 flash
python3 -c "import serial; ser=serial.Serial('/dev/ttyUSB0'); ser.setDTR(False); ser.setRTS(False); ser.close()"
idf.py -p /dev/ttyUSB0 monitor
```

Custom MQTT 3.1.1 broker (select-based, QoS 0, max 8 clients) on raw LWIP sockets. Data paths: MQTT `SENSOR` callback + HTTP poll fallback (600s interval). Web UI: `webui/index.html` → converted to C header via `scripts/embed_webui.py`.

## Tasmota requirements

- `SetOption19=ON` (blocks telemetry, only responds to `/cm`)
- GPIO parsing: `>D` section `GPIO<n>=<func>`, fallback `+<TX>,<RX>` (defaults RX=3, TX=1)
- Unit auto-mapping: W→gP, kWh→gEI, V→gV1, A→gA1/gA2/gA3 (phase-aware), Hz→gF, %→bS, "Power factor"→gPF

## HA integration quirks

- **ConfigFlow:** `single_instance_allowed` — only one LOTSE integration per HA instance (`config_flow.py:17`).
- **Stale entity cleanup:** On startup, `__init__.py` removes 19+ stale entity types from older versions via `STALE_UNIQUE_IDS`.
- **No external deps:** `"requirements": []` in `manifest.json`. All dependencies are HA built-ins.
- **HA min version:** `2026.1.0` (`hacs.json`).

## What's NOT in this repo (no linter/formatter/typecheck config)

No `.pre-commit-config.yaml`, `pyproject.toml`, `ruff.toml`, `.flake8`, `.clang-format`, `mypy.ini`, or `tsconfig.json` exist. No pre-commit hooks, no formatter, no type checker.

## Standalone analysis scripts

- `forecast_analysis.py` — loads `solarhistory.csv` (not committed, gitignored) for model analysis
- `forecast_optimal_params.py` — parameter sweep against `solarhistory.csv`

## Security

- `.gitignore` excludes `*.log` (may contain device IDs, PSKs, credentials)
- Communication is outbound-only (MQTT, no incoming ports)
- Generated binaries must not be committed
