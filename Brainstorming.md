# Technical Concept Brainstorming: LEM-Netz

**Status:** Brainstorming / Pre-design
**Based on:** `LEM-Requirements.md` (Draft)

---

## 1. Architecture Overview

The LEM is a **signaling and coordination layer** between autonomous household energy management systems. It does not control end devices. The topology has two tiers:

```
                     ┌─────────────────────────┐
                     │  Neighborhood            │
                     │  Coordinator             │
                     │  (grid limit, flex       │
                     │   matching, §14a fwd)    │
                     └────────────┬────────────┘
                                  │ communication link
                    ┌─────────────┼─────────────┐
                    │             │             │
             ┌──────┴──────┐ ┌───┴───────┐ ┌───┴───────┐
             │ Agent HH-01 │ │Agent HH-02│ │Agent HH-03│
             │ (thin       │ │           │ │           │
             │  bridge)    │ │           │ │           │
             └──────┬──────┘ └───┬───────┘ └───┬───────┘
                    │ local      │ local       │ local
                    │ MQTT/REST  │ MQTT/REST   │ MQTT/REST
             ┌──────┴──────┐ ┌───┴───────┐ ┌───┴───────┐
             │ Home EMS    │ │ Home EMS  │ │ Home EMS  │
             │ (OpenEMS/   │ │ (evcc/    │ │ (HA/       │
             │  evcc/HA)   │ │  OpenEMS) │ │  none)     │
             │ Controls:   │ │           │ │           │
             │ PV, batt,   │ │ Wallbox,  │ │ Heat pump │
             │ HP, EV      │ │ PV        │ │           │
             └─────────────┘ └───────────┘ └───────────┘
```

**Signal types flowing across the link (transport-agnostic):**

| Priority | Signal | Direction | Binding? | Description |
|----------|--------|-----------|----------|-------------|
| 1 | Grid Limit | Coordinator → Agents | ✅ Yes | Max net import/export for the branch |
| 2 | Load Shed | Coordinator → Agents | ⚠️ Hard recommendation | Shed order: wallbox → battery → heat pump |
| 3 | §14a Signal | Coordinator → Agents | ✅ Yes if §14a active | Module 1/2/3 reduction signal |
| 4 | Flex Offer | Agent → Coordinator | ❌ Voluntary | "I can shift 3 kW for 1h at 14:00" |
| 5 | Flex Request | Coordinator → Agent | ❌ Voluntary | "Need 5 kW reduction, who can help?" |
| 6 | Tariff/Price | Coordinator → Agents | ❌ Informational | EPEX Spot, TOU periods |
| 7 | Health/Status | Bidirectional | ❌ Informational | Heartbeat, connection state |

---

## 2. Communication Medium Options

Every option evaluated against the hard constraints from §4 NFRs.

### 2.1 Constraint Summary

| # | Constraint | Implication |
|---|-----------|-------------|
| C1 | No incoming ports at households | Outbound-only or dedicated medium |
| C2 | ≥100m through walls/cellars | Needs sub-GHz or wired for guaranteed reliability |
| C3 | No DDNS, no VPN, no port forwarding | Zero network configuration |
| C4 | €0 recurring | No cloud subscriptions, no VPS |
| C5 | €100-200/hh hardware one-time | Components + sensor + installation |
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

### 2.3 Detailed Assessment

#### LoRa 868 MHz

**How it works**: ESP32 + Semtech SX1276/SX1262 transceiver. Operates in EU 868 MHz ISM band (license-free). Star topology with coordinator as gateway, or peer-to-peer.

**Range**: 1-5 km line of sight, 200-500m through dense urban construction. Easily satisfies 100m through walls/cellars.

**Bandwidth constraints**: Duty cycle limited to 1% (ETSI EN 300.220). At SF7 this gives ~50 bytes every ~50 seconds per device. Sufficient for:
- Grid limit broadcast (50 bytes, every few minutes)
- Flex offer/request (50-100 bytes, occasional)
- Load shed signal (30 bytes, rare)
- §14a signal (30 bytes, hourly)

Not sufficient for: raw meter time series, large config transfers, firmware updates.

**Security**: AES-128 encryption at link layer. No IP-based attack surface (no TCP/IP stack). Physical range limits eavesdropping.

