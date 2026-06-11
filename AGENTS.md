# AGENTS.md

Two codebases in one repo:
- **Root**: HA Jinja templates, YAML blueprints, Python tests, docs — no build code
- **`config-hub/`**: ESP-IDF project (C). Working end-to-end: Tasmota SML → MQTT → transform → Meshtastic envelope → mqtt publish.

Dirs `firmware/`, `meshtastic-fork-clean/`, `simulation/`, `simulation_v2/` referenced in root `.md` files were planned but never committed.

## Project

Neighborhood energy coordination (Phase 1: share meter data over LoRa). Each household: Tasmota → MQTT → HA automation → MQTT → Heltec V3 (stock Meshtastic, mqtt ch+downlink) → LoRa 868 MHz → all neighbors.

## Critical: HA Jinja `NativeEnvironment` gotcha

HA uses Jinja2 `NativeEnvironment` which auto-converts template output back to Python types via `ast.literal_eval`. `{{ {"gIP":0} | to_json }}` outputs string `'{"gIP":0}'` but NativeEnvironment parses it back to dict `{"gIP": 0}`, breaking the Meshtastic envelope.

**Fix**: apply `| to_json` when embedding `inner` into the outer envelope dict: `payload: "{{ inner | to_json }}"`. This re-serializes the NativeEnvironment-parsed dict back to a JSON string at the point of embedding. The inner template uses single `| to_json` only; the outer dict's `payload` value goes through a second `| to_json` to produce clean single-level `\"` escaping (avoids the bloated `\\\"` of double-encoding). Tests use standard `Environment` (no NativeEnvironment) and need one `json.loads` call.

## Payload & MQTT conventions

| Rule | Detail |
|------|--------|
| Topic | `msh/{region}/2/json/mqtt/` — **trailing `/` required** (Meshtastic silently drops without it) |
| `from` | Must match the node's own decimal number |
| Payload keys | 2-3 char abbreviations: `gP` (grid power), `bS` (battery SoC), `gIP`, `gEP`, `gP1`-`gP3`, `gV1`-`gV3`, `gEI`, `gEO`, `sP`, `sE`, `bP`, `bEI`, `bEO`, `wP`, `wE`, `wS` |
| Envelope | `{"from": <int>, "type": "sendtext", "payload": "<json_string>", "channel": 1}` |
| `evaluate_payload` | Must be `false` on `mqtt.publish` service call |
| Max payload | 220 bytes inner JSON; full MQTT envelope < 4096 bytes |
| Sender interval | Default 5 min, configurable 1-60 min |

## Critical: test infrastructure quirks

Python tests do NOT use pytest — they are standalone scripts with custom runners:
```bash
pip install -r tests/requirements.txt
python3 tests/test_mesh.py       # 32 template + roundtrip tests
python3 tests/test_schema.py     # 9 schema constraint tests
python3 tests/test_e2e_mqtt.py   # requires Docker (eclipse-mosquitto), auto-skipped if unavailable
```

Config-hub C tests use Unity (vendored, no cmock):
```bash
make -C config-hub/tests run     # 30+ transform/parse/GPIO/envelope tests
```
Compiles `test_transform.c`, `unity.c`, `../main/transform.c`, `../main/lotse_config.c`, and vendored `cJSON` with `-Wall -Wextra -Werror`.

The test mock infra (`ha_environment()`) mimics HA's Jinja environment with custom `to_json`, `from_json`, `float`, `int` filters and mock states. Tests use standard `Environment`, **not** `NativeEnvironment`, so rendering the sender template requires one `json.loads` call to parse the single-encoded payload (`render_sender()` helper).

`tests/check_installation.py` — standalone HA connectivity health check (requires HA URL + token).

YAML validation handles `!input` tags via a custom constructor:
```bash
python3 -c "
import yaml, pathlib
yaml.FullLoader.add_constructor('!input', lambda loader, node: node.value)
for f in sorted(pathlib.Path().rglob('*.yaml')):
    yaml.load(f.read_text(), Loader=yaml.FullLoader)
"
```

## CI

