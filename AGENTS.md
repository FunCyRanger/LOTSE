# LOTSE

Requirements-phase repository for a decentralized Local Energy Management System (LOTSE) for German residential neighborhoods. Target: **100+ households** per logical neighborhood. **Specification-only — no code, no build tooling, no CI, no test framework.** Implementation work must start from `LOTSE-Requirements.md`.

## Source documents

- `LOTSE-Requirements.md` — single source of truth (Draft)
- `Brainstorming.md` — technical pre-design (architecture options, protocol design, hardware)
- `prototype-build.md` — hardware build plan with PlatformIO commands and flashing instructions

## Architecture invariant

**LOTSE is a signaling/coordination layer, not a device controller.** The LOTSE agent is a thin bridge between the neighborhood and the household's existing EMS (OpenEMS, evcc, Home Assistant, etc.). It never controls inverters, heat pumps, or wallboxes directly — all device control stays with the household's own system.

## Priority invariant (non-negotiable)

**Infrastructure Safety > Economic Fairness.** When grid limits are breached, controllable loads shed in this fixed order: EV wallbox → battery charging → heat pump. Balcony solar curtailed if reverse power flow limits exceeded.

## Phase structure

- **Phase 1 (Data Collection, minimum viable)**: Individual allocation — each agent self-regulates within its configured grid limit (from grid connection contract). No coordinator, no inter-household communication needed for grid protection.
- **Phase 2 (Coordination)**: Flexibility trading, local coordination, §14a grid-serving signals. Individual limits from Phase 1 remain the hard ceiling and fallback.

## Regulatory context & links

German energy law: §14a EnWG (grid-serving control), EEG (feed-in), MsbG (metering). The system deliberately avoids formal balancing-energy-sharing accounting.

- §14a EnWG — netzorientierte Steuerung: https://www.gesetze-im-internet.de/enwg_2005/__14a.html
- BNetzA §14a integration procedure: https://www.bundesnetzagentur.de/enwg14a
- MsbG (Messstellenbetriebsgesetz): https://www.gesetze-im-internet.de/messbg/
- BNetzA steuerbare VBE/Netzentgeltreduzierung: https://www.bundesnetzagentur.de/DE/Vportal/Energie/SteuerbareVBE/start.html

## Communication constraints (§4 NFRs)

- **No incoming ports**: All household communication outbound-only or dedicated local medium.
- **Range**: ≥100m through walls/cellars between any two households.
- **Ease**: No port forwarding, DDNS, or VPN — layperson-installable.
- Internet connections allowed if these constraints are met.

## Cost targets (Brainstorming §6)

Per-household hardware: €100–200 one-time (LilyGO T3 S3 + WattWächter TTL ~€46–52, fallback ESP32+SX1276+BPW40 ~€25). Central infrastructure: ≤€300 one-time (RPi + LoRa hat ~€70–105). Recurring: €0.

## Communication medium evaluation (Brainstorming §2, §9)

Six options evaluated against six constraints (C1–C6). **LoRa 868 MHz** ticks all boxes (~50 bytes per ~50s, 1% duty cycle). **MQTT over internet** mature but ~€3–4/mo VPS recurring. Architecture A (LoRa + coordinator) leads Phase 2 weighted matrix (153 pts); Architecture E (Phase 1 only) scores 158, validating Phase 1 suffices alone. Wrong directions: WiFi mesh (range), RS485 (cabling across properties), requiring EMS for participation, cloud dependency for grid protection.

## Protocol design (Brainstorming §4)

Transport-agnostic application-layer protocol with 7 message types: GridLimit, LoadShed, Par14aSignal, FlexOffer, FlexRequest, TariffInfo, Heartbeat (§4.1). Sketch MQTT topic structure in §2.3.

- **Serialization**: JSON or CBOR for MQTT; CBOR or custom binary for LoRa (a GridLimit message fits in ~25 bytes CBOR, 18 bytes custom binary) (§4.2).
- **Security**: TLS 1.3 for MQTT; AES-128-CCM for LoRa with per-household PSK, HMAC payload integrity, sequence number replay protection (§4.3).

## Open design decisions

These are documented in Brainstorming.md §8 and remain unresolved:

| # | Question | Status |
|---|----------|--------|
| Q1 | Communication medium (LoRa vs MQTT vs hybrid) | Open |
| Q2 | Coordinator placement (household / community / VPS / P2P / none) | Phase 1: none. Phase 2: Open |
| Q6 | Flex matching algorithm (FCFS / merit-order / proportional / priority / rotating) | Open |
| Q7 | Data retention (current only / local history / coordinator aggregate / opt-in) | Open |

## Referenced systems

- **OpenEMS** — open-source energy management system with MQTT and REST API
- **evcc** — EV charging controller, native MQTT API
- **Home Assistant** — home automation platform, MQTT and REST API
- **SML (Smart Message Language)** — protocol for German smart meters (IEC 62056-21), readable via IR phototransistor on UART/GPIO
- **OBIS codes** — standardized meter data IDs: 1.8.0 = total consumption, 2.8.0 = total feed-in, 16.7.0 = current power
- **EPEX Spot** — European power exchange, free day-ahead/intraday price data
- **LoRa 868 MHz** — EU ISM band, Semtech SX1276/SX1262 transceiver, 1% duty cycle per ETSI EN 300.220, AES-128 link-layer encryption
- **§14a EnWG modules** — Module 1 (flat kW reduction), Module 2 (percentage reduction), Module 3 (time-variable schedule)

Key OSS: **ESPHome** and **Tasmota** have built-in SML parsing. **RadioLib** and **Meshtastic** are mature LoRa stacks. **Common German smart meter brands** for testing: ISKRA, Landis+Gyr, Holley (Brainstorming §10).

## Household types (§2b)

See `LOTSE-Requirements.md` §2b for the full table (10 types from No PV to Balcony solar + Battery). Key constraint: each household must break even or benefit — optimization cannot cause financial loss relative to baseline (FR-06).
