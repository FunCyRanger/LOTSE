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

| Component | Purpose | Est. cost |
|-----------|---------|-----------|
| Heltec V3 (ESP32-S3 + SX1262 868 MHz) | LoRa mesh node with MQTT downlink | ~€25 |
| Tasmota IR reader | Smart meter IR interface | ~€20 |
| Home Assistant + MQTT broker | Sends and receives mesh data | — |
| USB-C power supply | Powers the node | €0 |

---

## Getting started

1. **Configure your Heltec V3** → [`mesh-setup.md`](mesh-setup.md)
   Flash stock Meshtastic, set up MQTT, create the `mqtt` channel, find your node number.

2. **Set up Home Assistant** → [`ha-setup.md`](ha-setup.md)
   Import the sender blueprint, configure auto-discovery, install combined sensors, link the Energy Dashboard.

That's it. Each neighbor that does the same becomes visible automatically — no central server, no registration.

---

## Key files

| File | Purpose | Group |
|------|---------|-------|
| [`mesh-setup.md`](mesh-setup.md) | Hardware, flashing, Heltec V3 config | **Setup guides** |
| [`ha-setup.md`](ha-setup.md) | Full HA integration guide | **Setup guides** |
| [`sender-blueprint.yaml`](sender-blueprint.yaml) | HA blueprint to send your data into the mesh | **Import into HA** |
| [`auto-discovery-automation.yaml`](auto-discovery-automation.yaml) | Auto-creates sensors for each neighbor | **Import into HA** |
| [`mesh-combined-sensors.yaml`](mesh-combined-sensors.yaml) | Dashboard-ready aggregate sensors | **Import into HA** |
| [`Requirements.md`](Requirements.md) | Requirements, household types | **Reference** |
| [`AGENTS.md`](AGENTS.md) | Project invariants for AI agents | **Reference** |

---

## Repository structure

| Directory | Contents |
|-----------|----------|
| `tests/` | Jinja template rendering tests, schema checks, MQTT roundtrip tests |
| `sender-blueprint.yaml` | Sender automation blueprint (import into HA) |
| `auto-discovery-automation.yaml` | Auto-discovery automation (paste into HA) |
| `mesh-combined-sensors.yaml` | Combined neighborhood HA sensor package |
| `archive/` | Legacy design docs, superseded specs, AI firmware reviews |

---

## Status

- **Phase 1 — Share meter data with neighbors** ✅ working, start here
- **Phase 2 — Coordinated load shedding and flex offers** ⏸️ deferred, no timeline

---

## Contributing

Feedback from: low-voltage infrastructure, embedded systems, MQTT/LoRa, energy management, operational safety.

---

## License

See [LICENSE](LICENSE).

---

## Disclaimer

Experimental research project. Not for production-critical infrastructure without proper validation.
