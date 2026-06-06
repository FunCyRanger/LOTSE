# Technical Concept Brainstorming

**Status:** Phase 1 data bridge — design complete, build in progress (Heltec V3). Phase 2 coordination deferred.
**Based on:** `Requirements.md` (Draft)

---

## 1. Architecture Overview

The system is a **signaling and coordination layer** between autonomous household energy management systems. It does not control end devices. 

Phase 1 is a **data transport pipeline**: relay IR sensor readings from a smart meter to Home Assistant via a LoRa mesh bridge. No local limit enforcement, no inter-household coordination, no device control. Implemented on Heltec V3 hardware with a Meshtastic firmware fork: the ingress node runs a SoftAP HTTP endpoint at `POST /api/v1/meter`, accepts Tasmota IR sensor data, and re-broadcasts it over the LoRa mesh. An egress node receives LoRa packets and forwards them to Home Assistant via MQTT/REST.

```
PHASE 1 (Data Bridge):
                          LoRa mesh (Meshtastic)
                              │
              HTTP POST       │ LoRa
┌──────────┐   /api/v1/meter  │         ┌─────────────────┐
│ Tasmota  │─────►┌─────────────┐       │ Heltec V3       │
│ IR sensor│SoftAP│ Heltec V3   │───────│ (egress)        │───► Home Assistant
│ meter    │      │ (ingress)   │ LoRa  │ WiFi station    │     MQTT/REST
└──────────┘      │ SoftAP HTTP │       │ LoRa RX         │
                  └─────────────┘       └─────────────────┘
No local limit enforcement, no inter-household coordination.
Meter data: forwarded from IR sensor through LoRa to Home Assistant.

PHASE 2 (adds Coordination):
                     ┌─────────────────────────┐
                     │ Optional: Coordinator   │
                     │ (flex matching, §14a)   │
                     └────────────┬────────────┘
                                  │ (or peer-to-peer)
                    ┌─────────────┼─────────────┐
                    │             │             │
             ┌──────┴──────┐ ┌───┴───────┐ ┌───┴───────┐
             │ Agent HH-01 │ │Agent HH-02│ │Agent HH-03│
             │ + offers    │ │ + buys    │ │ + sells   │
             └──────┬──────┘ └───┬───────┘ └───┬───────┘
                    │ local      │ local       │ local
             ┌──────┴──────┐ ┌───┴───────┐ ┌───┴───────┐
             │ Home EMS    │ │ Home EMS  │ │ Home EMS  │
             │ + flex resp.│ │ + flex    │ │ + flex    │
             └─────────────┘ └───────────┘ └───────────┘
```

**Signal types (transport-agnostic). Phase 1 signals are local (agent ↔ home EMS). Phase 2 signals add the inter-household dimension:**

| Priority | Signal | Phase | Direction | Binding? | Description |
|----------|--------|-------|-----------|----------|-------------|
| 1 | Grid Limit | P1+P2 | Pre-configured locally | ✅ Yes | Per-household import/export limit from grid connection |
| 2 | Load Shed | P2 | Agent ↔ Agent or via coordinator | ⚠️ Hard recommendation | Shed order: wallbox → battery → heat pump |
| 3 | §14a Signal | P2 | SMGW/Steuerbox → household EMS (independent of the system) | ✅ Yes if §14a active | Module 1/2/3 reduction signal. The system is not in this path — see §14a context in §7 |
| 4 | Flex Offer | P2 | Agent ↔ Agent or via coordinator | ❌ Voluntary | "I can shift 3 kW for 1h at 14:00" |
| 5 | Flex Request | P2 | Agent ↔ Agent or via coordinator | ❌ Voluntary | "Need 5 kW reduction, who can help?" |
| 6 | Tariff/Price | P1+P2 | Pre-configured or broadcast | ❌ Informational | EPEX Spot, TOU periods |
| 7 | Health/Status | P1+P2 | Agent → neighbor | ❌ Informational | Heartbeat, connection state |

---

## 2. Communication Medium Options

Every option evaluated against the hard constraints from Requirements.md §4 NFRs.

### 2.1 Constraint Summary

| # | Constraint | Implication |
|---|-----------|-------------|
| C1 | No incoming ports at households | Outbound-only or dedicated medium |
| C2 | ≥100m through walls/cellars | Needs sub-GHz or wired for guaranteed reliability |
| C3 | No DDNS, no VPN, no port forwarding | Zero network configuration |
| C4 | €0 recurring | No cloud subscriptions, no VPS |
| C5 | €100-200/hh hardware one-time | Components + sensor + installation |

