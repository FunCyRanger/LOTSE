# LEM2

Requirements-phase repository for a decentralized Local Energy Management System (LEM-Netz) for German residential neighborhoods.

## Architecture invariant

**LEM is a signaling/coordination layer, not a device controller.** Each household already has or can run its own EMS (OpenEMS, evcc, Home Assistant, etc.). The LEM agent is a thin bridge between the neighborhood and the household's existing automation — it never controls inverters, heat pumps, or wallboxes directly. All device control stays with the household's own system.

## Key document

- `LEM-Requirements.md` — single source of truth (Draft)

## Regulatory context

Everything references German energy law: §14a EnWG (grid-serving control), EEG (feed-in), MsbG (metering). The system deliberately avoids formal balancing-energy-sharing accounting.

## Phase 1 architecture

**Individual allocation** — each household's agent self-regulates within its configured grid limit (based on connection contract). No coordinator, no inter-household communication needed for grid protection. Phase 2 adds flexibility coordination between households but individual limits remain the hard ceiling.

## Priority invariant

**Infrastructure Safety > Economic Fairness** — non-negotiable hard constraint. When grid limits are breached, controllable loads shed in this fixed order: EV wallbox → battery charging → heat pump. Balcony solar curtailed if reverse power flow limits exceeded.

## Household types (section 2b)

Ten types defined with distinct pricing models (fixed/EPEX Spot/§14a/dynamic/mixed) and optimization goals. Each household must break even or benefit — optimization cannot cause financial loss relative to baseline.

## Communication constraints (section 4)

- **No incoming ports**: All household communication must be outbound-only or via dedicated local medium.
- **Range**: ≥100m through walls/cellars between any two households (within-household communication is unconstrained).
- **Ease**: No port forwarding, DDNS, or VPN setup — layperson-installable.
- Internet connections can be used if these constraints are met.

## Phases

- **Phase 1 (Data Collection)**: grid limit broadcast, measurement acquisition, onboarding
- **Phase 2 (Coordination)**: flexibility trading, local coordination, §14a grid-serving signals

## Cost targets (hard constraints)

- Per-household hardware: €100–200 one-time
- Central infra: ≤€300 one-time
- Recurring costs: €0 (all software OSS, EPEX Spot data free)

## Current status

Specification-only. No code, no build/test tooling, no CI. Any implementation work must start from `LEM-Requirements.md`.
