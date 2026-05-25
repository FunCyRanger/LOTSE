**Requirements Analysis and Use-Case Documentation (Simplified Version)**

**Status:** Draft — Phase 1 POC in progress (SoftAP works, HTTPServer binding blocked — see `phase1-summary.md` and `prototype-build.md §P7.5`).

### 1. Introduction and Purpose

The system enables neighborhoods to robustly and cost-effectively coordinate generation and consumption. It acts as a coordination and signaling layer between autonomous household energy management systems — each household retains full control over its own devices. The system prioritizes the protection of grid infrastructure and realizes economic benefits primarily through § 14a EnWG and optimized self-consumption. Formal balancing energy-sharing accounting is deliberately avoided to minimize complexity and additional regulatory hurdles.

### 2. Goals

- Highest priority: Ensuring grid infrastructure safety (transformers and lines).
- Increasing local self-consumption and load flexibility.
- Leveraging existing and future regulatory incentives (§ 14a EnWG).
- High robustness and self-governance capability.
- Low entry barriers and easy extensibility.
- Ensuring data sovereignty of participants.

### 2a. Priority Hierarchy

> **Infrastructure Safety > Economic Fairness**

1. **Infrastructure Safety (highest priority)**: The transformer and line limits are non-negotiable. When a conflict arises, all optimization is suspended to protect grid infrastructure.
2. **Economic Fairness (informational)**: Optimization should minimize financial disadvantage to any household type. Economic impact is tracked as an informational metric — infrastructure safety always takes precedence.
3. **If these conflict, infrastructure safety always wins.**

### 2b. Supported Household Types

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
| Balcony solar (Balkonkraftwerk) | Self-consumption | Maximize generation, curtail if grid export limit exceeded ⚠️ Note: most balcony solar systems lack a digital control interface — curtailment may not be programmatically achievable; treated as a known limitation |
| Balcony solar + Battery | Dynamic | Self-consumption + arbitrage (charge from grid when cheap, discharge when expensive) |

### 2c. Device Hierarchy

Household loads and generation are divided into two categories:

**Uncontrollable devices** — base loads that cannot be curtailed or shifted:
- Lighting, PCs, entertainment, oven, stove, refrigeration, always-on standby loads
- These are part of the household's baseline consumption and never included in flexibility offers

**Controllable devices** — can be shed or reduced when grid limits are exceeded, in priority order:

| Priority | Device | Rationale |
|----------|--------|-----------|
| 1 (shed first) | EV wallbox | Least comfort impact — charging can be delayed hours without notice |
| 2 | Battery | No comfort impact — lost arbitrage revenue only; can recharge later |
| 3 | PV curtailment | Reduces reverse power flow — lost feed-in revenue only; only relevant when exporting |
| 4 (shed last) | Heat pump | Comfort-sensitive — buffer allows short curtailment but cold building is unacceptable |

Within each household agent, shedding follows this priority: **EV → battery → PV → heat pump**. The coordinator's cross-household priority tiers (T7 → T4/T5/T10 → T6) complement this by targeting device-owning households first.

### 3. Functional Requirements (FR)

**FR-01 Grid Infrastructure Protection (highest priority)**  
The system must periodically determine the maximum permissible net export/import limit for the neighborhood or affected grid branch and distribute it bindingly to all participants.

**FR-02 Measurement Data Acquisition**  
Provision of time-resolved consumption and generation data through a suitable, certified metering device. As a private individual, access to this measurement data must be possible.

**FR-03 Decentralized Agents**  
Each participant operates an autonomous agent that acts as a bridge between the neighborhood coordination layer and the household's existing energy management system (e.g., OpenEMS, evcc, Home Assistant). The agent processes local measurement data, offers or requests flexibility to the neighborhood, and forwards coordination signals (grid limits, flexibility requests, tariff or § 14a information) to the household's internal automation. Direct device control remains with the household's own EMS — the agent never controls end devices such as inverters, heat pumps, or wallboxes directly.

**FR-04 Local Coordination**  
Support for coordinating local surplus and demand within applicable grid limits, mediated through household agents without direct device control. Coordination is achieved via signaling (grid limits, flexibility offers/requests, tariff information) — each household's EMS decides autonomously how to respond. No balancing accounting is performed.

**FR-05 Simple Onboarding**  
New participants must be able to integrate into the system without extensive administrative effort.

**FR-06 Economic Fairness (informational)**  
The optimization logic SHOULD avoid strategies that result in financial loss to any household compared to their baseline pricing model. This is an informational metric, not a hard constraint — infrastructure safety (FR-01) always takes precedence. Each household must have visibility into the financial impact of coordination decisions and the ability to opt out of participation.