**Phase 1 solution:** The agent provides a SoftAP WiFi network (192.168.4.1) that devices within the household (Tasmota IR sensor, configuration phone/laptop) connect to. The device itself has no incoming ports from outside the household. For the LoRa path, the Meshtastic mesh handles all inter-node communication — no IP routing needed.
| C6 | ≤€300 central infra one-time | Coordinator hardware |

### 2.2 Option Comparison

| Option | C1 no ports | C2 100m+walls | C3 zero-config | C4 €0 recurring | C5 €/hh | C6 € central | Overall bandwidth |
|--------|-------------|---------------|----------------|-----------------|---------|--------------|-------------------|
| **LoRa 868 MHz** | ✅ Radio, no IP stack | ✅ km range, excellent through masonry | ✅ Power on, no config | ✅ None needed | €10-15 | ~€80 | Very low (300bps-50kbps) |
| **MQTT over internet** | ✅ Outbound TCP | ✅ Uses home WiFi + internet | ⚠️ Needs WiFi + broker reachable | ❌ Broker VPS ~€3-4/mo | €15-25 | ~€0 | High |
| **Local WiFi mesh** | ⚠️ Local only | ❌ 2.4GHz dies in cellars | ❌ Multiple APs, mesh config needed | ✅ None | €15-25 | ~€80 | High |
| **Powerline (PLC)** | ✅ Uses electrical wiring | ✅ Same low-voltage grid | ✅ Plug in | ✅ None | €25-50 | ~€100 | Medium |
| **Thread/Matter mesh** | ✅ Local mesh | ❌ ~30m per hop, walls reduce drastically | ❌ Border router + commissioning needed | ✅ None | €15-25 | ~€50 | Medium |
| **RS485 wired** | ✅ Physical wire | ✅ Up to 1200m | ❌ Cable laying across properties | ✅ None | €5-10 | ~€30 | Medium |

### 2.4 Hybrid Possibility

A two-layer approach could combine strengths:

| Function | Primary link | Fallback |
|----------|-------------|----------|
| Grid limit broadcast | LoRa (guaranteed) | MQTT over internet (if available) |
| Load shed signal | LoRa (guaranteed) | MQTT over internet |
| Flex offers | LoRa or MQTT (whichever available) | — |
| §14a signals | LoRa or MQTT | — |
| Detailed analytics / UI | MQTT over internet (if available) | Local-only |

This gives reliability for critical signals while using internet for convenience features. Cost increase: ~€5/hh for the LoRa module.

---

## 3. Agent Hardware Options

### 3.1 Candidate Comparison

| Component | MCU | WiFi | LoRa | Smart meter IR | GPIO | Cost | Processing |
|-----------|-----|------|------|---------------|------|------|------------|
| **ESP32** | Xtensa dual 240MHz | ✅ Built-in | ✅ Via SX1276 | ✅ UART | Many | €5-15 | Sufficient for signaling |
| **ESP32-C6** | RISC-V 160MHz | ✅ | ✅ Via SX1276 | ✅ UART | Many | €7-12 | Sufficient + Thread |
| **RPi Zero 2W** | ARM quad 1GHz | ✅ | Via USB/SPI | Via GPIO USB | Few | €15-30 | Full Linux, MQTT native |
| **RPi 3B+** | ARM quad 1.4GHz | ✅ | Via HAT | Via GPIO/USB | Few | €35-45 | Overkill for agent |

### 3.2 Smart Meter Reading

Reading a German smart meter via its optical IR interface is a solved problem:

1. **IR phototransistor** (BPW40 or TEKT5400S, €0.50-2) connected to UART of ESP32 or GPIO of RPi
2. **SML protocol** (Smart Message Language) — the standard for German meters
3. **Parsing**: Extract OBIS codes — total consumption (1.8.0), total feed-in (2.8.0), current power (16.7.0, 36.7.0, etc.)
4. **Existing OSS**: ESPHome has built-in SML platform, Tasmota supports it, standalone Arduino sketches exist

**Example: ESP32 + IR reader (lowest cost: ~€12)**
- ESP32-WROOM: €6
- SX1276 LoRa module: €4
- BPW40 phototransistor + resistors: €1
- USB power supply (existing): €0
- **Total: ~€11**

