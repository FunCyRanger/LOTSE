# Phase 1 — LoRa-to-WiFi Data Bridge

**Status:** Architecture definition complete. Build in progress (Heltec V3).

## Concept

Phase 1 is a **data transport pipeline** only: relay IR sensor readings from a smart meter to Home Assistant via a LoRa mesh bridge. No local limit enforcement, no inter-household coordination, no device control.

## Architecture

```
[Tasmota IR sensor] --WiFi (SoftAP HTTP)--> [Heltec V3 (ingress)] --LoRa mesh--> [Heltec V3 (egress)] --WiFi station--> [Home Assistant]
        POST /api/v1/meter                     forward as packet                      MQTT or REST API
```

- **Data ingress**: IR sensor POSTs JSON to `http://192.168.4.1/api/v1/meter` over the Heltec V3's SoftAP WiFi.
- **LoRa transport**: Ingress node broadcasts data as a Meshtastic packet over the LoRa mesh.
- **Home Assistant bridge**: Egress node receives LoRa packets, connects to home WiFi, publishes to Home Assistant via MQTT or REST.

## Hardware

| Component | Purpose |
|-----------|---------|
| Heltec V3 (ESP32-S3 + SX1262 868 MHz) | Ingress node (SoftAP, HTTP server, LoRa TX) |
| Heltec V3 (ESP32-S3 + SX1262 868 MHz) | Egress node (LoRa RX, WiFi station, MQTT) |
| Tasmota IR sensor (or similar) | Reads smart meter IR interface, sends HTTP POST |

## Current build status (Heltec V3)

The Meshtastic firmware (v2.7.9) is the base. Building for `heltec-v3` requires:

| Requirement | Status |
|-------------|--------|
| Base build passes | ❌ Blocked — BLE, Ethernet, nRF52 platform issues |
| BLE excluded | Needs NimBLE lib or source filter |
| Ethernet excluded | Needs source filter on `src/mesh/eth/` |
| nRF52 platform excluded | Needs source filter on `src/platform/nrf52/` |
| ArduinoJson added | Added to root `lib_deps` |

Known build blockers are documented in `AGENTS.md`.

## Next steps

1. Get a clean Meshtastic build for Heltec V3 by stripping unsupported architectures and unused features.
2. Implement SoftAP HTTP endpoint (`POST /api/v1/meter`).
3. Implement LoRa forwarder (inject HTTP payload as Meshtastic packet).
4. Implement egress listener (extract LoRa packets, publish to HA).
5. End-to-end validation.
