# Agent Instructions

Specification-only repository for a decentralized neighborhood energy coordination system. **100+ households** per logical neighborhood. **No code, no build tooling, no CI, no test framework.** All work is in Markdown. **Do not write code, generate build files, or add CI/CD configurations.**

## Source documents

| File | What it contains |
|------|-----------------|
| `Requirements.md` | Single source of truth — requirements, use cases, priority hierarchy (Draft) |
| `Brainstorming.md` | Technical pre-design — architecture, protocol, hardware evaluation, open decisions (§8) |
| `prototype-build.md` | Hardware build plan — BOM, circuit, PlatformIO commands, flashing guide |
| `README.md` | Project overview, architecture diagrams, technical direction table |
| `20260517 AI review/Claude.md` | AI review — concrete errors found in prototype-build.md (OBIS codes, library IDs, baud rate) |
| `20260517 AI review/Grok.md` | AI review — feasibility assessment and recommendations |

## Architecture invariants

- **Signaling/coordination layer only** — never controls inverters, heat pumps, or wallboxes directly. All device control stays with the household's own EMS (OpenEMS, evcc, Home Assistant).
- **Infrastructure Safety > Economic Fairness** — load shed order: EV wallbox → battery charging → heat pump. Balcony solar curtailed if reverse power flow limits exceeded (non-negotiable).
- **Phase 1**: Individual allocation, no inter-household communication needed. **Phase 2**: flexibility trading + §14a signals added; Phase 1 limits remain hard ceiling.
- **FR-06**: Each household must break even or benefit vs. baseline. See §2b for 10 household types.
- No balancing-energy-sharing accounting (deliberate).

## Communication constraints

- No incoming ports (outbound-only or dedicated local medium). ≥100m through walls/cellars. No port forwarding, DDNS, or VPN. Internet connections allowed if constraints met.
- Preferred transport: LoRa 868 MHz (~50 bytes per ~50s, 1% duty cycle). See Brainstorming §2/§9 for full evaluation.

## Open design decisions (Brainstorming §8)

| # | Question | Status |
|---|----------|--------|
| Q1 | Communication medium (LoRa vs MQTT vs hybrid) | Open |
| Q2 | Coordinator placement | Phase 1: none. Phase 2: Open |
| Q3 | Dedicated agent device per household? | Both approaches valid — no single decision needed |
| Q4 | How is grid limit determined? | Phase 1: individual household limits (configured per agent) |
| Q5 | Household without home EMS? | Passive participation (meter reading + alerts, no auto-response) |
| Q6 | Flex matching algorithm | Open |
| Q7 | Data retention | Open |
| Q8 | Physical security of coordinator | Depends on Q1/Q2 outcomes |

## Protocol (Brainstorming §4)

7 message types: GridLimit, LoadShed, Par14aSignal, FlexOffer, FlexRequest, TariffInfo, Heartbeat. Transport-agnostic. JSON/CBOR for MQTT; CBOR/custom binary for LoRa. Security: TLS 1.3 (MQTT) or AES-128-CCM + per-household PSK + HMAC + sequence number (LoRa).

## Known errors (from AI reviews)

The `20260517 AI review/Claude.md` review found errors in `prototype-build.md`. These are verified fixes an agent should carry forward:
- **Wrong PlatformIO library ID**: `m-/SML` is not a valid registry name. Use **`mzi_/sml`** instead.
- **Baud rate mismatch**: Holley DTZ541 runs at **115200 baud** but firmware defaults to 9600. Handle per-meter baud config.
- **Phase inconsistency**: Prototype steps P3–P5 test inter-household LoRa (Phase 2 infra) but are labeled Phase 1 validation. Phase 1 has no inter-household communication.

OBIS codes in the current `prototype-build.md` §P2.1 have been corrected per review (code `36.7.0` replaced with `-1:16.7.0`).

## Regulatory cross-references

- §14a EnWG (grid-serving control): https://www.gesetze-im-internet.de/enwg_2005/__14a.html
- BNetzA §14a procedure: https://www.bundesnetzagentur.de/enwg14a
- MsbG (metering): https://www.gesetze-im-internet.de/messbg/
- BNetzA steuerbare VBE: https://www.bundesnetzagentur.de/DE/Vportal/Energie/SteuerbareVBE/start.html

## Key referenced systems

- **OpenEMS**, **evcc**, **Home Assistant** — household EMS (MQTT/REST API)
- **SML** (IEC 62056-21) — German smart meter protocol via IR/UART; OBIS codes: 1.8.0 (total consumption), 2.8.0 (total feed-in), 16.7.0 (current power)
- **EPEX Spot** — free day-ahead/intraday data
- **RadioLib**, **Meshtastic** — LoRa stacks
- **ESPHome**, **Tasmota** — built-in SML parsing

## Cost targets

Per household: €100–200 one-time (prototype BOM ~€46–55 with LilyGO T3 S3 + WattWächter TTL). Central: ≤€300 one-time. Recurring: €0.

## Git history note

Earlier commits reference the `LEM2` name.
