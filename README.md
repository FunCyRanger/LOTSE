# LOTSE — Local Energy Coordination

> Reducing transformer peaks through local coordination — respecting each household's individual pricing model.

An experimental open-source project exploring how residential loads — EV chargers, batteries, heat pumps, PV surplus — can be coordinated locally to reduce stress on low-voltage distribution grids. No energy trading between households, no cloud dependency, no billing. Each household keeps full control over its own devices and pricing.

---

## Architecture

```
Each household:
Tasmota ──MQTT──► HA automation ──MQTT──► Heltec V3 (stock Meshtastic, mqtt ch+downlink)
                                              │
                                              ▼ LoRa 868 MHz
                                         all neighbors
```

Every node runs stock Meshtastic firmware with the `mqtt` channel enabled. Each Home Assistant publishes its own meter data into the LoRa mesh, and receives data from all neighbors. No custom firmware, no shared infrastructure, no single point of failure.

---

## What you need (per household)

| Component | Purpose |
|-----------|---------|
| Heltec V3 (ESP32-S3 + SX1262 868 MHz) | LoRa mesh node with MQTT downlink |
| Tasmota IR reader | Reads smart meter via optical interface |
| Home Assistant + MQTT broker | Automates sending and receiving |
| USB-C power supply | Existing phone charger works |

---

## Getting started

1. **Configure your Heltec V3** → [`mesh-setup.md`](mesh-setup.md)
   Flash stock Meshtastic, set up MQTT, create the `mqtt` channel, find your node number.

2. **Set up Home Assistant** → [`ha-setup.md`](ha-setup.md)
   Import the sender blueprint, configure auto-discovery, install combined sensors, link the Energy Dashboard.

That's it. Each neighbor that does the same becomes visible automatically — no central server, no registration.

---

## Key files

| File | Content |
|------|---------|
| [`mesh-setup.md`](mesh-setup.md) | Hardware BOM, flashing, Heltec V3 configuration |
| [`ha-setup.md`](ha-setup.md) | Full HA integration — sender, receiver, combined sensors, energy dashboard |
| [`sender-blueprint.yaml`](sender-blueprint.yaml) | HA automation blueprint (import directly) |
| [`mesh-combined-sensors.yaml`](mesh-combined-sensors.yaml) | Combined neighborhood sensor package |
| [`Requirements.md`](Requirements.md) | Requirements, household types, device priority |
| [`AGENTS.md`](AGENTS.md) | Architecture invariants for AI coding agents |

---

## Repository structure

| Directory | Contents |
|-----------|----------|
| `tests/` | Jinja template rendering tests, schema checks, MQTT roundtrip tests |
| `archive/` | Legacy design docs, superseded specs, AI firmware reviews |

---

## Status

Phase 1 (neighborhood data sharing) — working and documented. Phase 2 (coordinated load shedding, flex offers) — deferred pending field experience.

---

## Contributing

Feedback from: low-voltage infrastructure, embedded systems, MQTT/LoRa, energy management, operational safety.

---

## License

See [LICENSE](LICENSE).

---

## Disclaimer

Experimental research project. Not for production-critical infrastructure without proper validation.
