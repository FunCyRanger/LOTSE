# Grid Utilization Simulation v2 — Specification

**Purpose:** Evaluate whether Phase 2 coordination strategies can defer grid upgrades by using existing capacity more efficiently, while protecting infrastructure safety. FR-06 (household economic impact) is tracked as an informational metric.
**Implements:** simulation-plan.md.
**Prerequisite for:** Phase 2 coordination algorithm selection.

---

## 1. Overview

The simulation tests how well Phase 2 coordination strategies manage grid utilization under increasing technology adoption (PV, EV, heat pumps). It does this by running **two passes** over the same input data at **hourly resolution**:

- **Baseline pass (Run A):** Each household follows its default load curve. No inter-household coordination signals.
- **Coordination pass (Run B):** Same agents, same external conditions. A coordinator broadcasts flex requests or load shed signals per a selected approach. Agents may accept or reject based on their minimum acceptable price, daily energy budget, and opt-out status.

**Infrastructure safety is the hard constraint.** The simulation exits with code 1 if coordination fails to keep transformer loading ≤ 100%. FR-06 (economic fairness) is tracked for visibility but is not a pass/fail criterion.

**Simplified agent model** (v2): Each household has a type-specific **flexibility curve** (kW per hour), **minimum acceptable price** (ct/kWh), and **daily energy budget** (kWh). No SOC tracking, no battery dispatch optimization, no thermal storage simulation.

### 1.1 What it tests

- Grid utilization metrics per approach: peak reduction, congestion events, headroom increase
- Hosting capacity: maximum PV/EV/HP penetration before grid limits are exceeded (via `--sweep` mode)
- Ranking of 9 approaches by utilization improvement
- **Priority-enforced load shed** (EV wallbox → battery charging → heat pump, per UC-04)
- **Per-household opt-out** after load shed events
- Sensitivity to neighborhood composition (mix of T1–T10) and technology scaling

### 1.2 What it does not test

- Real EMS behavior (the simplified flex-curve model captures decision boundaries, not full EMS logic)
- User behavior (manual overrides, non-economic decisions)
- Communication errors (packet loss, latency, collisions)
- Social dynamics (neighbor pressure, opt-out psychology)
- Intra-day battery state dynamics (daily budget only, not SOC tracking)
- Thermal network effects or voltage regulation hardware (statcom, on-load tap changers)

---

## 2. Architecture

```
                         Simulation Core
         ┌─────────────────────────────────────────────┐
         │  Discrete-time loop, Δt = 60 min             │
         │  24 steps/day × 365 days = 8,760 steps      │
         │                                              │
         │  Per step:                                   │
         │  1. Read price, load, PV for timestep       │
         │  2. Baseline actions (no coordination)       │
         │  3. Agents report flex_kw + min_price         │
         │  4. Coordinator: process_flex()                │
         │  5. If util ≥ 100%: priority-enforced shed    │
         │     (T7 → T4/T5/T10 → T6)                   │
         │  6. Agents respond (accept/reject within      │
         │     energy budget + opt-out status)           │
         │  7. Record costs both runs                    │
         │  8. Run load flow (pandapower)                │
         └────┬──────────┬──────────┬────────────────────┘
              │          │          │
     ┌────────▼──┐ ┌────▼───┐ ┌───▼──────────┐
     │ Agent Layer│ │Coord.  │ │ Grid Model   │
     │ 10 types  │ │Layer   │ │ (pandapower) │
     │ T1–T10    │ │ A–I    │ │ LV feeder    │
     │ flex curve│ │strat.  │ │ load flow    │
     │ min_price │ │+prio   │ │              │
     │ budget    │ │+optout │ │              │
     └───────────┘ └────────┘ └──────────────┘
```

### 2.1 Simulation loop

For each timestep:

1. **External state:** Read synthetic EPEX price, load profile value, PV generation for current timestep.
2. **Baseline actions:** Each agent computes `baseline_action(td)` — the default load/generation without coordination. Resulting action is `net_grid_kw = load_kw - pv_kw`.
3. **Baseline cost:** `action.cost_ct(price, config, dt_h)` computes the financial cost under the household's pricing model.
4. **Flex offers:** Each agent reports available flexibility (kW), minimum acceptable price (ct/kWh), and remaining daily budget.
5. **Coordinator flex:** The fairness strategy's `process_flex()` allocates flex requests to agents based on selection logic.
6. **Load shed:** If total `net_grid_kw` / transformer capacity ≥ 100%, coordinator triggers **priority-enforced load shed** (EV wallbox → battery → heat pump). Agents in opt-out cooldown are skipped.
7. **Coordination actions:** Each agent evaluates the received signal against its `min_price`, `daily_budget`, and `opt_out_steps`, then accepts or rejects.
8. **Coordination cost:** Same cost function applied to the coordinated action.
9. **Load flow:** Run pandapower AC unbalanced load flow. Record transformer loading, voltages, line loads.

### 2.2 Dual-run comparison

Same external conditions (price, load, PV) in both runs. Agent state is minimal: `remaining_daily_kwh` (resets at midnight) and `opt_out_steps` (countdown after load shed). Both runs share the same agent state trajectory (baseline never triggers opt-out since it receives no signals). Grid metrics are computed for both runs to measure the improvement from coordination.

### 2.3 Faithfulness to the real system

The simulation mirrors the Phase 2 architecture (Brainstorming §6):
- Agents are autonomous — they decide whether to respond to signals based on min_price and budget
- Coordination is voluntary (except during grid emergencies where infrastructure > fairness)
- No balancing accounting — the system never settles payments
- **Load shed priority order** per UC-04: EV wallbox → battery charging → heat pump
- **Opt-out**: households can temporarily opt out after being shed
- Phase 1 individual limits are not explicitly enforced in this simulation (prototype scope per discussion)

---

## 3. Timestep Model

| Parameter | Default | Description |
|-----------|---------|-------------|
| `timestep_min` | 60 | Simulation time step in minutes |
| `duration_days` | 365 | Total simulation duration |
| `year` | 2023 | Reference year for profiles and date indexing |
| Steps per run | 8,760 | 24 steps/day × 365 days (4× fewer than v1) |

