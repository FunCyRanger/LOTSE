# AGENTS.md

**This repo is documentation-only.** No firmware, simulation, or build code exists on disk
or in `main` branch history. Directories (`firmware/`, `meshtastic-fork-clean/`, `simulation/`,
`simulation_v2/`) referenced in root `.md` files and `.gitignore` were planned but never
committed, or were deleted.

Exception: `bridge/lotse-bridge.py` is a working Python MQTT bridge script (see below).

## Project state

Neighborhood energy coordination project — specification/planning phase.

- **Active guide:** `ha-mesh-setup.md` — per-household mesh with HA automations (working)
- Two AI reviews at `20260517 AI review/` (Claude, Grok) list concrete firmware errors —
  **read both before writing firmware**

## No tests / lint / build

Zero CI workflows, test files, linters, formatters, typecheckers, `package.json`,
`platformio.ini`, or `Makefile`. Don't look for or run test/lint commands.

## Architecture (chosen)

```
Each household:
Tasmota ──MQTT──► HA automation ──MQTT──► Heltec V3 (stock, mqtt ch+downlink)
                                              │
                                              ▼ LoRa 868 MHz
                                         all neighbors
```

Every node has the `mqtt` channel with downlink enabled. Each HA publishes to
`msh/{R}/2/json/mqtt/` — **trailing `/` is required** (Meshtastic silently drops
messages without it). The `from` field must match the node's own decimal number.

## Key documents

| File | Content |
|------|---------|
| `ha-mesh-setup.md` | **Active: per-household mesh with HA automations** |
| `Requirements.md` | Reqs, household types (T1–T10), device priority |
| `Brainstorming.md` | Architecture evaluation, decision matrix, open questions |
| `prototype-build.md` | BOM, flashing guide — **no `platformio.ini`** (known gap) |
| `simulation-spec.md` | V2 grid utilization simulation (active spec) |
| `HA-integration.md` | Older round-trip test (legacy reference) |
| `data-communication-brainstorming.md` | Architecture comparison (legacy reference) |
| `fairness-analysis.md` | FR-06 analysis — **superseded** |
| `simulation-plan.md` | Original simulation plan v1 (legacy reference) |

## Bridge (only runnable code — superseded by pure-HA approach)

```bash
pip install -r bridge/requirements.txt
export MQTT_BROKER=192.168.1.100 INGRESS_NODE_NUM=2892010904
python3 bridge/lotse-bridge.py
```

See `bridge/README.md` for all flags and node-address discovery. Every option is also
settable as an env var (uppercased).

## Known errors (from AI review; apply to `prototype-build.md`)

- OBIS code `36.7.0` is non-standard; correct for active power feed-in is `-1:16.7.0`
- SML library PlatformIO identifier `m-/SML` is invalid; use `mzi_/sml` or git URL
- No `platformio.ini` exists anywhere in the repo
- No `README.md` at GitHub root (local copy exists; repo is empty on GitHub)

## If building firmware

Reference hardware: Heltec V3 (ESP32-S3 + SX1262 868 MHz). Target was Meshtastic v2.7.9
fork. No build config or fork code exists on disk. `phase1-summary.md` notes BLE/Ethernet/
nRF52 platform code must be excluded from a Meshtastic build. Pinout assumptions vary by
doc — verify against board before coding.