**Example: RPi Zero 2W + IR reader (higher capability: ~€22)**
- RPi Zero 2W: €17
- USB LoRa dongle: €4
- IR sensor: €1
- **Total: ~€22**

### 3.3 Home EMS Integration

The agent must communicate with whatever EMS the household runs. Three cases:

| Household EMS | Integration method | Protocol | Reliability |
|--------------|-------------------|----------|-------------|
| **OpenEMS** | MQTT API or REST API | MQTT or HTTP | Native, documented |
| **evcc** | MQTT API | MQTT | Native, documented |
| **Home Assistant** | MQTT or REST API | MQTT or HTTP | Native, documented |
| **None / unknown** | No integration possible | — | Agent acts standalone, no opt-in from home EMS |

If no home EMS exists, the agent can still:
- Read the smart meter
- Display grid limit to the user (web page, small display)
- Participate in grid protection at a basic level
- But cannot influence device behavior (since there's no EMS to coordinate with)

### 3.4 German Compliance & Availability

All referenced hardware components must be CE-certified and available through German distributors. The table below summarizes compliance status and typical German sources:

| Component | CE/RED | ETSI | German distributors |
|-----------|--------|------|---------------------|
| ESP32-WROOM (Espressif) | ✅ CE certified | ✅ EN 300.328 (WiFi) | Conrad, Reichelt, RS Components, Mouser DE |
| SX1276 (Semtech) | ✅ CE certified | ✅ EN 300.220 (868 MHz) | RS Components DE, Mouser DE, Farnell DE |
| BPW40 / TEKT5400S | ✅ Passive component | N/A | Conrad, Reichelt |
| Raspberry Pi (any) | ✅ CE certified | ✅ EN 55032/55035 | Conrad, Reichelt, RS Components |

**LoRa 868 MHz**: The 868 MHz band is license-free in the EU. Semtech SX1276/SX1262 transceivers are designed for ETSI EN 300.220 compliance (1% duty cycle, +14/+20 dBm output power limits). The radio equipment directive 2014/53/EU (RED) applies.

**Smart meter IR reading**: Reading one's own meter data via the optical IR interface is permitted under German metering law (MsbG). Conditions:
- Read-only access via the IR/D0 interface (DIN EN 62056-21)
- No removal of tamper seals
- No opening of the meter housing
- No modification to the metering equipment
- The PIN for enhanced data (current power, historic values) can be requested from the meter operator (Messstellenbetreiber)

**Data protection**: Local data processing is preferred over cloud transmission to comply with GDPR data minimization principles and MsbG data processing rules (§§ 49–70 MsbG). The system's outbound-only communication constraint (Requirements.md §4 NFRs, constraint C1) inherently reduces the attack surface for personal data.

---

## 5. Coordinator Design

### 5.1 Phase 1: No Coordinator Needed

With **individual allocation**, each household's agent operates independently:
- Limit is configured locally per household (from grid connection contract)
- Agent reads smart meter, compares to limit
- Signals the home EMS: "stay within your limit"
- No inter-household communication, no central device, no coordinator

Grid protection works fully offline, fully locally, at every household.

### 5.2 Phase 2: Optional Coordinator

In Phase 2, a coordinator (or P2P coordination) is needed for functions that span households:

| Function | Requires coordinator? | Alternative |
|----------|----------------------|-------------|
| Flex offer/request matching | ✅ Central matching simpler | P2P gossip (agents broadcast offers, respond directly) |
| Load shed coordination | ✅ Central broadcast simpler | P2P flood (each agent propagates signal) |
| §14a external signal ingress | ✅ Single entry point needed | Any agent with internet can receive and propagate |
| Aggregate load monitoring | ✅ Central aggregation simpler | Gossip (each agent shares its load, peers sum locally) |
| Tariff information | ❌ | Each agent can fetch EPEX Spot independently |

### 5.3 Coordinator Options (Phase 2)

| Location | Pros | Cons |
|----------|------|------|
| **At one household** | No extra internet cost | Single point of failure, trust concern |
| **Transformer room / common space** | Neutral location | Requires permission |
| **Cloud VPS** | Always reachable | Recurring cost (€3-4/mo), GDPR |
| **Software instance (any device)** | Runs on existing RPi at any household | Same as "at one household" |
| **Fully P2P (no coordinator)** | Most robust, no central trust | More complex to implement; O(n²) message complexity scales poorly beyond ~30 nodes |

**Coordinator scaling for 100+ households:** A coordinator for 100 agents must handle peak flex-offer bursts — e.g., 100 offers arriving within one tariff period. Merit-order matching (sort 100 offers by price) completes in milliseconds on any modern RPi. The CPU/memory bottleneck is not the matching algorithm but the network I/O: an MQTT-based coordinator handles 100 clients trivially; a LoRa-based coordinator needs a TDMA schedule where each agent gets a dedicated transmission slot, extending the round-robin cycle proportionally to agent count.

### 5.4 Graceful Degradation (Phase 2)

Phase 2 coordination depends on the coordinator or P2P network. If it fails, each agent falls back to its Phase 1 individual limit — grid protection is unaffected.

### 5.5 Coordinator Hardware (if needed in Phase 2)

| Component | Cost | Notes |
|-----------|------|-------|
| Raspberry Pi 3B+ | €35-40 | Sufficient for signaling |
| Raspberry Pi 4 (2GB) | €45-55 | More headroom for data logging |
| LoRa hat / HAT | €20-30 | If using LoRa for Phase 2 comms |
| SD Card (32GB) | €8-10 | |
| Power supply + case | €10-15 | |
| **Total RPi 3B+ + LoRa** | **€70-85** | Within €300 budget |
| **Total RPi 4 + LoRa** | **€85-105** | Still well within budget |

---

## 7. Phase 1 → Phase 2 Path

### Phase 1 (Minimum Viable: Grid Protection + Measurement)

```
┌──────────────────────────────────────────────────────┐
│ Phase 1 — Individual Allocation                       │
│                                                       │
│ No coordinator needed.                                │
│                                                       │
│ Agent (per household):                                │
│  - Configured with individual grid limit              │
│    (from grid connection contract or neighborhood     │
│     agreement)                                        │
│  - Read smart meter (consumption, generation via SML) │
│  - Compare current load to configured limit           │
│  - Forward limit + current load to home EMS           │
│    (MQTT/REST within the household)                   │
│  - If limit is reached, signal the home EMS to shed   │
│  - Each agent is fully independent — no               │
│    inter-household communication needed               │
│                                                       │
│ Validation:                                           │
│  - Does the agent correctly read the smart meter?     │
│  - Does the household EMS receive and respect the     │
│    limit signal?                                      │
│  - How does the household behave when the limit is    │
│    approached or breached?                            │
└──────────────────────────────────────────────────────┘
```

**Deliverable**: Each household independently respects its grid limit. No flexibility trading yet. No inter-household communication. This is the foundation.

### Phase 2 (Full: Flexibility Coordination + §14a)

```
┌──────────────────────────────────────────────────────┐
│ Phase 2 (adds to Phase 1)                             │
│                                                       │
│ Adds inter-household communication layer:              │
│  - Agents exchange flexibility offers and requests    │
│  - Optional coordinator for offer matching (or P2P)   │
 │  - §14a awareness: the system may receive §14a state from     │
│    household EMS (which gets it via SMGW/Steuerbox)    │
│  - Collective load shed coordination                   │
│                                                       │
│ Individual limits from Phase 1 remain the hard        │
│ ceiling — flex trading only uses headroom within      │
│ those limits.                                         │
│                                                       │
│ Agent additions:                                      │
│  - Calculate available flexibility (headroom to       │
│    individual limit)                                  │
│  - Submit flex offers to peers or coordinator         │
│  - Optionally read §14a state from home EMS for       │
│    coordination optimization (informational only)      │
│  - Track financial impact vs baseline                 │
│  - Opt-out per household                              │
│                                                       │
│ Fairness validation:                                  │
│  - Each agent computes: would I have done better       │
 │    without system coordination?                          │
│  - If any household loses, coordination is adjusted   │
│                                                       │
│ Graceful degradation:                                 │
│  - If coordinator or P2P network fails, each agent    │
│    falls back to Phase 1: self-regulate within        │
│    individual limit. Grid protection is unaffected.   │
└──────────────────────────────────────────────────────┘
```

### 7.1 §14a Context — Where the System Fits

§14a EnWG (grid-serving control) is implemented through the smart meter infrastructure, independently of the system:

```
Grid operator → SMGW (Smart Meter Gateway) → Steuerbox → EEBUS/relay → device or EMS
```

- The Steuerbox lives in the meter cabinet (Zählerschrank), installed by the Messstellenbetreiber.
- For **direct control**: the Steuerbox switches a relay contact (230V) that reduces the device to 4.2 kW.
- For **EMS-based control**: the Steuerbox sends the signal via EEBUS (VDE-AR-E 2829-6) to a certified household EMS (e.g. E3/DC, Loxone), which then distributes the reduction across its managed devices.

The system is **not in this signal path**. The household EMS receives §14a commands directly from the Steuerbox — it has no role in the certified control loop. However:

1. **Coexistence is straightforward**: the system signals the same EMS (via MQTT/REST) with coordination offers and grid limit info. The EMS reconciles both inputs autonomously — it decides how to split 4.2 kW across devices during a §14a event while respecting the system's neighborhood coordination goals.
2. **Optional system awareness**: The EMS can expose its current §14a state to the system agent (e.g. "§14a active, 4.2 kW limit"), allowing the coordinator to factor this into flex matching. This is informational only — the system never originates or relays §14a commands.
3. **No certification needed**: Because the system is not in the §14a signal path, it does not require §14a certification per BK6-22-300.

**Implication for application protocol:** The `Par14aSignal` message is informational (household-EMS → agent), not a §14a distribution channel. No changes to the Phase 1 or Phase 2 grid protection model are needed — the Phase 1 individual limit already provides local grid protection independent of §14a.

---

## 8. Open Questions

These need decisions before implementation starts. Entries accumulate discussion notes as they are explored.

### Q1: Communication medium

**Options**: LoRa 868 MHz / MQTT over internet / WiFi mesh / Powerline / Thread / RS485 / Hybrid

**Discussion notes**:
- Data volumes are tiny (grid limits, flex offers, tariff info — typically <100 bytes per message)
- Key constraints: no incoming ports, ≥100m through walls/cellars, easy setup, €0 recurring preferred
- LoRa ticks all boxes but has very low bandwidth (~50 bytes every ~50s) and duty cycle limits (1% ETSI)
- MQTT over internet is mature and agents connect outbound, but needs a reachable broker (VPS ~€3-4/mo = recurring cost, or one household opens a port = violates constraint)
- WiFi mesh unlikely to work reliably through German residential construction at 100m
- Powerline possible but expensive modules and interference risk from PV inverters
- RS485 excellent technically but cabling impractical across private property
- **Decision**: We chose **Architecture F (LoRa + Meshtastic fork)** as the Phase 1 transport layer. The Meshtastic firmware provides LoRa mesh routing, AES encryption, MQTT bridging, and the HTTP server extension point for meter data injection — all on the same Heltec V3 hardware. This avoids building a custom protocol stack from scratch (see `prototype-build.md §P5` for fork status).

### Q2: Where does the coordinator live?

**Options**: At one household / community space / VPS / fully decentralized (no coordinator) / soft witness only

**Discussion notes**:
- A full central coordinator is not the only model. Possibilities range from a "soft witness" (just publishes aggregate transformer load) to fully peer-to-peer
- In a P2P system, each agent needs to know the total neighborhood load to self-regulate — approaches include individual allocation, gossip aggregation, or a soft witness
- Fully decentralized avoids single point of failure and trust issues but adds complexity (discovery, consensus, eventual consistency)
- Soft witness model (one agent at transformer publishes only aggregate load, no authority) is a middle ground — removes coordinator authority without full P2P complexity
- **Phase 1: No coordinator needed at all** — each agent self-regulates within its configured individual limit
- Phase 2: Coordinator or P2P coordination may be added for flexibility trading, but is not required for grid protection
- **Status**: ⏳ Phase 1: no coordinator. Phase 2: to be decided.

### Q3: Does every household need a dedicated agent device?

**Options**: Dedicated device / Share with existing hardware / Hybrid

**Discussion notes**:
- Many households already run a Raspberry Pi for evcc, Home Assistant, or OpenEMS — the agent could be a software component on that hardware
- Smart meter reading is within the same household, so local connectivity (serial, WiFi, Bluetooth) is sufficient — no range issue
- Cost target (€100-200/hh) is generous enough that a dedicated €15-25 device is negligible if desired
- Hybrid approach possible: agent software on existing hardware, add cheap ESP32 just for IR meter reading
- **Status**: ✅ Both approaches valid — depends on household environment. No single decision needed.

### Q4: How is the grid limit determined?

**Options**: Manual config (transformer rating) / Supply contract capacity / Transformer meter reading / Aggregator data / Distributed estimation

**Discussion notes**:
- Phase 1: Use individual household limits configured from each household's grid connection contract or neighborhood agreement. Simple, static, no dependencies.
  - Each agent knows its own limit, self-regulates locally
  - No transformer meter needed, no grid operator permission required
  - Possible to define via net provider (each household already has a contractual max. connection power)
- Phase 2: Revisit this — could be upgraded to transformer meter reading or grid operator API for dynamic adaptation
- **Status**: ✅ Phase 1: individual household limits (configured per agent). Phase 2: to be clarified later.

### Q5: What if a household has no home EMS?

**Options**: Agent still works (passive mode) / Require EMS for participation

**Discussion notes**:
- A household without EMS is still a valuable participant: smart meter data contributes to neighborhood aggregate, grid limit can be displayed to the user
- Agent works fully on the input side (meter reading, receiving signals), partially on the output side (can't auto-respond, user acts on alerts)
- Phase 1: no EMS required for onboarding — meter reading + limit display works standalone
- Phase 2: EMS integration is an upgrade for households that want automated response; those without EMS remain passive participants
- **Status**: ✅ No EMS = passive participation. Agent works for everyone; EMS is optional upgrade.

### Q6: Flexibility matching algorithm?

**Options**: First-come-first-served / Merit-order (cheapest first) / Proportional sharing / Priority-based (load shed order) / Rotating priority (round-robin)

**Discussion notes**:
- Phase 2 detail, not needed for Phase 1
- **First-come-first-served**: Earliest offer wins. Simplest to implement, but may systematically favor fast-responding households and create unfair allocation patterns over time.
- **Merit-order (cheapest first)**: Sort all offers by price, accept cheapest until demand is met. Economically optimal, but risks always picking the same households (e.g., those with large batteries), concentrating the burden on few participants.
- **Proportional sharing**: Each household contributes a percentage of their offered flexibility. Fair in terms of load distribution, but doesn't consider that some flexibility is cheaper or more valuable (e.g., battery vs heat pump).
- **Priority-based (load shed order)**: Match according to the fixed priority — wallbox flexibility first, then battery, then heat pump. Aligns naturally with the grid protection invariant (same shed order from FR/UC-04), but ignores price signals.
- **Rotating priority**: Round-robin across households over days. Ensures long-term fairness, each household takes turns. Complex to coordinate and may not align with real-time grid needs.
- **Status**: 🔄 Open — to be decided when Phase 2 is designed

### Q7: Data retention?

**Options**: Only current values / Each agent stores own history / Coordinator stores aggregate history / Optional opt-in logging

**Discussion notes**:
- **Only current values, no history**: Maximum privacy, minimal resource usage. No debugging capability, no optimization history, no audit trail. Hard to verify long-term coordination effects without any record.
- **Each agent stores own history**: Data stays in the household (GDPR-friendly). Enables local trend analysis and fairness validation. Data survives coordinator failure. If the agent device fails, history is lost unless backed up.
- **Coordinator stores aggregate history**: Enables neighborhood-level trend analysis, transformer load profiles, and system optimization over time. Privacy concern — must only store aggregate (sum of all households), never per-household data, or require explicit consent.
- **Optional opt-in logging**: Household chooses whether to contribute data. Most flexible but adds permission complexity. Households without logging can still benefit from the system; those with logging help improve coordination over time.
- Current values are sufficient for grid protection (Phase 1). History becomes relevant for fairness validation and optimization tuning (Phase 2).
- **Status**: 🔄 Open

### Q8: Physical security of coordinator?

**Options**: Locked box at transformer / In someone's home / Weatherproof enclosure / VPS hosting / Not applicable (fully decentralized)

**Discussion notes**:
- Depends on Q1 (communication medium) and Q2 (coordinator placement) — both still open
- If **fully decentralized** (Q2): no coordinator device exists, Q8 is moot
- If **soft witness** only (Q2): one small device (ESP32 + LoRa) at transformer, publishes aggregate load. Low value target. Locked box is sufficient.
- If **coordinator at a household**: physical security is the household's normal home security — no extra measures needed
- If **coordinator on VPS** (Q1 internet): physical security is the cloud provider's problem
- If **coordinator in community/transformer space**: needs locked, weatherproof enclosure
- **Status**: 🔄 Open — depends on Q1 and Q2 decisions

