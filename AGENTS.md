# AGENTS.md

LoRa-to-WiFi data bridge for Home Assistant. Two firmware stacks exist; design docs in root `.md` files.

## Architecture

```
IR sensor --WiFi (SoftAP HTTP)--> Ingress (ESP32-S3) --LoRa 868 MHz--> Egress (ESP32-S3) --WiFi station--> Home Assistant (MQTT/REST)
```

Phase 1 = data transport only.

## Directories

| Path | Purpose |
|------|---------|
| `firmware/` | **Active simple stack** — PlatformIO, RadioLib, ESP32-S3 (LilyGO T3-S3 pinout), no Meshtastic |
| `meshtastic-fork-clean/` | Meshtastic v2.7.9 fork (Heltec V3 target), build in progress |
| `meshtastic-fork/` | Deprecated older fork — reference only |

## Build targets

### Simple stack (`firmware/`)

```bash
cd firmware
pio run -e lora_node       # Ingress: SoftAP + HTTP + LoRa
pio run -e mqtt_bridge     # Egress: LoRa + WiFi STA + MQTT
pio run -e lora_node -t upload --upload-port /dev/ttyUSB0
pio device monitor -p /dev/ttyUSB0 -b 115200
```

Pinout: LilyGO T3-S3 (SX1262: CS=8, SCK=9, MOSI=10, MISO=11, RST=12, BUSY=13, DIO1=14).

### Meshtastic stack (`meshtastic-fork-clean/`)

```bash
cd meshtastic-fork-clean
pio run -e heltec-v3               # build
pio run -e heltec-v3 -t upload --upload-port /dev/ttyUSB0
```

Build filters already in `heltec_v3/platformio.ini`: excludes BLE, Ethernet.

## Important: lib_deps inheritance

If you customize `lib_deps` in an env, use `${env.lib_deps}` to inherit base deps. Otherwise you lose nanopb, ArduinoJson, etc. causing:
- `pb.h: No such file` (nanopb missing)
- `AES.h: No such file` (broken inheritance)

## Quick commands

| Action | Command |
|--------|---------|
| List envs | `pio run -t listenvs` |
| Clean build | `pio run -e <env> -t clean && pio run -e <env>` |
| Serial monitor | `pio device monitor -p /dev/ttyUSB0 -b 115200` |

## Reference docs

- `Requirements.md` — requirements & use cases
- `Brainstorming.md` — architecture notes & open decisions
- `prototype-build.md` — BOM, flashing, test procedure
- `phase1-summary.md` — Phase 1 status
