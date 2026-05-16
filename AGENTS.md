# LEM2

Requirements-phase repository for a decentralized Local Energy Management System (LEM-Netz) for German residential neighborhoods. **Specification-only — no code, no build tooling, no CI, no test framework.** Implementation work must start from `LEM-Requirements.md`.

## Source documents

- `LEM-Requirements.md` — single source of truth (Draft)
- `Brainstorming.md` — technical pre-design (architecture options, protocol design, hardware)

## Architecture invariant

**LEM is a signaling/coordination layer, not a device controller.** The LEM agent is a thin bridge between the neighborhood and the household's existing EMS (OpenEMS, evcc, Home Assistant, etc.). It never controls inverters, heat pumps, or wallboxes directly — all device control stays with the household's own system.

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

## Cost targets & breakdown

Per `Brainstorming.md` §6.1–§6.3 and §3.1–§3.2, §5.5.

| Category | Target | Composition |
|----------|--------|-------------|
| Per-household hardware (one-time) | €100–200 | **Recommended (prototype→production):** LilyGO T3 S3 SX1262/SX1276 €22–28 + WattWächter TTL IR head €24 = €46–52. **Fallback:** ESP32 €5–15 + SX1276 €3–5 + BPW40 €0.50–2 = ~€25. Headroom €48–154 for enclosure/antenna/installation. |
| Central infrastructure (one-time) | ≤€300 | RPi 3B+ €35–40 (or RPi 4 €45–55) + LoRa hat €20–30 + SD card €8–10 + power/case €10–15 = €70–105. VPS alternative: ~€0–48/yr. |
| Recurring costs | €0 | LoRa: no subscriptions. MQTT-VPS: ~€3–4/month (violates target). All software OSS, EPEX Spot data free. |

## Communication medium options

Brainstorming.md §2 evaluates six options (LoRa 868 MHz, MQTT over internet, WiFi mesh, Powerline, Thread, RS485) against six hard constraints (C1–C6). **LoRa 868 MHz** ticks all boxes but has very low throughput (~50 bytes every ~50s, 1% duty cycle). **MQTT over internet** is mature but incurs recurring VPS cost (~€3–4/mo). A hybrid (LoRa for critical signals + MQTT for analytics) is also considered at +~€5/hh (§2.4).

**Architecture evaluation (Brainstorming §9):** For Phase 2, Architecture A (LoRa + lightweight coordinator) leads the weighted decision matrix at 153 points. Architecture E (Phase 1 only) scores 158 — validating Phase 1 is sufficient on its own. Wrong directions: WiFi mesh (range), RS485 (cabling across properties), requiring EMS for participation (excludes passive households), cloud dependency for grid protection (Phase 1 already solves it locally).

## Protocol design (Brainstorming §4)

Transport-agnostic application-layer protocol with 7 message types: GridLimit, LoadShed, Par14aSignal, FlexOffer, FlexRequest, TariffInfo, Heartbeat (§4.1). Sketch MQTT topic structure in §2.3.

- **Serialization**: JSON or CBOR for MQTT; CBOR or custom binary for LoRa (a GridLimit message fits in ~25 bytes CBOR, 18 bytes custom binary) (§4.2).
- **Security**: TLS 1.3 for MQTT; AES-128-CCM for LoRa with per-household PSK, HMAC payload integrity, sequence number replay protection (§4.3).

## Open design decisions

These are documented in Brainstorming.md §8 and remain unresolved:

| # | Question | Status |
|---|----------|--------|
| Q1 | Communication medium (LoRa vs MQTT vs hybrid) | 🔄 Open |
| Q2 | Coordinator placement (household / community / VPS / P2P / none) | Phase 1: none. Phase 2: 🔄 Open |
| Q6 | Flex matching algorithm (FCFS / merit-order / proportional / priority / rotating) | 🔄 Open |
| Q7 | Data retention (current only / local history / coordinator aggregate / opt-in) | 🔄 Open |

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

## Recommended next step (Brainstorming §10)

Build one agent prototype (LilyGO T3 S3 SX1262/SX1276 + WattWächter TTL IR head + SML parsing on real or simulated meter — see prototype-build.md), build coordinator prototype (second T3 S3 or RPi + LoRa hat), test range in a real neighborhood.

## Household types (§2b)

| Type | Pricing Model | Optimization Goal |
|------|---------------|-------------------|
| No PV | Fixed tariff | Minimize consumption cost |
| PV only (EEG) | Fixed feed-in | Maximize self-consumption |
| PV only (Dynamic) | EPEX Spot | Shift consumption to low-price periods |
| PV + Battery | Dynamic | Arbitrage (charge low, discharge high) |
| Battery only | Dynamic | Arbitrage (charge cheap, discharge expensive) |
| Heat pump | §14a network charges | Shift to low-tariff periods |
| EV + Wallbox | Dynamic | Coordinate charging with price signals |
| EV + Wallbox + Heat pump + Battery | Mixed | Full optimization across all assets |
| Balcony solar (Balkonkraftwerk) | Self-consumption | Maximize generation, curtail if grid export limit exceeded |
| Balcony solar + Battery | Dynamic | Self-consumption + arbitrage |

Each household must break even or benefit — optimization cannot cause financial loss relative to baseline (§2a, FR-06).
