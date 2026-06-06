# AGENTS.md

**This repo is documentation-only.** No firmware, simulation, or build code exists on disk
or in `main` branch history. Directories (`firmware/`, `meshtastic-fork-clean/`, `simulation/`,
`simulation_v2/`) referenced in root `.md` files and `.gitignore` were planned but never
committed, or were deleted.

## Project state

Neighborhood energy coordination project — specification/planning phase.

- **Active guides:** `mesh-setup.md` — Heltec V3 configuration; `ha-setup.md` — HA automation integration
- Two AI reviews at `archive/20260517 AI review/` (Claude, Grok) list concrete firmware errors —
  **read both before writing firmware**

## Critical: HA Jinja NativeEnvironment `ast.literal_eval` gotcha

HA uses Jinja2 `NativeEnvironment` which auto-converts template output
back to Python types via `ast.literal_eval`. This means:
- `{{ {"gIP":0} | to_json }}` outputs string `'{"gIP":0}'`, but
  NativeEnvironment parses it back to Python dict `{"gIP": 0}`.
- If that dict is then used in another `| to_json`, it serializes as
  a nested object, not a JSON string — **breaks Meshtastic envelope**.

**Fix**: apply `| to_json` twice to produce a JSON string literal:
`{{ dict(items) | to_json | to_json }}` → output `'"{\\"gIP\\":0}"'` →
NativeEnvironment unwraps to Python string `'{"gIP":0}'` (not a dict).

This applies anywhere the final template output must be a JSON string
rather than a parsed object. Standard `Environment` (used in tests)
does NOT have this behavior.

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
| `mesh-setup.md` | Heltec V3 flashing, MQTT config, channel setup |
| `ha-setup.md` | **Active: full HA integration — sender, receiver, combined sensors, energy dashboard** |
| `Requirements.md` | Reqs, household types (T1–T10), device priority |
| `archive/` | Legacy design docs, superseded specs, old brainstorming |

## Known errors (from AI review; apply to `archive/prototype-build.md`)

- OBIS code `36.7.0` is non-standard; correct for active power feed-in is `-1:16.7.0`
- SML library PlatformIO identifier `m-/SML` is invalid; use `mzi_/sml` or git URL
- No `platformio.ini` exists anywhere in the repo
- No `README.md` at GitHub root (local copy exists; repo is empty on GitHub)

## If building firmware

Reference hardware: Heltec V3 (ESP32-S3 + SX1262 868 MHz). Target was Meshtastic v2.7.9
fork. No build config or fork code exists on disk. `archive/phase1-summary.md` notes BLE/Ethernet/
nRF52 platform code must be excluded from a Meshtastic build. Pinout assumptions vary by
doc — verify against board before coding.
