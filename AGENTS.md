# AGENTS.md

Two codebases:
- **Root**: HA Jinja templates, YAML blueprints, Python tests, docs
- **`config-hub/`**: ESP-IDF project (C) — Tasmota SML → MQTT → transform → Meshtastic envelope

Dirs `firmware/`, `meshtastic-fork-clean/`, `simulation/`, `simulation_v2/` were planned but never committed.

## Critical gotchas

| Gotcha | Detail |
|--------|--------|
| **NativeEnvironment** | HA Jinja auto-parses `{% set %}...{{ x \| to_json }}` output via `ast.literal_eval`. Build envelope in one `{% set %}` block: `{% set inner = dict(items) \| to_json %}` captures inner JSON as Python string, `{% set outer_env = {"payload": inner, ...} %}` embeds it, `{{ outer_env \| to_json }}` produces clean `\"`. Tests use standard `Environment` (not `NativeEnvironment`) so they need **2x `json.loads`**: one on envelope, one on `payload` field. |
| **Topic trailing /** | `msh/{region}/2/json/mqtt/` — trailing `/` required (Meshtastic silently drops without it) |
| **`evaluate_payload`** | Must be `false` on `mqtt.publish` service call |
| **Payload** | Inner JSON ≤220 bytes; envelope ≤4096 bytes. Keys: 2-3 char abbreviations (`gP`, `bS`, `gIP`, `gEP`, `gP1`-`gP3`, `gV1`-`gV3`, `gEI`, `gEO`, `sP`, `sE`, `bP`, `bEI`, `bEO`, `wP`, `wE`, `wS`) |
| **Envelope format** | `{"from": <int>, "type": "sendtext", "payload": "<json_string>", "channel": 1}` |
| **Sender `from`** | Must match node's own decimal number |
| **Receiver payload** | Heltec V3 echoes LoRa with `payload` as **string** (not object). `auto-discovery-automation.yaml` handles both: `{% if value_json.payload is mapping %}...{% else %}... \| from_json({}){% endif %}`. Sender via config-hub has echo fix that reparses to object. |

## Testing (no pytest — standalone scripts)

```bash
pip install -r tests/requirements.txt

python3 tests/test_mesh.py       # 32 Jinja template + roundtrip tests
python3 tests/test_schema.py     # 9 schema constraint tests
python3 tests/test_e2e_mqtt.py   # requires Docker (eclipse-mosquitto), auto-skipped
python3 tests/check_installation.py --ha-url <url> --token <token>  # HA health check

# Config-hub C (Unity, vendored, no cmock):
make -C config-hub/tests run     # 30+ transform/parse/GPIO/envelope tests
```

Test mock infra: `ha_environment()` — standard Jinja `Environment` (not `NativeEnvironment`), custom `to_json`, `from_json`, `float`, `int` filters, mock `states`/`state_attr`/`expand` globals.

## YAML validation (handles `!input` tags)

```bash
python3 -c "
import yaml, pathlib
yaml.FullLoader.add_constructor('!input', lambda loader, node: node.value)
for f in sorted(pathlib.Path().rglob('*.yaml')):
    yaml.load(f.read_text(), Loader=yaml.FullLoader)
"
```

## CI (`.github/workflows/test.yml`)

Push/PR to `main`. Spins up `eclipse-mosquitto` Docker service, runs config-hub C tests + all 3 Python test scripts + YAML validation.

## Sender blueprint (`sender-blueprint.yaml`)

Unit conversion logic: W→kW (*0.001), MW→kW (*1000), mV→V (*0.001), kV→V (*1000), Wh→kWh (*0.001), MWh→kWh (*1000). Clamping: power ±500, energy ≥0, bS/wS 0-100 int. Skips `unavailable`/`unknown`/`none`/`NaN`/`inf`/-`inf` states. Skips unit mismatch (kWh sensor in kW slot). Sends to `msh/{{region}}/2/json/mqtt/{{node}}` with `evaluate_payload: false`.

## Auto-discovery (`auto-discovery-automation.yaml`)

Trigger: `msh/+/2/json/mqtt/+`. Extracts `from` (decimal) from `payload_json.from`, `sender` (hex) from `topic.split('/')[-1]`, `region` from `topic.split('/')[1]`. `pp` variable: `{% if payload is mapping %}payload{% else %}payload | from_json({}){% endif %}`. Publishes HA MQTT discovery configs for each present key. Node `device` identifiers: `mesh_node_{{ from }}`.

## Combined sensors (`mesh-combined-sensors.yaml`)

Drop into HA `config/packages/`. Regex patterns: `node_\d+_gp$`, `node_\d+_bs$`, etc. Sum for power/energy, average for SOC.

## Known stale content

- `sender-blueprint-python.md` — AI-generated Node-RED guide, **not real code**
- `archive/prototype-build.md` — references firmware that was never committed
- `archive/20260517 AI review/` — two AI firmware reviews with errors; read before attempting firmware
- `.opencode/plans/` — agent session scratch, not docs

## Security

- `.gitignore` excludes `*.log` (may contain device IDs, PSKs, credentials)
- All communication outbound-only (MQTT, no incoming ports)
- No firmware/build code committed; generated binaries must not be committed

## `config-hub/` — ESP-IDF project

Custom MQTT 3.1.1 broker (select-based, QoS 0, max 8 clients) on raw LWIP sockets — no external broker. Two data paths: (1) MQTT SENSOR callback, (2) HTTP poll fallback.

### Key files

| File | Purpose |
|------|---------|
| `main/main.c` | Init → NVS → WiFi → MQTT broker → HTTP server. Own-node echo fix for `payload` string→object republish |
| `main/transform.c` | SMI parser, Tasmota JSON→LOTSE transform, envelope builder |
| `main/mqtt_broker.c` | Minimal MQTT 3.1.1 broker |
| `main/tasmota_client.c` | HTTP client for Tasmota `/cm` API |
| `main/web_server.c` | HTTP server with embedded SPA |
| `main/config_store.c` | NVS JSON persistence |
| `main/lotse_config.c` | Shared types, key names |
| `webui/index.html` | SPA source |
| `scripts/embed_webui.py` | Converts `webui/index.html` → `main/html.h` |

### Build & flash

```bash
cd config-hub/
idf.py set-target esp32 && idf.py build
idf.py -p /dev/ttyUSB0 flash
python3 -c "import serial; ser=serial.Serial('/dev/ttyUSB0'); ser.setDTR(False); ser.setRTS(False); ser.close()"  # de-assert RTS/DTR
idf.py -p /dev/ttyUSB0 monitor  # TTY required
```

### Tasmota requirements

- `SetOption19=ON` (blocks telemetry by default)
- GPIO parsing: `>D` section `GPIO<n>=<func>`, fallback `+<TX>,<RX>` format. Defaults: RX=3, TX=1
- Unit auto-mapping: W→gP, kWh→gEI, V→gV1, %→bS