**Cost**: SX1276 module €3-5, ESP32 €5-8, IR sensor €1-2 = **€10-15/hh**. Coordinator: RPi 3B €40 + LoRa hat €25 + SD card €10 = **€75**.

**Maturity**: ESP32+LoRa is mature in OSS (Meshtastic, RadioLib, ESP-IDF). Many open SML meter readers exist for ESP32.

**Key tradeoff**: Very low throughput limits message frequency and payload size. Not suitable if agents need to exchange detailed data frequently.

---

#### MQTT over Internet

**How it works**: Each agent connects via outbound MQTT over TLS to a reachable broker. The coordinator also connects to the same broker. All traffic is via the broker — no household opens ports. Uses the household's existing internet connection.

**Broker placement**:
- **VPS** (€3-4/month on Hetzner/Hetzner): violates C4 (€0 recurring), but avoids any household needing ports
- **Local RPi + DDNS**: requires opening one port (MQTTS 8883) on the coordinator's household — violates C1 for that household
- **Community-hosted** (e.g., transformer room with LTE router): feasible but depends on finding suitable location

**Range**: Depends on home WiFi coverage. If the agent is in a cellar next to the smart meter, a separate AP or powerline WiFi extender may be needed to reach the household's router — adds cost and complexity.

**Security**: TLS + MQTT username/password or client certificates. Well-understood. Brute-force protection via broker config.

**Cost**: MQTT broker VPS ~€3-4/month (€36-48/year). Spread across 10 households = €0.30-0.40/hh/month. Agent hardware: ESP32 with WiFi €5-8, no LoRa needed, IR sensor €1-2 = **€7-10/hh**. Coordinator: none if using VPS, or RPi for local fallback.

**Maturity**: Extremely mature. Both OpenEMS and evcc have native MQTT support. Home Assistant has MQTT integration.

**Key tradeoff**: Violates €0 recurring unless a non-VPS approach is found. Requires WiFi coverage where the agent is installed.

**MQTT topic structure sketch (transport independent, works with any TCP/IP link)**:
```
lem/{neighborhood_id}/coordinator/limit           ← Grid limit broadcast
lem/{neighborhood_id}/coordinator/flex/request    ← Flexibility needed
lem/{neighborhood_id}/coordinator/signal/par14a   ← §14a reduction signal
lem/{neighborhood_id}/coordinator/signal/shed     ← Load shed order
lem/{neighborhood_id}/coordinator/tariff          ← Price/Tariff info

lem/{neighborhood_id}/household/{hh_id}/meter     ← Current consumption/generation (optional)
lem/{neighborhood_id}/household/{hh_id}/flex/offer ← Available flexibility
lem/{neighborhood_id}/household/{hh_id}/status    ← Health, connection state
```

---

#### Local WiFi Mesh

**How it works**: Multiple access points across the neighborhood forming a mesh (802.11s, BATMAN, OLSR). All agents and coordinator connect to the same mesh network. Can work without internet.

**Range**: 2.4 GHz WiFi has poor wall penetration. ~30m per hop through one wall degrades quickly. Unlikely to achieve 100m through multiple walls/cellars without many mesh nodes.

**Cost**: Additional APs at €20-40 each if coverage gaps exist. WiFi-capable ESP32 is cheap (€5-8).

**Key tradeoff**: Range is the limiting factor. In a dense German neighborhood with thick stone walls and cellars, this is unreliable without extensive infrastructure.

---

#### Powerline (PLC)

**How it works**: Uses existing household electrical wiring as a communication medium. Modern standards (HomePlug AV, G.hn) achieve 10-100 Mbps.

**Range**: Stays within the same low-voltage transformer — ideal for a neighborhood.

**Cost**: HomePlug adapters €20-50 each. Limited OSS ecosystem.

**Key tradeoff**: German PV inverters and modern power electronics are known to inject noise on power lines, potentially degrading PLC performance. Modules are relatively expensive. No established OSS stack for LEM use.

---

#### Thread / Matter Mesh

**How it works**: 2.4 GHz mesh using IEEE 802.15.4. Self-healing, IPv6-capable. Border router needed for internet connectivity.

**Range**: ~30m per hop, further reduced by walls. Needs many devices close together to form a mesh. Unlikely to cover 100m through multiple buildings.

