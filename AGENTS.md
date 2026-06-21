# AGENTS.md

Two codebases:
- **Root**: HA Jinja templates, YAML blueprints, Python tests
- **`config-hub/`**: ESP-IDF project (C) — Tasmota SML → MQTT → transform → Meshtastic envelope

Dirs `firmware/`, `meshtastic-fork-clean/`, `simulation/`, `simulation_v2/` are not present in the working tree — abandoned planning directories. `simulation_v2/results/` is `gitignore`d.

## Critical gotchas

| Gotcha | Detail |
|--------|--------|
| **NativeEnvironment** | HA auto-parses `{% set %}...{{ x \| to_json }}` output via `ast.literal_eval`. Sender template builds outer env in one `{% set %}` block: `dict(items) \| to_json` → inner JSON string, then `{"payload": inner, ...} \| to_json` → clean `\"`. Tests use standard `Environment` (not `NativeEnvironment`), so they need **2x `json.loads`**: one on envelope, one on `payload` field. |
| **Topic trailing /** | `msh/{region}/2/json/mqtt/` — trailing `/` required (Meshtastic silently drops without it) |
| **Random jitter** | HA blueprint: random 0-60s delay before publish. Config-hub: `esp_random() % min(interval*1e6/10, 10e6)` jitter per cycle. Both ensure nodes don't flood mesh in lockstep. |
| **`evaluate_payload`** | Must be `false` on `mqtt.publish` service call |
| **Inner payload** | ≤220 bytes; envelope ≤4096 bytes. Keys: 2-3 char abbreviations (`gP`, `bS`, `gIP`, `gEP`, `gP1`-`gP3`, `gV1`-`gV3`, `gEI`, `gEO`, `sP`, `sE`, `bP`, `bEI`, `bEO`, `wP`, `wE`, `wS`) plus config keys (`bC`, `sK`, `sA`, `sZ`) |
| **Envelope format** | `{"from": <int>, "type": "sendtext", "payload": "<json_string>", "channel": 1}`. `from` must match node's own decimal number. |
| **Receiver payload type** | Heltec V3 echoes with `payload` as **string** (not object). `auto-discovery-automation.yaml` handles both: `{% if value_json.payload is mapping %}...{% else %}... \| from_json({}){% endif %}`. `config-hub` has echo fix that reparses string to object before republishing. |
| **Sender unit mismatch** | kWh sensor assigned to kW slot → key silently omitted. `energy_units` tuple (`Wh`,`kWh`,`MWh`) excludes them from power slots and vice versa. |

## Testing (no pytest — standalone scripts)

```bash
pip install -r tests/requirements.txt    # pyyaml, jinja2, paho-mqtt

python3 tests/test_mesh.py               # 39 template + roundtrip tests
python3 tests/test_schema.py             # 11 schema tests
python3 tests/test_e2e_mqtt.py           # requires Docker (eclipse-mosquitto), auto-skipped
python3 tests/check_installation.py --ha-url <url> --token <token>

# Config-hub C (Unity, vendored, no cmock), compiles natively with gcc:
make -C config-hub/tests run             # 52 transform/parse/GPIO/envelope tests
```

Test infra: `ha_environment()` — standard Jinja `Environment`, custom `to_json`/`from_json`/`float`/`int` filters, mock `states`/`state_attr`/`expand` globals.

## YAML validation (`!input` tags)

```bash
python3 -c "
import yaml, pathlib
yaml.FullLoader.add_constructor('!input', lambda loader, node: node.value)
for f in sorted(pathlib.Path().rglob('*.yaml')):
    yaml.load(f.read_text(), Loader=yaml.FullLoader)
"
```

## CI (`.github/workflows/test.yml`)

Push/PR to `main`. Spins up `eclipse-mosquitto` Docker, runs config-hub C tests + all Python tests + YAML validation.

## HA blueprints key behavior

| File | Details |
|------|---------|
| `sender-blueprint.yaml` | Unit conversion: W→kW (*0.001), MW→kW (*1000), mV→V (*0.001), kV→V (*1000), Wh→kWh (*0.001), MWh→kWh (*1000). Clamping: power ±500, energy ≥0, bS/wS 0-100 int. Skips `unavailable`/`unknown`/`none`/`NaN`/`inf`/`-inf`. Publishes measurement data to `msh/{{region}}/2/json/mqtt/{{node}}` with `evaluate_payload: false`. Also publishes config-only envelope (bC/sK/sA/sZ) on HA startup + daily as a separate message when config fields are filled. |
| `auto-discovery-automation.yaml` | Trigger: `msh/+/2/json/mqtt/+`. Extracts `from` (decimal) from `payload_json.from`, `sender` (hex) from topic, `region` from topic. For payload string→dict: `{% if payload is mapping %}payload{% else %}payload \| from_json({}){% endif %}`. Device identifiers: `mesh_node_{{ from }}`. Config keys (`bC`, `sK`, `sA`, `sZ`) only update when present (no overwrite with 0). |
| `mesh-combined-sensors.yaml` | Drop into HA `config/packages/`. 16 sensors: regex `node_\d+_gp$`, `node_\d+_bs$`, etc. Sum power/energy, weighted SOC, total PV/battery capacity. |

## Known stale / non-code content

- `sender-blueprint-python.md` — AI-generated Node-RED guide (not real code)
- `archive/prototype-build.md` — references firmware never committed
- `archive/20260517 AI review/` — AI firmware reviews (may contain errors)
- `.opencode/plans/` — agent session scratch, not docs
- `.opencode/node_modules/` — auto-generated (`@opencode-ai/plugin`), gitignored

## Security

- `.gitignore` excludes `*.log` (may contain device IDs, PSKs, credentials)
- All communication outbound-only (MQTT, no incoming ports)
- No firmware/build code committed; generated binaries must not be committed

## `config-hub/` — ESP-IDF project

Custom MQTT 3.1.1 broker (select-based, QoS 0, max 8 clients) on raw LWIP sockets — **no external broker needed**. Two data paths: (1) MQTT SENSOR callback, (2) HTTP poll fallback.

Key files:
- `main/main.c` — Init → NVS → WiFi → MQTT broker → HTTP server. Contains echo fix: detects own-node echo, parses `payload` string into object, republishes for HA compatibility.
- `main/transform.c` — SMI script parser, Tasmota JSON→LOTSE transform, envelope builder, `build_config_envelope()`
- `main/mqtt_broker.c` — Minimal MQTT 3.1.1 broker
- `main/tasmota_client.c` — HTTP client for Tasmota `/cm` API
- `main/web_server.c` — HTTP server with embedded SPA
- `main/config_store.c` — NVS JSON persistence
- `main/lotse_config.{c,h}` — Shared types, key names, mappings (24 max, 24 keys: 20 measurement + 4 config)
- `webui/index.html` — SPA source; `scripts/embed_webui.py` converts it to `main/html.h`

### Build & flash

```bash
cd config-hub/
idf.py set-target esp32 && idf.py build
idf.py -p /dev/ttyUSB0 flash
# De-assert RTS/DTR to avoid keeping ESP32 in reset:
python3 -c "import serial; ser=serial.Serial('/dev/ttyUSB0'); ser.setDTR(False); ser.setRTS(False); ser.close()"
idf.py -p /dev/ttyUSB0 monitor    # TTY required
```

### Tasmota requirements

- `SetOption19=ON` (blocks telemetry by default, only responds to `/cm` commands)
- GPIO parsing: `>D` section `GPIO<n>=<func>`, fallback `+<TX>,<RX>` format. Defaults: RX=3, TX=1
- Unit auto-mapping: W→gP, kWh→gEI, V→gV1, %→bS