At each timestep, the simulation builds a `TimestepData` struct:

```
TimestepData {
    price_ct: float       // synthetic EPEX price in ct/kWh
    load_kw: float         // household load in kW
    pv_kw: float           // PV generation in kW
    hour: int             // hour of day (0–23)
    dayofyear: int        // day of year (1–365)
    dt_h: float           // timestep duration in hours (1.0)
    par14a_active: bool   // §14a curtailment event active
}
```

Values in kW throughout (v1 used W for load/PV, kW for net). v2 uses kW consistently.

---

## 4. Data Model

### 4.1 Core types

| Type | Fields | Purpose |
|------|--------|---------|
| `TimestepData` | price_ct, load_kw, pv_kw, hour, dayofyear, dt_h, par14a_active | External state at one timestep |
| `AgentConfig` | household_type, pv_kwp, battery_kwh, annual_consumption_kwh, tariff_rate_ct, eeg_rate_ct, idx | Static household parameters |
| `AgentState` | remaining_daily_kwh (daily budget remaining), opt_out_steps (cooldown counter), cumulative_cost_baseline, cumulative_cost_coord | Minimal per-agent state |
| `Action` | net_grid_kw, flex_kw (offered), flex_accepted_kw, min_price_ct, shed_kw | Energy + flex action |
| `FlexOffer` | agent_idx, flex_kw, min_price_ct, daily_budget_remaining_kwh, opt_out_steps | What agent offers coordinator |
| `CoordSignal` | flex_request_kw, load_shed, price_signal_ct, shed_priority_tier | Coordination signal to agent |
| `SimulationResult` | approach_name, fairness_metrics, utilization_metrics, grid_summary, per_agent | Full simulation output |

### 4.2 Action cost function

The cost of an action depends on the household type's pricing model (unchanged from v1):

| Type | Cost formula |
|------|-------------|
| T1, T9 | `import_kwh × tariff_rate_ct` |
| T2 | `import_kwh × tariff_rate_ct - export_kwh × eeg_rate_ct` |
| T3, T4, T5, T7, T8, T10 | `import_kwh × price_ct - export_kwh × price_ct` |
| T6 | `import_kwh × price_ct` (import only; heat pump is a consumer) |

All costs in Euro-cents. `import_kwh = max(0, net_grid_kw) × dt_h`.
`export_kwh = max(0, -net_grid_kw) × dt_h`.

---

## 5. Agent Models (T1–T10)

### 5.1 Device-based model

Each agent's flexibility is modeled as a list of **controllable devices**, each with:

1. **Device type** — `ev`, `battery`, `pv`, `heatpump`. Uncontrollable loads (oven, PC, light) are part of the baseline and never in this list.
2. **Rated power** `rated_kw` — maximum power (kW) the device can shed at its operating hours.
3. **Priority** — shedding order within the household: **EV (1) → battery (2) → PV curtailment (3) → heat pump (4)**. Lower number = shed first (less comfort impact).
4. **Minimum acceptable price** `min_price_ct` — for voluntary flex requests, the device only participates if `signal.price_signal_ct >= min_price_ct`.
5. **Daily energy budget** `daily_kwh` — maximum cumulative flex energy per day from this device.
6. **Operating hours** — the hours when the device can provide flexibility (e.g., PV only during daylight, EV only during charging window).

Agent-level properties are derived from the device list:
- `flex_kw(hour)` = sum of all device `rated_kw` at that hour
- `min_price_ct` = minimum of device `min_price_ct` values
- `daily_capacity_kwh` = sum of device `daily_kwh`

### 5.2 Device interface

```python
@dataclass
class FlexDevice:
    device_type: str       # "ev" | "battery" | "pv" | "heatpump"
    rated_kw: float        # max flexible power
    priority: int          # 1 (EV) → 4 (heat pump)
    min_price_ct: float    # min acceptable price
    daily_kwh: float       # daily energy budget
    hour_start: int        # operating window start (inclusive)
    hour_end: int          # operating window end (inclusive, handles midnight wrap)

    def flex_kw(self, hour: int) -> float:
        """Return rated_kw if hour is within operating window, else 0"""
```

```python
class BaseAgent:
    devices: list[FlexDevice]  # class-level device list per type
    config: AgentConfig
    state: AgentState          # remaining_daily_kwh, opt_out_steps

    def baseline_action(self, td: TimestepData) -> Action:
        """Default import/export: net_kw = load_kw - pv_kw"""

    def make_flex_offer(self, td: TimestepData) -> FlexOffer:
        """Sum devices' flex_kw, report min_price + remaining budget"""

    def accept_signal(self, td: TimestepData, signal: CoordSignal) -> Action:
        """Shed lowest-priority devices first (load_shed) or cheapest-first (flex)"""
```

### 5.3 Per-type device composition

| Type | Devices | Total flex_kw peak | Daily capacity | Baseline action |
|------|---------|-------------------|----------------|-----------------|
| T1 | — | 0 kW | 0 kWh | `net = load` |
| T2 | PV (3 kW, 9–17, prio=3, 8.2 ct) | 3 kW at 9–17 | 21 kWh | `net = load - pv` |
| T3 | PV (3 kW, 9–17, prio=3, 0 ct) | 3 kW at 9–17 | 21 kWh | `net = load - pv` |
| T4 | Battery (5 kW, 6–22, prio=2, 2 ct) | 5 kW at 6–22 | 40 kWh | `net = load - pv` |
| T5 | Battery (5 kW, all hours, prio=2, 5 ct) | 5 kW | 40 kWh | `net = load` |
| T6 | Heat pump (3 kW, 6–22, prio=4, 1 ct) | 3 kW at 6–22 | 30 kWh | `net = load` |
| T7 | EV (7 kW, 17–7, prio=1, 1 ct) | 7 kW at 17–7 | 50 kWh | `net = load + 7 kW EV at night` |
| T8 | EV (11 kW, 17–7, prio=1, 1 ct) + Battery (5 kW, 6–22, prio=2, 1 ct) | 16 kW (11+5) | 80 kWh | `net = load - pv` |
| T9 | — | 0 kW | 0 kWh | `net = load - pv` |
| T10 | Battery (1 kW, 6–22, prio=2, 3 ct) | 1 kW at 6–22 | 5 kWh | `net = load - pv` |