**Cost**: ESP32-H2 or similar Thread-capable MCU: €5-10.

**Key tradeoff**: Range insufficient for typical neighborhood layouts. Requires dense device placement (every 20-30m) for reliable coverage.

---

#### RS485 Wired

**How it works**: Two-wire differential bus running between households. Simple, robust, proven in industrial settings.

**Range**: Up to 1200m. Immune to interference. No penetration issues (it's wired).

**Cost**: RS485 transceiver €1-2. Cable: €0.50-1/m. For 10 households spread across 200m of cable run: €100-200 in cabling alone.

**Key tradeoff**: Laying cable across private properties, possibly under roads, is impractical for a voluntary neighborhood initiative. Installation cannot be done by a layperson.

---

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

---

## 4. Message Protocol Design (Transport-Agnostic)

The protocol is defined at application layer and is independent of the physical transport (LoRa radio frames, MQTT topics, HTTP payloads, etc.).

### 4.1 Message Types

```
Message
├── GridLimit          (coordinator → all agents)
│   ├── import_limit_w: int      // Max net import in W
│   ├── export_limit_w: int      │ Max net export in W (negative)
│   ├── valid_from: timestamp
│   └── valid_until: timestamp
│
├── LoadShed           (coordinator → all agents)
│   ├── reason: enum              // grid_overload | reverse_power | transformer
│   ├── priority_order: string[]  // ["wallbox", "battery_charge", "heatpump"]
│   ├── reduction_pct: int        // 0-100, how much to reduce
│   └── duration_s: int
│
├── Par14aSignal       (coordinator → all agents, or grid_op → coordinator)
│   ├── module: enum              // 1 (flat reduction) | 2 (pct reduction) | 3 (time-variable)
│   ├── reduction_pct: int        // for module 2
│   ├── valid_from: timestamp
│   └── valid_until: timestamp
│
├── FlexOffer          (agent → coordinator)
│   ├── hh_id: string
│   ├── type: enum                // load_shed | load_increase | battery_discharge | battery_charge
│   ├── power_w: int
│   ├── duration_s: int
│   ├── start_earliest: timestamp
│   ├── end_latest: timestamp
│   └── price_ct_per_kwh: int     // minimum price for flex (if applicable)
│
├── FlexRequest        (coordinator → agent)
│   ├── type: enum
│   ├── power_w: int
│   ├── duration_s: int
│   ├── window_start: timestamp
│   └── window_end: timestamp
│
├── TariffInfo         (coordinator → all agents)
│   ├── type: enum                // epex_spot | fixed | tou
│   ├── price_ct_per_kwh: float
│   └── valid_from: timestamp
│   └── valid_until: timestamp
│
├── FlexAck            (agent → coordinator)
│   ├── hh_id: string
│   ├── accepted: bool
│   └── reason: string             // if rejected
│
└── Heartbeat          (bidirectional)
    ├── node_id: string
    └── seq: int
```

### 4.2 Serialization

For **internet/MQTT** transport: JSON or CBOR.
- JSON: human-readable, ~100-300 bytes per message
- CBOR: binary, ~50-150 bytes per message

For **LoRa** transport: CBOR or custom binary.
- CBOR: widely supported, compact
- Custom binary: most compact (e.g., 8 bytes for a limit message), but least flexible

A CBOR-encoded `GridLimit` message: ~25-40 bytes
```
{
  1: 50000,    // import_limit
  2: -30000,   // export_limit
  3: 1715000000, // valid_from (epoch)
  4: 1715000600  // valid_until
}
```

In CBOR: 25 bytes. In custom binary (4 int32 fields): 18 bytes. Easily fits in a LoRa frame.

### 4.3 Security

| Aspect | Approach |
|--------|----------|
| Encryption (MQTT) | TLS 1.3 |
| Encryption (LoRa) | AES-128 at application layer |
| Authentication | Pre-shared key per household or client certificate |
| Replay protection | Message sequence number + timestamp validation |
| Payload integrity | HMAC in each message |
| Forward secrecy | Not critical — short-lived messages, no long-term secrets |

For LoRa specifically, a simple approach:
- Each agent has a unique PSK (pre-shared key) baked at onboarding
- Coordinator has all PSKs
- Messages encrypted with AES-128-CCM
- Sequence number prevents replay
- No key exchange needed over the air (reduces attack surface)

---

## 5. Coordinator Design

### 5.1 What the Coordinator Does

| Function | Required for Phase 1? | Required for Phase 2? |
|----------|----------------------|----------------------|
| Determine & broadcast grid limit | ✅ Yes | ✅ Yes |
| Accept agent registration | ✅ Yes | ✅ Yes |
| Forward §14a signals from grid operator | ❌ Optional | ✅ Yes |
| Store measurement data (for analysis) | ❌ Optional | ❌ Optional |
| Match flexibility offers/requests | — | ✅ Yes |
| Broadcast load shed signals | ✅ Yes (if limit breached) | ✅ Yes |
| Broadcast tariff information | ❌ Optional | ❌ Optional |

### 5.2 Placement Options

| Location | Pros | Cons |
|----------|------|------|
| **One household** | No extra internet cost, easy access for maintenance | Single point of failure (power/internet at that house), trust issue (data passes through neighbor's network) |
| **Transformer room / common space** | Neutral, may already have power, logical grid attachment point | Requires permission from grid operator or homeowners association |
| **Cloud VPS** | Highest reliability, always reachable | Recurring cost (€3-4/mo), GDPR concerns for meter data |

### 5.3 Graceful Degradation

Critical requirement: grid protection must work even if the coordinator fails.

**Approach A: Local fallback**
- Each agent caches the last valid grid limit
- If no heartbeat from coordinator for N seconds, agent uses cached limit
- If cached limit expires, agent switches to conservative default (e.g., zero export, minimal import)
- When coordinator recovers, agents sync

**Approach B: Agent-to-agent mesh**
- Agents can still communicate peer-to-peer if coordinator is offline
- Flood-based gossip protocol for grid limit propagation
- More complex but more robust

**Approach C: Hot standby**
- A second RPi acts as backup coordinator
- Takes over if primary fails
- Simple but doubles hardware cost (still within €300 budget for a pair of RPis)

### 5.4 Coordinator Hardware

| Component | Cost | Notes |
|-----------|------|-------|
| Raspberry Pi 3B+ | €35-40 | Sufficient for signaling |
| Raspberry Pi 4 (2GB) | €45-55 | More headroom for data logging |
| LoRa hat / HAT | €20-30 | For LoRa-based communication |
| SD Card (32GB) | €8-10 | |
| Power supply + case | €10-15 | |
| **Total RPi 3B+ + LoRa** | **€70-85** | Within €300 budget |
| **Total RPi 4 + LoRa** | **€85-105** | Still well within budget |

For internet-based communication (no LoRa): subtract €20-30 for the LoRa hat, add €0 for VPS coordinator if using cloud.

---

## 6. Cost Verification

### 6.1 Per-Household (Target: €100-200 one-time)

| Component | LoRa-based | MQTT-internet | Notes |
|-----------|-----------|---------------|-------|
| ESP32 | €6 | €6 | Or RPi Zero at €17 |
| LoRa module (SX1276) | €4 | €0 | Not needed for internet-only |
| IR sensor + resistors | €2 | €2 | Smart meter reading |
| Wiring/enclosure | €5 | €5 | |
| Power supply (USB) | €3 | €3 | Existing phone charger likely works |
| Installation materials | €5 | €5 | Cable clips, etc. |
| **Total** | **€25** | **€16** | Well within €100-200 |

With RPi Zero instead of ESP32: add €11. Still under €50.

**Headroom**: €75-184 for optional extras (display, sensors, backup).

### 6.2 Central Infrastructure (Target: ≤€300)

| Component | LoRa-based | Internet-based (VPS) | Notes |
|-----------|-----------|---------------------|-------|
| Raspberry Pi | €40 | €0 | VPS replaces local hardware |
| LoRa hat | €25 | €0 | Not needed for internet-only |
| SD card | €10 | €0 | |
| Power/case | €15 | €0 | |
| VPS (first year) | €0 | €0 | If free tier available |
| **Total** | **€90** | **€0-48/yr** | |

With RPi 4: add €15.

**Headroom (LoRa)**: €210 for extras (backup coordinator, better antenna, weatherproofing).

### 6.3 Recurring (Target: €0)

- **LoRa**: ✅ €0 — no subscriptions, no cloud
- **MQTT internet, VPS**: ❌ ~€3-4/month unless a free tier suffices
- **MQTT internet, local RPi**: ✅ €0 — household hosting, but violates C1 at that household

---

## 7. Phase 1 → Phase 2 Path

### Phase 1 (Minimum Viable: Grid Protection + Measurement)

```
┌──────────────────────────────────────────────────────┐
│ Phase 1                                               │
│                                                       │
│ Coordinator:                                          │
│  - Manually configured grid limit (set during setup)  │
│  - Periodic broadcast of limit to all agents          │
│  - Agent registration / heartbeat monitoring          │
│                                                       │
│ Agent:                                                │
│  - Read smart meter (consumption, generation via SML) │
│  - Receive and display grid limit                     │
│  - Forward limit to home EMS (MQTT/REST)              │
│  - Send heartbeat to coordinator                     │
│  - Fall back to cached limit if coordinator lost      │
│                                                       │
│ Validation:                                           │
│  - Can each agent receive the limit reliably?         │
│  - Does the household EMS see and respect the limit?  │
│  - How fast does the system react to limit changes?   │
└──────────────────────────────────────────────────────┘
```

**Deliverable**: A working neighborhood where each household sees the grid limit and can adjust behavior. No automated flexibility trading yet.

### Phase 2 (Full: Flexibility Coordination + §14a)

```
┌──────────────────────────────────────────────────────┐
│ Phase 2 (adds to Phase 1)                             │
│                                                       │
│ Coordinator additions:                                │
│  - Receive flexibility offers from agents             │
│  - Match offers to requests                           │
│  - §14a signal forwarding                             │
│  - Tariff information broadcast                       │
│  - Load shed signaling when limit is breached         │
│                                                       │
│ Agent additions:                                      │
│  - Calculate available flexibility                    │
│  - Submit flex offers                                 │
│  - Receive and forward §14a signals to home EMS       │
│  - Track financial impact vs baseline                 │
│  - Opt-out per household                              │
│                                                       │
│ Fairness validation:                                  │
│  - Each agent computes: would I have done better       │
│    without LEM coordination?                          │
│  - If any household loses, coordination is adjusted   │
└──────────────────────────────────────────────────────┘
```

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
- **Status**: 🔄 Open — no decision made yet

### Q2: Where does the coordinator live?

**Options**: At one household / community space / VPS / fully decentralized (no coordinator) / soft witness only

**Discussion notes**:
- A full central coordinator is not the only model. Possibilities range from a "soft witness" (just publishes aggregate transformer load) to fully peer-to-peer
- In a P2P system, each agent needs to know the total neighborhood load to self-regulate — approaches include individual allocation, gossip aggregation, or a soft witness
- Fully decentralized avoids single point of failure and trust issues but adds complexity (discovery, consensus, eventual consistency)
- Soft witness model (one agent at transformer publishes only aggregate load, no authority) is a middle ground — removes coordinator authority without full P2P complexity
- **Status**: 🔄 Open — no decision made yet

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
- Phase 1: Use a configured value based on transformer rating or household supply contract capacity — simple, static, no dependencies
- Phase 2: Revisit this — could be upgraded to transformer meter reading or grid operator API for dynamic adaptation
- A transformer meter (ESP32 + SML reader at the transformer, €20-30) gives real-time aggregate load knowledge but requires physical access and grid operator permission
- **Status**: ⏳ Phase 1: manually configured value. Phase 2: to be clarified later.

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
- **Only current values, no history**: Maximum privacy, minimal resource usage. No debugging capability, no optimization history, no fairness audit trail. Hard to verify FR-06 (economic fairness) without any record.
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

---

## 9. Recommendations for Next Step

Regardless of which communication medium is chosen, the next concrete step could be:

1. **Build one agent prototype** (ESP32 + IR reader on a test smart meter or simulator)
2. **Validate SML parsing** against real German smart meters (ISKRA, Landis+Gyr, Holley, etc.)
3. **Build coordinator prototype** (RPi + LoRa hat or MQTT broker)
4. **Test range in a real neighborhood** — drive 100m with a LoRa node in a backpack through cellars
5. **Measure latency and reliability** for grid limit broadcast under real conditions

This would prove the physical layer before investing in the full protocol stack.