`.github/workflows/test.yml`: runs on push/PR to `main`. Spins up `eclipse-mosquitto` Docker service, runs config-hub C tests + all 3 Python test scripts + YAML validation.

## Known stale content

- `sender-blueprint-python.md` — AI-generated Node-RED guide, **not real code**, describes a non-existent protocol
- `archive/prototype-build.md` — references firmware code, PlatformIO configs, and a Meshtastic fork that were never committed
- Two AI reviews at `archive/20260517 AI review/` (Claude, Grok) list concrete firmware errors; read before attempting firmware
- `.opencode/plans/` — agent session scratch, not project documentation

## Security

- `.gitignore` excludes `*.log` files (may contain device identifiers, PSKs, or credentials)
- No firmware/build code exists — any generated binaries must not be committed
- All communication is outbound-only (MQTT, no incoming ports)

## `config-hub/` — ESP-IDF project

Config Hub ESP32 device that replaces the HA Jinja sender. Tasmota IR reader publishes raw SML via MQTT → Config Hub transforms → publishes Meshtastic envelope to `msh/{region}/2/json/mqtt/`.

### Architecture

```
Tasmota (SMI script) --MQTT--> Config Hub --MQTT--> Heltec V3 --LoRa--> neighbors
```

Transform runs on Config Hub (replaces HA Jinja sender). Custom MQTT 3.1.1 broker (select()-based, QoS 0, max 8 clients) on raw LWIP sockets — no external broker dependency.

### Key files

| File | Purpose |
|------|---------|
| `main/main.c` | Init → NVS → WiFi → MQTT broker → HTTP server. Two data paths: (1) MQTT SENSOR callback, (2) HTTP poll fallback task |
| `main/transform.c` | SMI parser, Tasmota JSON→LOTSE payload transformer, Meshtastic envelope builder |
| `main/mqtt_broker.c` | Minimal MQTT 3.1.1 broker |
| `main/tasmota_client.c` | HTTP client for Tasmota `/cm` API |
| `main/web_server.c` | HTTP server with embedded SPA |
| `main/config_store.c` | NVS JSON persistence |
| `main/lotse_config.c` | Shared types, key names |
| `webui/index.html` | SPA source |
| `scripts/embed_webui.py` | Converts `webui/index.html` → `main/html.h` |

### Build

```bash
cd config-hub/
idf.py set-target esp32
idf.py build
idf.py -p /dev/ttyUSB0 flash
# After flash: de-assert RTS/DTR so ESP32 doesn't stay in reset:
python3 -c "import serial; ser=serial.Serial('/dev/ttyUSB0'); ser.setDTR(False); ser.setRTS(False); ser.close()"
# Monitor (TTY required):
idf.py -p /dev/ttyUSB0 monitor
```

### Echo fix (essential for HA receiver compat)

When the Heltec V3 echoes a `sendtext` message back via LoRa, the `payload` field arrives as an escaped JSON string. `main.c:on_mqtt_publish()` detects messages on `msh/{region}/2/json/mqtt/{node_hash}`, parses the inner JSON string, and republishes with `"type": "text"` and `payload` as a parsed JSON object. Without this, `value_json.payload.gEI` in HA receiver templates would fail because `payload` would be a string, not a dict.

**Caveat**: The echo fix only runs for the config-hub's own `node_hash` (sender-side). On the receiver's HA broker (no config-hub), LoRa echoes arrive with `payload` as a raw string. The `auto-discovery-automation.yaml` handles both cases via a `pp` variable (`trigger.payload_json.payload | from_json({})` with `is mapping` fallback) and extracts `sender` from `trigger.topic.split('/')[-1]` instead of the message body.

### Tasmota requirements

- `SetOption19=ON` (was OFF by default, blocks all telemetry publishing)
- GPIO parsing: `transform_parse_gpio()` scans `>D` section for `GPIO<n>=<func>`, falls back to `+<TX>,<RX>` format. Defaults: RX=3, TX=1
- SPI: unit-based auto-mapping (W→gP, kWh→gEI, V→gV1, %→bS), overridable via dropdown