> **Note:** FR-06 is evaluated as an informational metric in the simulation. The primary hard constraint is infrastructure safety (see FR-01). The comparison algorithm and baseline scenario are defined in the simulation (`simulation_v2/`).

**FR-07 §14a Compatibility**  
The system must coexist with §14a grid-serving control without interference. The grid operator's control path (smart meter gateway → Steuerbox → EEBUS/relay → device or household EMS) is independent and pre-existing for households with §14a-capable devices. The system operates as a separate coordination layer above this: it may optionally receive §14a state information from the household EMS to inform coordination decisions, but it is never a §14a signal carrier. The household EMS reconciles both system coordination signals and §14a reduction commands autonomously. Formal §14a certification is not required because the system is not in the signal path.

### 4. Non-Functional Requirements

- **Robustness**: The system must be able to continue operating with reduced functionality during partial failures. The grid protection function has absolute priority.
- **Scalability**: The system must support at least 100 households within a single logical neighborhood without protocol redesign. Phase 1 (individual allocation) is inherently scalable; Phase 2 coordination mechanisms must not assume an upper bound below 100. Communication duty cycles, mesh size limits, and coordinator throughput must be dimensioned for 100+ participants.
- **Economic Efficiency**: Low investment and no recurring costs — see §4.1.

### 4.1 Cost Requirements

| Category | Target | Notes |
|----------|--------|-------|
| Per-household hardware (one-time) | €100–200 | Bridge device, sensors, installation materials |
| Central infrastructure (one-time) | ≤ €300 | Server + gateway, shared across the community |
| Recurring costs | €0 | No subscriptions, no annual fees — all software is open-source, EPEX Spot data is free |
- **Data Sovereignty and Privacy**: Local data processing in compliance with GDPR.
- **Scalability**: Support for a variable number of households in a neighborhood.
- **Simplicity**: Minimization of administrative and technical complexity.
- **Interoperability**: Compatibility with existing and future metering and control infrastructures.
- **Secure Communication**: The system must not require opening incoming ports on household internet connections. All communication between participants must use outbound connections only, or a dedicated local medium. Authentication and encryption must be provided for all data exchange.
- **Communication Range**: Reliable data exchange between any two **households** must be possible over distances of at least 100 meters through walls, cellars, and other typical residential obstacles. Communication within a household (e.g., agent to smart meter or agent to home EMS) is not subject to this range constraint.
- **Ease of Installation**: Network configuration must not require technical networking expertise — no port forwarding, no DDNS, no VPN setup. Participation must be achievable by a layperson.
- **German Regulatory Compliance**: All hardware components must be CE-certified and available through German distributors. Radio modules (e.g., LoRa 868 MHz) must comply with EU radio equipment directive (2014/53/EU) and ETSI EN 300.220. Smart meter data reading via the optical IR interface is permitted only in read-only mode without tampering with seals or opening the meter housing (§§ MsbG). Data processing must comply with GDPR and MsbG data protection rules; local processing is preferred over cloud transmission.

### 5. System Overview

```mermaid
mindmap
  root((System))
    Phase 1 - Meter Data Collection & Broadcast
      Local grid limit enforcement (per household)
      Smart meter reading via Tasmota IR sensor → HTTP POST
      Mesh-LoRa broadcast (Meshtastic fork) for logging
      SoftAP configuration interface (192.168.4.1)
      Simple onboarding via SoftAP
    Phase 2 - Coordination
      Offer / request flexibility
      Local coordination & load shifting
      Grid-serving signals §14a
      Flexibility trading between households
```

### 6. Detailed Use Cases

#### Phase 1 — Meter Data Collection & Broadcast

- **UC-01 Determine & broadcast grid limit**: Each household's grid limit is configured locally on the agent (from the grid connection contract). The agent self-regulates within this limit independently — no inter-household communication needed. The limit is set via the SoftAP web UI (192.168.4.1) or the Meshtastic admin interface.
- **UC-02 Record consumption & generation data**: A Tasmota-based IR sensor (WattWächter TTL) reads the German smart meter via optical interface. The Tasmota device sends parsed values to the T3-S3 agent via `POST /api/v1/meter` over WiFi (SoftAP). The agent re-broadcasts the meter data over the LoRa mesh for logging and display on other nodes. Supported OBIS codes: 1.8.0 (total consumption), 2.8.0 (total feed-in), 16.7.0 (current power, needs PIN).
- **UC-05 Simple onboarding**: The T3-S3 broadcasts a SoftAP (`LEM-Meshtastic-XXXX`) on every boot. A new participant connects to this WiFi network and configures the agent via the embedded web interface. No port forwarding, DDNS, VPN, or technical networking expertise required.

