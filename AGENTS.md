# AGENTS.md

LoRa-to-WiFi data bridge for Home Assistant. Firmware in `meshtastic-fork-clean/` (PlatformIO ESP32-S3 Heltec V3); design docs in root `.md` files.

## System architecture

```
IR sensor --WiFi (SoftAP HTTP)--> Heltec V3 (ingress) --LoRa mesh--> Heltec V3 (egress) --WiFi station--> Home Assistant (MQTT/REST)
```

Phase 1 = data transport only (no local limit enforcement, no inter-household coordination).

## Directories

| Path | Contents |
|------|----------|
| `meshtastic-fork-clean/` | Active PlatformIO ESP32-S3 firmware (Heltec V3 target, Meshtastic v2.7.9). |
| `meshtastic-fork/` | Earlier LoRa stack fork (deprecated — kept for reference). |
| `firmware/` | Unused placeholder (empty). |

## Build & flash (Heltec V3)

```bash
cd meshtastic-fork-clean
pio run -e heltec-v3               # build
pio run -e heltec-v3 -t upload --upload-port /dev/ttyUSB0  # flash via CP2102 UART
```

**Known build blockers (Heltec V3):**

| Error | Cause | Fix |
|-------|-------|-----|
| `host/ble_uuid.h: No such file` | Framework BLE library requires NimBLE. | Add `nkolban/NimBLE-Arduino` to `lib_deps` or exclude BLE sources. |
| `RAK13800_W5100S.h: No such file` | Ethernet code not needed. | Exclude `src/mesh/eth/` in `build_src_filter`. |
| `bluefruit_common.h: No such file` | nRF52 platform code compiled for ESP32. | Exclude `src/platform/nrf52/` in `build_src_filter`. |
| `AES.h: No such file` | `lib_deps` override broke base inheritance. | Use `${env.lib_deps}` to inherit, don't re-list. |
| `pb.h: No such file` | Nanopb missing from deps. | Same cause — inherit from base, don't override. |

## Data bridge implementation plan

1. **Ingress node** (Heltec V3, SoftAP mode):
   - Run SoftAP on `192.168.4.1`.
   - Accept HTTP POST at `/api/v1/meter` with IR sensor JSON payload.
   - Forward payload over LoRa mesh as a Meshtastic packet.
2. **Egress node** (Heltec V3, WiFi station mode):
   - Connect to home WiFi.
   - Listen for specific LoRa packets.
   - Forward data to Home Assistant via MQTT or REST.
3. **Simplify**: strip BLE, Ethernet, GPS, display UI from the build to reduce flash size and build time.

## Known firmware errors

| Error | Fix |
|-------|-----|
| `MESHTASTIC_EXCLUDE_WEBSERVER=1` in `configuration.h:536` | Set `-D MESHTASTIC_EXCLUDE_WEBSERVER=0` |
| Serial corruption after proto load | Upstream Meshtastic bug: null byte corrupts `RedirectablePrint` after device.proto load. |
| DTR/RTS reset inverted | `setDTR(False)` = EN LOW (reset). Correct: `True → False (wait) → True`. |

## Open decisions (Brainstorming §8)

| # | Question | Status |
|---|----------|--------|
| Q1 | Comms medium | **Decided: LoRa 868 MHz + SoftAP HTTP** |
| Q2 | Coordinator placement | Phase 1: none. Phase 2: open |
| Q6 | Flex matching algorithm | Open |
| Q7 | Data retention | Open |

## Quick commands (firmware project root)

| Action | Command |
|--------|---------|
| List envs | `pio run -t listenvs` |
| Clean build | `pio run -e heltec-v3 -t clean && pio run -e heltec-v3` |
| Monitor serial | `pio device monitor -p /dev/ttyUSB0 -b 115200` |
