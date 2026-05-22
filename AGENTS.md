# Agent Instructions

Spec + simulation repo for a decentralized neighborhood energy coordination system (100+ households). Primary objective: maximize grid utilization to defer upgrades. Design docs are Markdown; the grid utilization simulation is Python.

## Source documents

| File | Key content |
|------|-------------|
| `Requirements.md` | Requirements, use cases, 10 household types (T1–T10), priority hierarchy |
| `Brainstorming.md` | Architecture, protocol, 7 message types, open decisions (§8) |
| `prototype-build.md` | Hardware BOM, circuit, PlatformIO flashing guide |
| `simulation-spec.md` | Grid utilization simulation specification (v2) |
| `fairness-analysis.md` | FR-06 problem statement (superseded — see simulation-spec.md) |
| `20260517 AI review/Claude.md` | Verified errors in `prototype-build.md` |

## Simulation code

**Active**: `simulation_v2/` (pandapower + numpy + pandas). **Archived**: `simulation/` (older version, do not use).

```sh
# Run (approach A, 365 days, synthetic data)
python -m simulation_v2.sim

# Common variations
python -m simulation_v2.sim --approach E --days 30
python -m simulation_v2.sim --data-source opsd
python -m simulation_v2.sim -c configs/stress.yaml

# Technology scaling (PV, EV, heat pump penetration)
python -m simulation_v2.sim --pv-scale 2.0 --ev-scale 1.5

# Penetration sweep — find hosting capacity limits
python -m simulation_v2.sim --sweep

# Exit code: 0 = grid safe (coordination kept transformer ≤ 100%), 1 = grid unsafe
```

Deps: `pip install pandapower numpy pandas pyyaml` (see `simulation_v2/requirements.txt`).

**Key files:**
- `sim.py` — entrypoint, CLI arg parsing, sys.path quirk (`sys.path.insert(0, parent.parent)`), `--sweep` mode
- `agents.py` — 10 household agents (T1–T10), each with a list of `FlexDevice` (ev/battery/pv/heatpump) and device-level priority shedding
- `coordinator.py` — 9 coordination strategies (A–I), `_priority_shed()` tiers: wallbox → battery → heat pump
- `core.py` — `run_simulation()`, `write_timeseries_csv()`, dataclasses for state/signals, `compute_utilization_metrics()`
- `grid.py` — builds pandapower LV network from config
- `data_loader.py` — OPSD time-series data loading
- `configs/` — `default.yaml`, `opsd.yaml`, `stress.yaml`, `opsd_stress.yaml`

**No tests exist.** Results directory (`simulation_v2/results/`) is gitignored — regenerated on each run.

### Configuration

Config keys of interest in `configs/*.yaml`:
- `approach`: coordination strategy (A–I), overridable via `--approach`
- `duration_days`, `timestep_min`, `seed`, `n_households`
- `household_mix`: dict mapping T1–T10 to proportions
- `type_defaults`: per-type overrides for `pv_kwp`, `battery_kwh`, `annual_consumption_kwh`
- `tariff_rate_ct_per_kwh`, `eeg_rate_ct_per_kwh`
- `transformer_kva`, `feeder_config`, `par14a`
- `technology_scaling`: `{pv, ev, heatpump}` multipliers for penetration sweeps (default 1.0)
- `sweep`: `{max_pv_scale, max_ev_scale, max_hp_scale, step}` for `--sweep` mode

## Architecture invariants

- **Signaling/coordination layer only** — never controls devices directly. All device control stays with household's EMS (OpenEMS, evcc, Home Assistant).
- **Infrastructure Safety (hard constraint) > Economic Fairness (informational)** — load shed order: EV wallbox → battery charging → heat pump. Balcony solar curtailed if reverse power flow exceeded. Within each household, devices shed by priority: EV (prio 1) → battery (2) → PV (3) → heat pump (4).
- **Phase 1**: individual allocation, no inter-household communication. **Phase 2**: flexibility trading + §14a signals; Phase 1 limits remain hard ceiling.
- **Grid utilization** is the primary evaluation metric: peak reduction, congestion events, headroom increase. FR-06 (household economics) is informational only.

## Communication constraints

- No incoming ports. ≥100m through walls/cellars. No port forwarding, DDNS, or VPN.
- Preferred transport: LoRa 868 MHz (~50 bytes per ~50s, 1% duty cycle).

## Known errors (verified, carry forward)

| Error | Fix |
|-------|-----|
| PlatformIO library ID `m-/SML` invalid | Use **`mzi_/sml`** instead |
| Holley DTZ541 baud 115200 but firmware defaults to 9600 | Handle per-meter baud config |
| OBIS code `36.7.0` wrong for instantaneous power | Use **`-1:16.7.0`** (bidirectional) |
| Prototype steps P3–P5 test Phase 2 LoRa but labeled Phase 1 | Phase 1 has no inter-household comm |

## Open design decisions (Brainstorming §8)

| # | Question | Status |
|---|----------|--------|
| Q1 | Communication medium (LoRa vs MQTT vs hybrid) | Open |
| Q2 | Coordinator placement | Phase 1: none. Phase 2: open |
| Q6 | Flex matching algorithm | Open |
| Q7 | Data retention | Open |

## Key references

- **Regulatory**: §14a EnWG, BNetzA procedure, MsbG (metering). Links in `Requirements.md §7`.
- **EMS**: OpenEMS, evcc, Home Assistant (MQTT/REST API). Smart meter SML (IEC 62056-21) via IR/UART.
- **LoRa stacks**: RadioLib, Meshtastic. SML parsing: ESPHome, Tasmota.
- **Cost targets**: €100–200/hh one-time (BOM ~€46–55), central ≤€300, €0 recurring.