**§14a interaction:** During `par14a_active`, heat pump devices (T6, T8) are excluded from flexibility (already curtailed by grid operator).

### 5.4 Agent logic — device-level shedding

**Baseline** (unchanged):
```
net_grid_kw = load_kw - pv_kw
```
All types follow this baseline. No self-optimization.

**Voluntary flex request:**
```
if remaining_daily_kwh > 0 and opt_out_steps == 0:
    sort devices by min_price_ct (cheapest first)
    budget_kw = remaining_daily_kwh / dt_h
    remaining = min(flex_kw(hour), request_kw, budget_kw)
    for device in sorted_devices:
        if signal.price_signal_ct < device.min_price_ct:
            skip this device
        take = min(device.rated_kw, remaining)
        net_grid_kw -= take   # reduce import
        remaining -= take
        remaining_daily_kwh -= take * dt_h
```

**Load shed (bypasses min_price check):**
```
if opt_out_steps == 0:
    sort devices by priority (1 = EV first, 4 = heat pump last)
    remaining = reduction_requested
    for device in sorted_devices:
        take = min(device.flex_kw(hour), remaining)
        net_grid_kw -= take   # reduce import
        remaining -= take
    if any device was shed:
        opt_out_steps = config.opt_out_duration  # start cooldown
```

### 5.5 Opt-out behavior

After an agent is shed:
- `opt_out_steps` is set to a configurable duration (default 48 hours)
- During cooldown: agent ignores all flex requests and load shed signals (returns baseline action)
- Counter decrements each timestep
- Opt-out does **not** trigger from voluntary flex requests (only from involuntary load shed)

---

## 6. Coordinator Strategies (A–I)

### 6.1 Common interface

```python
class FairnessStrategy:
    def process_flex(self, agents: list, flex_offers: list, actions: list, demand_kw: float) -> list[CoordSignal]
    def process_load_shed(self, agents: list, actions: list, grid_util_pct: float) -> list[CoordSignal]
```

`process_flex` is called during normal operation, receives each agent's `FlexOffer`, and returns per-agent `CoordSignal`. `process_load_shed` is called when grid utilization exceeds 100%.

### 6.2 Priority-enforced load shed (shared across all approaches)

When `grid_utilization_pct >= 100`, the coordinator applies a shared priority logic per **UC-04** (Requirements.md §6):

