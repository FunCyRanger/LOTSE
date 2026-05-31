# AGENTS.md

**This repo is documentation-only.** No firmware, simulation, or build code exists on disk or in `main` branch history. All directories (`firmware/`, `meshtastic-fork-clean/`, `simulation/`) referenced in root `.md` files were planned but never committed, or were deleted.

Exception: `bridge/` contains a working Python MQTT bridge script (see below).

## Current state

Neighborhood energy coordination project — specification/planning phase with one working component. Two AI reviews exist at `20260517 AI review/` (Claude, Grok) with concrete implementation errors — **read both before writing firmware.**

## Running the bridge (only runnable code)

```bash
pip install -r bridge/requirements.txt     # only dep: paho-mqtt
export MQTT_BROKER=192.168.1.100
export INGRESS_NODE_NUM=2892010904
python3 bridge/lotse-bridge.py
```

See `bridge/README.md` for all flags, env vars, and node-address discovery. Every option is also settable as an env var (uppercased).

## No CI / no tests / no build system

This repo has zero CI workflows, test files, linters, formatters, typecheckers, `package.json`, `platformio.ini`, or `Makefile`. Don't look for or run test/lint commands.

## Architecture (chosen approach — May 2026)

```
Each household:
Tasmota ──MQTT──► HA automation ──MQTT──► Heltec V3 (stock, mqtt ch+downlink)
                                              │
                                              ▼ LoRa 868 MHz
                                         all neighbors
```

Every node has the `mqtt` channel with downlink enabled. Each HA publishes to `msh/{R}/2/json/mqtt/` with its own node's decimal `from` — Meshtastic's firmware check ensures only the matching node injects into LoRa. No single point of failure, no extra hardware, no bridge script.

| Component | What it does | Status |
|-----------|-------------|--------|
| `ha-mesh-setup.md` | Per-household setup guide: node config, HA automations, sensor templates | Active guide |
| `HA-integration.md` | Original round-trip test (one injector node) | Superseded by `ha-mesh-setup.md` but kept for reference |
| `bridge/lotse-bridge.py` | Standalone Python MQTT bridge | Superseded by pure-HA approach |
| `data-communication-brainstorming.md` | Architecture comparison of 5 approaches | Reference |

## Key docs

| File | What it contains |
|------|-----------------|
| `ha-mesh-setup.md` | **Current: per-household mesh setup with HA automations** |
| `HA-integration.md` | Older: round-trip test with single injector (kept for reference) |
| `data-communication-brainstorming.md` | Architecture comparison of all approaches |
| `Requirements.md` | Functional/non-functional reqs, household types (T1–T10), device priority |
| `Brainstorming.md` | Architecture evaluation, decision matrix, open design questions |
| `prototype-build.md` | BOM, flashing guide — but **no `platformio.ini` exists** (known gap) |
| `fairness-analysis.md` | FR-06 analysis — **superseded** (FR-06 is now informational only) |
| `simulation-spec.md` | V2 grid utilization simulation — ~900 lines, Python+pandas+pandapower **(active spec)** |
| `simulation-plan.md` | Original simulation plan (v1, pre-v2 simplification) |
| `20260517 AI review/Claude.md` | Lists concrete errors: wrong OBIS code `36.7.0`, SML lib ID, missing `platformio.ini`, baud rate gap |

## Known errors (from AI review, not yet fixed)

- OBIS code `36.7.0` is non-standard; correct for active power feed-in is `-1:16.7.0`
- SML library PlatformIO identifier `m-/SML` is invalid; use `mzi_/sml` or git URL
- No `platformio.ini` file exists anywhere in the repo
- No `README.md` at GitHub root (README.md exists locally but repo is empty on GitHub)

## If building firmware

Reference hardware: Heltec V3 (ESP32-S3 + SX1262 868 MHz). Target firmware stack was Meshtastic v2.7.9 fork. Pinout assumptions vary by the last-active doc — verify against actual board before coding.

## Style conventions

- Root `.md` files are the spec source of truth
- Don't add code without also creating the corresponding build config
- If editing simulation-spec or fairness-analysis, check whether `fairness-analysis.md` states "superseded" before trusting it