#### Phase 2 — Coordination

- **UC-03 Offer / request flexibility**: The household agent advertises available flexibility or signals demand to the neighborhood coordinator. The household's own EMS decides whether and how to fulfill flexibility requests.
- **UC-04 Local coordination & load shifting**: Coordination of flexibility between autonomous household systems via signaling. When grid limits are breached, the coordinator broadcasts a load-shed signal with this recommended priority order: EV wallbox → battery charging → heat pump. Each household's EMS decides how to respond. Balcony solar (Balkonkraftwerk) curtailment follows the same signaling principle if reverse power flow limits are exceeded.
- **UC-06 Grid-serving signals**: Forwarding of § 14a-compliant grid-serving signals (module 1/2/3) from grid operator or coordinator to each household's EMS for autonomous implementation.

### 7. Sources

1. Gesetz über die Elektrizitäts- und Gasversorgung (Energiewirtschaftsgesetz - EnWG), § 14a – Netzorientierte Steuerung von steuerbaren Verbrauchseinrichtungen und steuerbaren Netzanschlüssen.  
   [https://www.gesetze-im-internet.de/enwg_2005/__14a.html](https://www.gesetze-im-internet.de/enwg_2005/__14a.html)

2. Bundesnetzagentur. Festlegungsverfahren zur Integration von steuerbaren Verbrauchseinrichtungen und steuerbaren Netzanschlüssen nach § 14a EnWG.  
   [https://www.bundesnetzagentur.de/enwg14a](https://www.bundesnetzagentur.de/enwg14a)

3. Gesetz über den Messstellenbetrieb und die Datenkommunikation in intelligenten Energienetzen (Messstellenbetriebsgesetz - MsbG).  
   [https://www.gesetze-im-internet.de/messbg/](https://www.gesetze-im-internet.de/messbg/)

4. Bundesnetzagentur. Informationen zur netzorientierten Steuerung und Netzentgeltreduzierung nach § 14a EnWG.  
   [https://www.bundesnetzagentur.de/DE/Vportal/Energie/SteuerbareVBE/start.html](https://www.bundesnetzagentur.de/DE/Vportal/Energie/SteuerbareVBE/start.html)

---

**Two-Pager – Neighborhood Energy Coordination**

**Page 1 – System Description**

The system is a simple, robust coordination and signaling layer for local coordination of electricity generation and consumption in residential neighborhoods. It connects autonomous household energy management systems, based on suitable metering devices, decentralized bridge agents, and clear priority rules. The system never controls end devices directly — each household retains full autonomy over its own installations.

**Core functions**:
- Continuous monitoring and adherence to grid limits to protect local infrastructure.
- Coordinated use of generation surpluses and consumption flexibility.
- Support for grid-serving operation of controllable installations.

The system avoids complex billing mechanisms and focuses on practical, immediately usable benefits. It is designed to start with existing installations and be expanded incrementally.

**Why does implementation make sense?**  
The ongoing energy transition is leading to increasing decentralized generation and electrification of the heating and transport sectors. This significantly increases the load on low-voltage grids. Local coordination mechanisms can reduce grid congestion without costly grid expansion. At the same time, they enable households to realize direct economic benefits through optimized self-consumption and regulatory incentives such as § 14a EnWG.

**Page 2 – Advantages, Disadvantages, and Assessment**

**Advantages**:
- **Economic**: Utilization of grid fee reductions according to § 14a EnWG and increase in self-consumption share.
- **Technically robust**: High reliability through decentralized structure and graceful degradation.
- **Regulatory compliant**: No dependency on certified sharing metering systems; compatibility with current legal frameworks.
- **Practical**: Low entry barriers and use of existing metering infrastructure.
- **Future-proof**: Solid foundation for later regulatory developments.

**Disadvantages**:
- Limited monetary benefit when few controllable consumption devices are available.
- Dependence on the grid operator's willingness to cooperate for full § 14a benefits.
- Initial organizational effort within the neighborhood.

**Overall assessment**:  
The system represents a pragmatic and sensible approach. It addresses real physical and economic challenges of the energy transition at the neighborhood level, without requiring excessive complexity or high investment. In a phase of increasing grid load and grid fees, it offers a concrete contribution to local resilience, cost reduction, and efficient use of existing infrastructure.

**Recommendation**: Start with a small pilot project to validate the practical effectiveness of grid protection and flexibility coordination.

**Sources (Two-Pager)**  
See detailed sources in the requirements analysis (Section 7).