1. Compute required reduction: `demand_kw = total_import_kw - transformer_capacity_kva × 0.95`
2. **Tier 1 — EV wallbox (type T7):** Distribute reduction proportionally among T7 agents with available flex. If demand met, stop.
3. **Tier 2 — Battery charging (types T4, T5, T10):** Distribute remaining reduction among battery agents. If demand met, stop.
4. **Tier 3 — Heat pump (type T6):** Distribute remaining reduction among T6 agents.
5. All other types (T1, T2, T3, T8, T9): receive informational signal but are not targeted (T8's battery/EV/HP components are handled via their type categories already).

Within each tier, reduction is split proportionally by the agent's current `flex_kw(hour)`.

**Opt-out exclusion:** Agents with `opt_out_steps > 0` are excluded from all tiers.

### 6.3 Per-approach specification (flex logic only)

| Approach | Flex selection logic | State kept |
|----------|---------------------|------------|
| **A: Self-Selection** | Broadcast flex request equally, agents decide individually | None |
| **B: Min Price** | Sort `FlexOffer` by `min_price_ct`, accept cheapest first | `participation_score` per agent |
| **C: Rotation** | Sort by cumulative contribution (lowest first), accept from least-used | `scores` per agent |
| **D: Proportional** | Each agent contributes `flex_kw / total_flex × demand` | None |
| **E: Merit+Budget** | Like B but with `max_budget_kwh` cap per period | `budget` per agent |
| **F: Priority** | Sort by contribution (highest first), most-contributing get first access | `contributions` per agent |
| **G: Narrow** | Round-robin across all agents, regardless of flexibility | `last_idx` |
| **H: Emergency** | Normal: same as A. Emergency: proportional shed (priority tiers) | None |
| **I: Hybrid B+C** | Sort by price, tie-break by budget used (lowest first) | `budget` per agent |

**Load shed logic is shared across all approaches** (the priority tiers + opt-out rules above). Approaches only differ in how they allocate **voluntary flex requests** during normal operation.

### 6.4 Load shed trigger

All approaches use the same threshold:
- If `grid_utilization_pct >= 100`: trigger priority-enforced load shed (see §6.2)
- The load shed signal is a **hard recommendation** — agents may refuse, but the priority hierarchy permits this override
- Agents in opt-out cooldown are skipped

---

## 7. Grid Model

### 7.1 Network topology

Built with pandapower as a parameterized LV feeder:

| Component | Default | Description |
|-----------|---------|-------------|
| Transformer | 630 kVA, 20/0.4 kV | MV/LV substation |
| HV bus | 20 kV | Connection to MV grid |
| LV bus | 0.4 kV | Transformer secondary |
| Main feeder cable | NA2XY 4×150 mm², 0.208 Ω/km | Radial feeder segments |
| Service cable | 4×35 mm², 0.841 Ω/km | House connection cables |
| Transformer impedance | vk=4%, vkr=1% | Standard distribution transformer |

The network is built from configuration:
```
feeder_config:
  n_feeder: 1
  households_per_feeder: [10]
  feeder_length_km: [0.3]
```

Each household connects to a dedicated LV bus via a short service line (15m default).

### 7.2 Load flow

- Algorithm: Newton-Raphson (pandapower `runpp`)
- Output per timestep: transformer loading %, bus voltages p.u., line loading %
- Computed every timestep (8,760 steps/year at hourly resolution)
- Non-convergent cases retry with Iwamoto-NR, then mark as non-convergent

### 7.3 Household-to-bus mapping

`net._household_bus_map` maps agent index to pandapower bus index. At load flow time, each agent's `net_grid_kw / 1000` is set as the bus load in MW (unchanged from v1).

---

## 8. Input Data

The simulation supports two data sources, controlled by the `data_source` config field:

| Mode | Config value | Description |
|------|-------------|-------------|
| **Synthetic** | `synthetic` (default) | Statistically generated prices, load, and PV — no external files needed |
| **OPSD** | `opsd` | Real 2019 German data from Open Power System Data — requires downloaded CSV files |

When `data_source: synthetic`, the models below are used. When `data_source: opsd`, the OPSD loaders (§8.5) override specific generators while keeping others unchanged.

### 8.1 Price model (synthetic mode)

Simplified hourly synthetic price (changed from v1's lognormal + season model to a simpler hourly array):

```
base_price ~ LogNormal(mean=2.5, sigma=0.5)     # median ~12 ct/kWh
hour_multiplier = [0.8, 0.8, 0.7, 0.7, 0.8, 0.9,  # 0–5
                   1.0, 1.3, 1.5, 1.4, 1.2, 1.1,  # 6–11
                   1.0, 1.0, 1.0, 1.0, 1.1, 1.3,  # 12–17
                   1.6, 1.8, 1.7, 1.5, 1.2, 1.0]  # 18–23
season_factor = 1.0 + 0.3 × cos(2π × day / 365)  # winter peak
noise ~ Normal(0, 2) clipped to [-5, 5]
price_ct = base_price × hour_multiplier × season_factor + noise
price_ct = max(-1, price_ct)  # allow occasional negative prices
```

Result ranges from -1 to 50 ct/kWh. Negative prices trigger T3's curtailment logic (profitable at spot < 0).

**OPSD mode override:** replaced by `DE_LU_price_day_ahead` (EUR/MWh ÷ 10 → ct/kWh) from OPSD Time Series (DE-LU bidding zone).

### 8.2 Load profiles (synthetic mode)

Same BDEW H0 seasonal profiles as v1, but at hourly resolution (24 values per day instead of 96):

| Season | Days | Hourly shape (24h) |
|--------|------|-------------------|
| Winter (doy 0–90) | 90 | [0.32, 0.28, 0.26, 0.26, 0.28, 0.34, 0.48, 0.56, 0.52, 0.48, 0.44, 0.44, 0.44, 0.44, 0.44, 0.46, 0.52, 0.60, 0.68, 0.72, 0.70, 0.64, 0.52, 0.38] |
| Spring (doy 90–181) | 91 | [0.26, 0.24, 0.22, 0.22, 0.24, 0.28, 0.38, 0.48, 0.48, 0.44, 0.40, 0.38, 0.38, 0.38, 0.38, 0.40, 0.48, 0.54, 0.58, 0.60, 0.58, 0.52, 0.42, 0.30] |
| Summer (doy 181–273) | 92 | [0.22, 0.20, 0.18, 0.18, 0.20, 0.24, 0.34, 0.42, 0.42, 0.38, 0.36, 0.34, 0.34, 0.34, 0.34, 0.36, 0.44, 0.50, 0.54, 0.56, 0.54, 0.48, 0.38, 0.26] |
| Fall (doy 273–365) | 92 | [0.28, 0.26, 0.24, 0.24, 0.26, 0.30, 0.42, 0.50, 0.50, 0.46, 0.42, 0.40, 0.40, 0.40, 0.40, 0.42, 0.50, 0.56, 0.62, 0.66, 0.64, 0.58, 0.46, 0.34] |

Profiles are scaled to `annual_consumption_kwh / 8760` per household and multiplied by per-household Gaussian noise `N(1.0, 0.1)`.

**OPSD mode override:** load profiles for mapped households are replaced by real `consumption` time series from the OPSD Household Data package. Unmapped types (or types without a matching real household) retain synthetic BDEW profiles.

### 8.3 PV generation (synthetic mode)

Same clear-sky irradiance model as v1, at hourly resolution:

```
cos_zenith = sin(lat) × sin(declination) + cos(lat) × cos(declination) × cos(15 × (solar_time - 12))
clear_sky = 1000 × cos_zenith^1.2
clouds ~ Beta(2, 5) × 0.6 + 0.4
pv_kw = clear_sky × clouds / 1000 × kWp × 0.85
```

**OPSD mode override:** scaled from `DE_solar_generation_actual` (MW):

```
pv_kw[t][i] = DE_solar_generation_actual[t] × cfg[i].pv_kwp / DE_solar_capacity[t]
```

where `DE_solar_generation_actual` is actual German PV feed-in (MW) and `DE_solar_capacity` is total installed German solar capacity (MW), both from the OPSD Time Series package.

### 8.4 §14a events

Stochastic model (unchanged across both modes):
- `events_per_year`: number of curtailment events (default 5)
- `max_duration_h`: per-event duration (default 3 hours)
- Events placed randomly in the year
- When active: T6 and T8 agents set `flex_kw = 0` (cannot offer flexibility while curtailed by grid operator)

### 8.5 OPSD data source

#### 8.5.1 Data packages used

| Package | Version | Geographical scope | Period | Description |
|---------|---------|-------------------|--------|-------------|
| [**Time Series**](https://data.open-power-system-data.org/time_series/2020-10-06/) | 2020-10-06 | Germany (country-level) | 2015–mid 2020 | Hourly load, PV generation, PV capacity, day-ahead prices |
| [**Household Data**](https://data.open-power-system-data.org/household_data/2020-04-15/) | 2020-04-15 | 11 households in Konstanz, Germany | 2015–2018 (best: 2017) | Per-device cumulative consumption, PV, EV, heat pump, battery |

Both packages are published under Creative Commons Attribution (CC BY) licenses. Data was collected from the CoSSMic project (Household Data) and ENTSO-E Transparency Platform (Time Series).

**Primary sources:**
- ENTSO-E Transparency Platform: `https://transparency.entsoe.eu/`
- CoSSMic project: `https://cossmic.eu/`
- OPSD data platform: `https://data.open-power-system-data.org/`

#### 8.5.2 Scaling methodology

| Signal | OPSD column | Scaling | Notes |
|--------|-------------|---------|-------|
| Price | `DE_LU_price_day_ahead` (EUR/MWh) | ÷ 10 → ct/kWh | Direct replacement for §8.1 |
| PV | `DE_solar_generation_actual` (MW) | × `pv_kwp` / `DE_solar_capacity` (MW) → kW | National PV scaled per household capacity |
| Load (mapped) | `{household}_consumption` (kWh/h) | Direct use | Replaces BDEW H0 profile |
| Load (unmapped) | — | BDEW H0 synthetic | Fallback when no real household matches |

#### 8.5.3 Household mapping (Household Data)

Each T-type can be mapped to a real household profile from the CoSSMic dataset using the `household_mapping` config section. Available CoSSMic household identifiers and their known devices:

| Identifier | PV | Battery | EV | Heat pump | Grid data | Suitable for |
|------------|----|---------|----|-----------|-----------|--------------|
| `residential1` | ✓ | — | — | ✓ | imp | T2/T3 (PV), T6 (HP) |
| `residential2` | — | — | — | — | imp | T1 (base, no PV) |
| `residential3` | ✓ | — | — | — | imp+exp | T4/T8 (PV+battery candidate) |
| `residential4` | ✓ | — | ✓ | ✓ | imp+exp | T7 (EV), T6 (HP) |
| `residential5` | — | — | — | — | imp | T1 (base) |
| `residential6` | ✓ | — | — | — | imp+exp | T2/T3 (PV) |
| `industrial1` | ✓ | — | — | — | imp | T8 (large PV) |
| `industrial2` | ✓ | ✓ | — | — | imp+sto | T5 (battery) |
| `industrial3` | ✓ | — | ✓ | — | imp | T7 (EV, commercial) |

Cumulative meter readings are differenced to per-hour kW. Unmapped types retain synthetic BDEW profiles and synthetic PV. Config year defaults to 2017 (best overlap between both packages).

#### 8.5.4 Data files

CSV files are stored in `simulation_v2/opsd_data/` (added to `.gitignore` — too large for version control):

```
simulation_v2/opsd_data/
├── time_series_60min_singleindex.csv     # ~124 MB
├── household_data_60min_singleindex.csv  # ~36 MB
└── .gitignore                            # ignores all CSV files
```

Download instructions:

```bash
wget -P simulation_v2/opsd_data/ \
  https://data.open-power-system-data.org/time_series/2020-10-06/time_series_60min_singleindex.csv
wget -P simulation_v2/opsd_data/ \
  https://data.open-power-system-data.org/household_data/2020-04-15/household_data_60min_singleindex.csv
```

#### 8.5.5 Time alignment

- OPSD timestamps use `cet_cest_timestamp` (Central European Time, including DST) for local time alignment
- Simulation uses CET/CEST hours directly — `hour = step % 24` matches the local hour of day
- Household data is cumulative (kWh meter readings); data_loader differences to per-hour kW
- DST transitions (23h/25h days) are handled by pandas dt accessor during data loading
- If `n_steps` exceeds available OPSD data for the configured year, the shorter length wins

#### 8.5.6 Run comparison: synthetic vs OPSD

| Aspect | Synthetic mode | OPSD mode | Impact |
|--------|---------------|-----------|--------|
| Price dynamics | Lognormal + hour cycle | Real 2017 EPEX day-ahead (DE-LU bidding zone) | Captures actual price spikes, negative price events, seasonal volatility |
| PV generation | Clear-sky + Beta clouds | Real German PV (scaled from national) | Captures actual weather patterns, cloud cover, seasonal irradiance |
| Load profiles | BDEW H0 standard | Real CoSSMic household measurements (differenced from cumulative kWh) | Captures individual household behavior, load diversity |
| Flex model | T1–T10 synthetic behavior | Unchanged (flex model is not data-driven) | Isolates input data effect from algorithm effect |
| §14a events | Stochastic random placement | Same (no real §14a data available) | No change |

---

## 9. Configuration Schema

### 9.1 YAML structure

```yaml
# Simulation parameters
duration_days: 365
timestep_min: 60
year: 2017
seed: 42

# Data source
data_source: synthetic       # "synthetic" or "opsd"

# OPSD-specific (only when data_source: opsd)
time_series_csv: simulation_v2/opsd_data/time_series_60min_singleindex.csv
household_csv: simulation_v2/opsd_data/household_data_60min_singleindex.csv
# Optional: map T-types to real household profiles
# Household data covers 2015-2018 (best coverage in 2017).
# Unmapped types use synthetic BDEW profiles.
household_mapping:
  T2: "residential1"
  T3: "residential6"
  T4: "residential3"
  T5: "industrial2"
  T6: "residential1"
  T7: "residential4"
  T8: "industrial1"

# Neighborhood
n_households: 10

# Household type mix (fractions must sum to 1.0)
household_mix:
  T1: 0.10   T2: 0.10   T3: 0.10
  T4: 0.15   T5: 0.05   T6: 0.10
  T7: 0.15   T8: 0.10   T9: 0.10   T10: 0.05

# Fairness approach (A–I)
approach: A

# Opt-out duration after load shed (hours)
opt_out_duration_h: 48

# Type-specific parameters
type_defaults:
  T2:  {pv_kwp: 7.0, annual_consumption_kwh: 4000}
  T4:  {pv_kwp: 10.0, battery_kwh: 10.0}
  T7:  {annual_consumption_kwh: 3500}
  T8:  {pv_kwp: 10.0, battery_kwh: 10.0}
  ...

# Tariff defaults
tariff_rate_ct_per_kwh: 30.0
eeg_rate_ct_per_kwh: 8.2

# Grid
transformer_kva: 630
feeder_config:
  n_feeder: 1
  households_per_feeder: [10]
  feeder_length_km: [0.3]

# §14a (disabled by default)
par14a:
  enabled: false
  events_per_year: 5
  max_duration_h: 3
```

### 9.2 Configuration keys

| Key | Default | Description |
|-----|---------|-------------|
| `data_source` | `synthetic` | Input data mode: `"synthetic"` (built-in generators) or `"opsd"` (real OPSD data + CSVs) |
| `year` | 2019 | Reference year for OPSD data filtering; also used for synthetic season profiles |
| `time_series_csv` | `simulation_v2/opsd_data/...` | Path to OPSD Time Series CSV (only when `data_source: opsd`) |
| `household_csv` | `simulation_v2/opsd_data/...` | Path to OPSD Household Data CSV (only when `data_source: opsd`) |
| `household_mapping` | `{}` | T-type to real household name mapping (only when `data_source: opsd`); unmapped types use synthetic BDEW |
| `annual_consumption_kwh` | 4000 | Scaling for load profile (all types) |
| `pv_kwp` | 0 | Installed PV capacity in kWp (T2, T3, T4, T8, T9, T10) |
| `battery_kwh` | 0 | Battery energy capacity in kWh (T4, T5, T8, T10) |
| `opt_out_duration_h` | 48 | Cooldown after load shed event (global) |

**Changes from v1:** Removed `battery_kw`, `ev_kwh`, `ev_kw`, `ev_arrival_hour`, `ev_departure_hour`, `hp_kw`, `hp_buffer_kwh`, `grid_limit_w`, and the `lora` section. Flex curves are type-constant (defined in code, not config). `battery_kwh` and `pv_kwp` are retained only for output scaling (daily budget is derived from type, not from battery size).

---

## 10. CLI Reference

### 10.1 Usage

```bash
python simulation_v2/sim.py [OPTIONS]
```

### 10.2 Options

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--config` | `-c` | `configs/default.yaml` | Configuration file path |
| `--approach` | `-a` | from config | Fairness approach (A–I) |
| `--days` | `-d` | from config | Simulation duration in days |
| `--output` | `-o` | `results/` | Output directory |
| `--data-source` | `-s` | from config | Data source mode (`synthetic` or `opsd`) |

### 10.3 Exit codes

| Code | Meaning |
|------|---------|
| 0 | Simulation completed, grid safe (coordination kept transformer ≤ 100%) |
| 1 | Simulation completed, grid unsafe (congestion persisted even with coordination) |

### 10.4 Examples

```bash
# Default run (approach A, 10 households, 1 year)
python simulation_v2/sim.py

# Specific approach, shorter duration
python simulation_v2/sim.py --approach D --days 30

# Custom output
python simulation_v2/sim.py --approach I --output /tmp/my_run

# Compare all approaches (synthetic)
for a in A B C D E F G H I; do
    python simulation_v2/sim.py --approach $a --days 30 --output results/$a
done

# OPSD mode with custom config
python simulation_v2/sim.py --config configs/opsd.yaml

# Override data source from CLI
python simulation_v2/sim.py --data-source opsd
```

---

## 11. Output Format

### 11.1 YAML result file

Written to `results/result_{approach}.yaml`:

```yaml
approach: A
approach_name: "A: Self-Selection"
n_households: 10
duration_days: 365
utilization:
  peak_reduction_pct: 15.2
  congestion_events_baseline: 48
  congestion_events_coord: 0
  congestion_resolved: true
  headroom_increase_pct: 45
  hours_above_90pct_baseline: 120
  hours_above_90pct_coord: 23
fairness:
  max_cost_delta_ct: 12.1
  mean_cost_delta_ct: -3.5
  violations_count: 4
  total_savings_ct: 340
per_type:
  T4:
    count: 2
    mean_delta_ct: 12.1
    max_delta_ct: 12.1
    violations: 2
  T7:
    count: 2
    mean_delta_ct: -34.1
    violations: 0
  ...
grid:
  max_trafo_loading_pct: 95.2
  p95_trafo_loading_pct: 72.3
  hours_above_100pct: 12
  hours_above_90pct: 45
per_agent:
  - idx: 0
    type: T1
    baseline_cost_ct: ...
    coord_cost_ct: ...
    delta_ct: ...
    shed_events: 2
    opt_out_timesteps: 48
```

### 11.2 Console summary

```
============================================================
  Approach: A: Self-Selection
============================================================

  Grid Utilization
  ------------------
    Peak transformer:     146.2%
    P95 transformer:      108.2%
    Hours >100%:          5
    Peak reduction:       35.9% vs baseline
    Congestion resolved:  yes
    Headroom increase:    100%

  Economic (informational)
  --------------------------
    Max cost delta:    12.10 ct
    Mean cost delta:   -3.45 ct
    FR-06 violations:  1
    Total savings:     340 ct

  Per-type cost deltas:
    T4: mean=12.1ct, max=12.1ct, violations=1
    T7: mean=-34.1ct, violations=0
```

### 11.3 Timeseries CSV

Written to `results/timeseries_{approach}.csv`. One row per timestep with data from both runs (baseline + coordination side by side), enabling:

- Household load/PV/net curves per agent and per type
- Flex energy transfer (flex_kw, shed_kw per agent)
- Transformer loading curve
- Price trajectory
- Cost delta accumulation per agent
- **Event markers** for critical situations (grid stress, load shed, cost delta)

**Single combined CSV** — both runs in one file for direct comparison:

```
timestep,day,hour,price_ct,grid_stress,trafo_loading_pct,
hh_0_type,hh_0_load_kw,hh_0_pv_kw,
hh_0_net_kw_baseline,hh_0_net_kw_coord,
hh_0_flex_kw_baseline,hh_0_flex_kw_coord,
hh_0_shed_kw_baseline,hh_0_shed_kw_coord,
hh_0_shed_active,
hh_0_step_cost_ct_baseline,hh_0_step_cost_ct_coord,
hh_0_cumulative_cost_ct_baseline,hh_0_cumulative_cost_ct_coord,
hh_0_violation_flag,
hh_1_type,...
```

Global columns:

| Column | Unit | Description |
|--------|------|-------------|
| `timestep` | — | Step index (0–N-1) |
| `day` | — | Day of year (1–365) |
| `hour` | — | Hour of day (0–23) |
| `price_ct` | ct/kWh | EPEX Spot price |
| `grid_stress` | 0/1 | **Event marker:** transformer loading ≥ 100% this timestep |
| `trafo_loading_pct` | % | Transformer utilization from load flow |

Per-household columns:

| Column | Unit | Description |
|--------|------|-------------|
| `hh_{i}_type` | — | Household type (T1–T10) |
| `hh_{i}_load_kw` | kW | Load consumption |
| `hh_{i}_pv_kw` | kW | PV generation |
| `hh_{i}_net_kw_baseline` | kW | Net grid import (+=import, -=export), baseline |
| `hh_{i}_net_kw_coord` | kW | Net grid import, coordination |
| `hh_{i}_flex_kw_baseline` | kW | Flex accepted (0 in baseline) |
| `hh_{i}_flex_kw_coord` | kW | Flex accepted in coordination |
| `hh_{i}_shed_kw_baseline` | kW | Load shed amount (0 in baseline) |
| `hh_{i}_shed_kw_coord` | kW | Load shed amount in coordination |
| `hh_{i}_shed_active` | 0/1 | **Event marker:** this household shed this timestep (coordination only) |
| `hh_{i}_step_cost_ct_baseline` | ct | Cost for this timestep only, baseline |
| `hh_{i}_step_cost_ct_coord` | ct | Cost for this timestep only, coordination |
| `hh_{i}_cumulative_cost_ct_baseline` | ct | Running total cost, baseline |
| `hh_{i}_cumulative_cost_ct_coord` | ct | Running total cost, coordination |
| `hh_{i}_violation_flag` | 0/1 | **Event marker:** cumulative cost delta > 0.01 ct (informational) |
| `hh_{i}_opt_out_baseline` | 0/1 | Agent in opt-out cooldown (always 0 in baseline) |
| `hh_{i}_opt_out_coord` | 0/1 | Agent in opt-out cooldown |

At 10 households: ~65 columns × 8,760 rows, ~5 MB. Openable in Excel or Python.

**Plotting recipes:**

| Visualization | How |
|---------------|-----|
| Household usage/production | Plot `hh_{i}_load_kw`, `hh_{i}_pv_kw`, `hh_{i}_net_kw_baseline` |
| Flex transfer events | Plot `hh_{i}_flex_kw_coord` over time |
| Transformer load | Plot `trafo_loading_pct`; shade regions where `grid_stress=1` |
| Coordination effect | Overlay `hh_{i}_net_kw_baseline` vs `hh_{i}_net_kw_coord` |
| Cost delta tracking | Plot `hh_{i}_cumulative_cost_ct_coord - hh_{i}_cumulative_cost_ct_baseline`; mark `hh_{i}_violation_flag` crossings |
| Shed events | Scatter `hh_{i}_shed_active` on any chart |

---

## 12. Metrics

### 12.1 Grid Utilization (primary)

| Metric | Definition | Interpretation |
|--------|------------|----------------|
| `peak_reduction_pct` | (baseline_peak - coord_peak) / baseline_peak × 100 | How well coordination shaves peaks |
| `congestion_events_baseline` | Steps where baseline trafo loading ≥ 100% | Unmitigated overload events |
| `congestion_events_coord` | Steps where coordinated trafo loading ≥ 100% | Residual overload after coordination |
| `congestion_resolved` | `congestion_events_baseline > 0` and `congestion_events_coord == 0` | Did coordination eliminate all overloads? |
| `hours_above_90pct_baseline` | Baseline steps > 90% loading | Near-critical utilization before coordination |
| `hours_above_90pct_coord` | Coordinated steps > 90% loading | Near-critical utilization after coordination |
| `hours_above_80pct_baseline` / `hours_above_80pct_coord` | Same for 80% threshold | Moderate stress comparison |
| `headroom_increase_pct` | (100 - coord_peak) / (100 - baseline_peak) × 100 | Extra capacity headroom unlocked |

**Pass/fail criterion:** `congestion_events_coord == 0` → exit 0 (grid safe). Otherwise exit 1 (grid unsafe even with coordination).

### 12.2 Grid (secondary)

| Metric | Definition |
|--------|------------|
| `max_trafo_loading_pct` | Maximum transformer utilization (coordinated) |
| `p95_trafo_loading_pct` | 95th percentile loading (coordinated) |
| `hours_above_100pct` | Coordinated hours exceeding transformer rating |
| `hours_above_90pct` | Coordinated hours above 90% |

### 12.3 Economic (informational)

| Metric | Definition | Interpretation |
|--------|------------|----------------|
| `max_cost_delta_ct` | max_i (coord_cost_i - baseline_cost_i) | Worst-case household loss |
| `mean_cost_delta_ct` | average across all households | Negative = system saves money |
| `total_savings_ct` | sum(baseline_cost) - sum(coord_cost) | Total neighborhood benefit |
| `violations_count` | number of households with delta > 0.01 ct | Informational — not a pass/fail criterion |
| `per_type` | per-type mean, max, violation count | Identifies systematically disadvantaged types |

Economic metrics are informational only. Infrastructure safety is the sole hard constraint (see §2a priority hierarchy).

### 12.4 Shed & opt-out

| Metric | Source | Description |
|--------|--------|-------------|
| `shed_events` | per_agent | Count of load shed activations for this agent |
| `opt_out_timesteps` | per_agent | Total timesteps spent in opt-out cooldown |

---

## 13. Implementation

### 13.1 Technology stack

| Component | Choice | Version |
|-----------|--------|---------|
| Language | Python | 3.11+ |
| Grid simulation | pandapower | ≥2.14 |
| Array handling | numpy | ≥1.24 |
| CSV/data loading | pandas | ≥2.0 |
| Configuration | PyYAML | ≥6.0 |

pandas is required only for OPSD CSV loading. When `data_source: synthetic`, the simulation runs without pandas.

### 13.2 Directory structure

```
simulation_v2/
├── sim.py              # Entry point (CLI + config load + results)
├── core.py             # Types, loop, cost function, synthetic data
├── agents.py           # T1–T10 flex curves + offers + opt-out
├── coordinator.py      # Approaches A–I + priority shed + opt-out
├── grid.py             # pandapower network builder + load flow
├── data_loader.py      # OPSD time_series + household CSV loading
├── configs/
│   ├── default.yaml    # Default configuration (synthetic data)
│   └── opsd.yaml       # OPSD-based configuration (year: 2017)
├── opsd_data/
│   ├── .gitignore      # Ignores CSV files (too large for git)
│   ├── time_series_60min_singleindex.csv     # ~124 MB (downloaded)
│   └── household_data_60min_singleindex.csv  # ~36 MB (downloaded)
└── requirements.txt    # Python dependencies
```

6 source files (~800 lines total), compared to 13+ files (~1,500 lines) in v1.

### 13.3 Dependencies

```
pandapower>=2.14
numpy>=1.24
pandas>=2.0      # required for OPSD CSV loading
pyyaml>=6.0
```

---

## 14. Limitations

| Limitation | Impact | Reason |
|------------|--------|--------|
| No SOC tracking | Battery agents overestimate availability within a day (no charge/discharge cycle limit beyond daily budget) | Acceptable simplification for fairness: captures first-order economic cost (min_price) and daily energy limitation (budget) |
| Flex curves are type-constant | Same flexibility curve for all agents of the same type regardless of battery size, PV capacity, or consumption level | Simplification: individual differences are smoothed over; type-level fairness results still valid |
| No EV schedule | EV flexibility available throughout connection window regardless of actual trip needs | Overestimates EV shiftability; min_price captures willingness-to-shift |
| No thermal dynamics | Heat pump flexibility always available during daytime regardless of actual heating demand | Conservative: real heat pumps have more flexibility during cold weather |
| No user behavior | Manual overrides, non-economic decisions, social factors not captured | Requires field pilot |
| No communication errors | Assumes perfect message delivery | Not needed for fairness comparison |
| Single grid topology | Results may not generalize to all LV grids | Configurable via feeder_config |
| Hourly resolution | Misses sub-hour dynamics (PV cloud transients, intra-hour EV charging) | 4× cheaper computationally; sufficient for economic fairness (settlement is 15-min minimum in real systems) |
| No self-optimization in baseline | Baseline is simply `load - pv` without battery arbitrage or EV scheduling | Baseline and coordination use the same simplified model; the delta captures the coordination effect, not the EMS optimization effect |
| Prototype scope | Phase 1 individual limits are not explicitly enforced | Per discussion: this is a Phase 2 prototype; the grid model (transformer capacity) provides the physical constraint |

---

## 15. References

| Document | Section | Relation |
|----------|---------|----------|
| fairness-analysis.md | §4 | Approach catalog (A–I) |
| fairness-analysis.md | §2 | Household type economic analysis |
| simulation-plan.md | §2 | Architecture design |
| Requirements.md | §3 FR-06 | Economic fairness (informational metric) |
| Requirements.md | §6 UC-04 | Load shed priority order (wallbox → battery → heat pump) |
| Requirements.md | §2b | 10 household types with pricing models |
| Requirements.md | §2a | Priority hierarchy (infrastructure > fairness) |
| Brainstorming.md | §6 | Phase 2 coordination architecture |
| Brainstorming.md | §5.2 | Phase 2 coordinator functions |
| AGENTS.md | Architecture | Phase 2 invariants, no balancing accounting |
| OPSD Time Series | §8.5 | Real German prices, PV, and load (2015–2020) — [data.open-power-system-data.org/time_series/2020-10-06/](https://data.open-power-system-data.org/time_series/2020-10-06/) |
| OPSD Household Data | §8.5 | Real household load and device data from CoSSMic project — [data.open-power-system-data.org/household_data/2020-04-15/](https://data.open-power-system-data.org/household_data/2020-04-15/) |
| ENTSO-E Transparency | §8.5 | Primary data source for OPSD Time Series — [transparency.entsoe.eu](https://transparency.entsoe.eu/) |
| CoSSMic Project | §8.5 | Primary data source for OPSD Household Data — [cossmic.eu](https://cossmic.eu/) |

---

## 16. Changes from v1

| Aspect | v1 | v2 | Rationale |
|--------|----|----|-----------|
| Resolution | 15 min | 60 min | 4× faster; sufficient for fairness (settlement is 15-min minimum) |
| Agent model | Full EMS (SOC, arbitrage, EV schedule, thermal) | Flex curve + min_price + daily budget | 10× simpler, same first-order decision boundary |
| Agent state | battery_soc, ev_soc, thermal_temp, cumulative costs | remaining_daily_kwh, opt_out_steps | From 4+ state variables to 2 |
| Baseline action | Self-optimized (arbitrage, pre-heat, cheap charging) | `load - pv` only | Removes EMS optimization from baseline/coordination delta |
| Load shed | Broadcast to all agents (same signal) | Priority tiers: T7 → T4/T5/T10 → T6 | Implements UC-04 requirement |
| Opt-out | None | 48h cooldown after load shed | Household-level protection after forced shed |
| Comms model | LoRa duty cycle tracking | Removed | Not needed for fairness analysis |
| Data generation | BDEW profiles, lognormal price, irradiance model | Hourly arrays + noise + optional OPSD | OPSD datasource adds real 2019 German data |
| Data sources | Built-in synthetic only | Synthetic + OPSD Time Series + OPSD Household Data | Two modes: fast synthetic or realistic OPSD |
| File count | 13+ source files | 6 + data loaders | Easier to maintain |
| Lines of code | ~1,500 | ~800 | 47% reduction |
| Dependencies | 7 packages (pandapower, numpy, pandas, matplotlib, seaborn, pyyaml, requests) | 4 packages (pandapower, numpy, pandas, pyyaml) | pandas readded for OPSD CSV loading; synthetic mode runs without it |
| Phase 1 limits | Explicitly enforced via `grid_limit_w` | Not enforced (prototype scope) | Per discussion: grid model provides physical constraint |
