# Local Energy Coordination

> Reducing transformer peaks through local coordination — respecting each household's individual pricing model.

An experimental open-source project exploring how residential loads — EV chargers, batteries, heat pumps, PV surplus — can be coordinated locally to reduce stress on low-voltage distribution grids. No energy trading between households, no cloud dependency, no billing. Each household keeps full control over its own devices and pricing — coordination never forces an action that financially disadvantages a household relative to its baseline (FR-06).

---

## Architecture (Phase 1 — Data Bridge)

```
IR sensor --WiFi (SoftAP HTTP)--> Heltec V3 (ingress) --LoRa mesh--> Heltec V3 (egress) --WiFi station--> Home Assistant
```

Phase 1 is a **data transport pipeline**: relay smart meter IR readings from sensor to Home Assistant via LoRa. No local limit enforcement, no inter-household coordination.

**Phase 2** — Optional neighborhood coordination (flex offers, load shedding). See [Brainstorming.md](Brainstorming.md).

---

## Repository

| File | Content |
|------|---------|
| [`Requirements.md`](Requirements.md) | Requirements, use cases, priority hierarchy |
| [`Brainstorming.md`](Brainstorming.md) | Architecture, hardware evaluation, open decisions |
| [`prototype-build.md`](prototype-build.md) | BOM, circuit, PlatformIO flashing guide |
| [`phase1-summary.md`](phase1-summary.md) | Phase 1 data bridge status |
| [`AGENTS.md`](AGENTS.md) | Architecture invariants & constraints (AI agent reference) |

## Technical Direction

| Layer | Choice |
|-------|--------|
| Transport | LoRa 868 MHz + WiFi |
| Ingress HW | Heltec V3 (ESP32-S3 + SX1262) |
| Egress HW | Heltec V3 (ESP32-S3 + SX1262) |
| Sensor IF | Tasmota IR → WiFi (SoftAP HTTP) |
| HA IF | MQTT or REST API |
| Build | PlatformIO + Arduino ESP32 core |
| LoRa stack | Meshtastic firmware |

## Status

Phase 1 data bridge: specification complete, build in progress.

---

## Contributing

Feedback from: low-voltage infrastructure, embedded systems, MQTT/LoRa, energy management, operational safety.

---

## Disclaimer

Experimental research project. Not for production-critical infrastructure without proper validation.
