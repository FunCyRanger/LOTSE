# Simulation Plan — Grid + Fairness Simulation

**Purpose:** Validate FR-06 fairness approaches (fairness-analysis.md) under realistic grid and market conditions before Phase 2 implementation.

---

## 1. Questions the Simulation Answers

| Question | How the simulation answers it |
|----------|------------------------------|
| Does Approach X violate FR-06? | Dual-run comparison: per-household cost delta |
| Which approach is most fair across all 10 household types? | Rank by max cost delta, Gini of cost distribution |
| How does the household type mix affect fairness? | Sensitivity sweeps: vary T1–T10 ratios |
| Is the communication load within LoRa 1% duty cycle at 100+ households? | Message count per agent per hour |
| How often does "infrastructure > fairness" override actually fire? | Fraction of timesteps where transformer/voltage limits are exceeded |
| What parameter values work? (budget size, rotation period, emergency threshold) | Parametric sweeps over each approach's tunable parameters |
| Is gaming detectable in price-based approaches? | Strategic bidding vs. honest bidding comparison runs |

It does NOT answer: real EMS behavior fidelity, user behavior (manual overrides), packet loss effects, social dynamics. Those require field testing.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Simulation Core                       │
│  Discrete-time loop (Δt = 15 min, 1 year default)       │
│  Orchestrates: Agents → Coordinator → Grid → Metrics    │
│  Dual-run: baseline run vs. coordination run            │
└──────────┬──────────┬──────────┬────────────────────────┘
           │          │          │
     ┌─────▼────┐ ┌──▼───┐ ┌───▼────────┐
     │ Agent    │ │Coord.│ │ Grid Model │
     │ Layer    │ │Layer │ │ (pandapwr) │
     │ 10 types │ │ A-I  │ │ LV feeder  │
     │ EMS sim  │ │strat.│ │ load flow  │
     └──────────┘ └──────┘ └────────────┘
```

### 2.1 Simulation Core

**Time model:**
- Discrete steps, Δt = 15 minutes (96 steps/day, 35,040 steps/year)
- Configurable duration: 1 month (debug), 1 year (full analysis), multi-year (parameter sweeps)
- Each step: load→agent→coordinator→grid→metrics

**Dual-run:**
- Run A (baseline): Each agent self-optimizes without coordination signals. Grid computed but no inter-agent messaging.
- Run B (coordination): Same inputs, same agents, but coordinator broadcasts flex requests / load shed per selected approach.
- FR-06 check: `cost(hh, run_B) <= cost(hh, run_A)` for every household

### 2.2 Agent Layer

Each household type has a simplified EMS model. The models are not full EMS simulations — they capture the economic decision boundary that matters for fairness.

| Type | EMS Model | Decision Logic |
|------|-----------|----------------|
| T1 | No control | Consume load as-is. No flexibility to offer. |
| T2 | PV self-consumption | Export PV surplus at EEG rate. Rejects any curtailment request (loses revenue). |
| T3 | PV + spot | Export at spot price. Accepts curtailment only if spot < 0 (beneficial). |
| T4 | PV + battery arb. | Battery: charge when price below threshold, discharge when above. PV: self-consume, export surplus. Flexibility: can shift battery schedule. |
| T5 | Battery arbitrage | Pure price follower: charge at low price, discharge at high (spread > round-trip loss). Flexibility: shift schedule if compensated. |
| T6 | Heat pump + §14a | Thermal storage model: pre-heat when price low or §14a inactive. Default: heat on demand. |
| T7 | EV charging | Schedule charge within connection window (configurable arrival/departure). Flexibility: shift within window. |
| T8 | Mixed | Composition of T4 + T6 + T7. Priority: heat pump → EV → battery. |
| T9 | Balcony solar | Generate fixed small PV. No control possible. |
| T10 | Balcony + battery | Small-scale arbitrage. Same logic as T5 but at lower capacity (x0.1). |

**Common agent interface:**
```
class Agent:
    type: HouseholdType
    config: AgentConfig  # limit, battery_kwh, pv_kwp, ev_kwh, etc.
    state: AgentState    # battery_soc, ev_departure, thermal_temp
    
    def baseline_action(self, timestep, price, load, pv_gen) -> Action
    def respond_to_coordination(self, signal: CoordSignal) -> Action
    def compute_financial_impact(self, actions: List[Action], price) -> float
```

### 2.3 Coordinator Layer

Pluggable fairness strategy following the approaches from fairness-analysis.md:

| Approach | Implementation |
|----------|---------------|
| A: Self-selection | No coordinator logic. Broadcasts flex requests, agents decide. |
| B: Min price | Collect offer+price from agents, sort merit order, accept lowest. |
| C: Rotation | Track per-agent participation count, rotate requests to balance. |
| D: Proportional | Compute each agent's headroom, allocate proportionally. |
| E: Merit+Budget | Like B but with cumulative budget constraint per agent. |
| F: Priority access | Two-tier: active vs. passive. Active agents get first access. |
| G: Narrow | Symmetric round-robin. No per-agent data used. |
| H: Emergency | Self-selection during normal; proportional during grid stress. |
| I: Hybrid (B+C) | Min price + rotation budget tiebreaker. |

Each strategy implements:
```
class FairnessStrategy:
    def process_flex_offers(self, offers: List[FlexOffer], demand_kw: float) -> List[Acceptance]
    def process_load_shed(self, state: GridState) -> ShedOrder
    def update_tracking(self, accepted: List[Acceptance])
    def get_threshold(self) -> float  # for emergency detection
```

### 2.4 Grid Layer

**Network model (pandapower):**

A configurable German LV feeder:
- Transformer: 400 kVA or 630 kVA, 20/0.4 kV
- 1–4 feeders, each with 5–40 households
- Cable types: NA2XY 4×150 mm² (main), 4×35 mm² (service)
- Household connection: 30–63 A fuse
- Per-household limit: 5–30 kW (configurable per type)

**Configuration-driven topology:**
```
network_config = {
    "transformer_kva": 630,
    "n_feeder": 3,
    "households_per_feeder": [35, 35, 30],  # total 100
    "feeder_length_km": [0.3, 0.5, 0.2],
    "cable_per_feeder": "NA2XY-4x150",
}
```

**Load flow:** AC unbalanced, computed at each timestep. Outputs: transformer loading, voltage at each bus, line loading, losses.

**Scenarios:**
- Normal: all households within limits
- Stress: high PV + high EV (summer midday + evening peak)
- Emergency: near or at transformer limit
- §14a event: stochastic reduction signals

### 2.5 Communication Model

Tracks LoRa duty cycle for each agent:
- Payload size per message type (from Brainstorming §4)
- Time on air (SF, bandwidth, payload → calculate with RadioLib parameters)
- 1% duty cycle: sum of tx_time / window_time <= 0.01
- At 100+ agents: broadcast is O(1), agent→coordinator is O(N)

**Metrics logged:**
- Messages sent per agent per hour
- Cumulative duty cycle utilization
- Collisions / contention (simplified probability model)

---

## 3. Input Data

### 3.1 EPEX Spot Prices

| Detail | Value |
|--------|-------|
| Source | SMARD.de (Bundesnetzagentur) or ENTSO-E Transparency Platform |
| Format | CSV, hourly resolution |
| Year | 2023 or 2024 (most recent complete) |
| Access | Free, no registration for SMARD |
| Fallback | Synthetic price model (mean-reverting with seasonality) |

### 3.2 Load Profiles

| Type | Source | Notes |
|------|--------|-------|
| Household (H0) | BDEW standard load profile | 15-min or hourly, scaled by annual consumption |
| EV charging | Synthetic from mobility data | Arrival/departure times, daily energy |
| Heat pump | Synthetic from temperature data | COP-dependent, thermal storage model |
| Balcony solar | Same as PV but scaled | ~300–600 Wp |

### 3.3 PV Generation

| Detail | Value |
|--------|-------|
| Source | Synthesized from DWD irradiance data or standard PVGIS |
| Resolution | 15-min or hourly |
| Orientation | South-facing, 30° tilt (default) |
| Capacity | Configurable per household (0–15 kWp) |

### 3.4 §14a Events

Stochastic model:
- Frequency: 1–10 events per year per grid operator (calibrated to BNetzA statistics)
- Duration: 1–3 hours per event
- Reduction: 4.2 kW per device (standard §14a setpoint)
| Affected devices | Heat pump, EV wallbox (configurable per household) |

---

## 4. Household Type Configuration

Each simulation run defines a household mix:

```python
household_mix = {
    T1: 0.10,   # No PV
    T2: 0.15,   # PV only (EEG)
    T3: 0.05,   # PV only (Dynamic)
    T4: 0.20,   # PV + Battery
    T5: 0.05,   # Battery only
    T6: 0.10,   # Heat pump
    T7: 0.10,   # EV + Wallbox
    T8: 0.10,   # Mixed (EV+HP+Battery+PV)
    T9: 0.10,   # Balcony solar
    T10: 0.05,  # Balcony solar + Battery
}
```

Each type also has a set of default config parameters:

```python
type_defaults = {
    T2: {"pv_kwp": 7.0, "eeg_ct_per_kwh": 8.2},
    T4: {"pv_kwp": 10.0, "battery_kwh": 10.0, "battery_kw": 5.0},
    T7: {"ev_kwh": 50.0, "ev_kw": 11.0, "arrival_hour": 17, "departure_hour": 8},
    ...
}
```

The mix and parameters are varied in sensitivity sweeps to test how the fairness approach performs across different neighborhood compositions.

---

## 5. Metrics

### 5.1 Fairness (FR-06) Metrics

| Metric | Definition | Pass/Fail |
|--------|------------|-----------|
| Max cost delta | max_hh (cost_baseline_hh - cost_coord_hh) | FAIL if any positive |
| Mean cost delta | average across all households | Should be negative (system saves money) |
| Cost delta range | max - min | Spread of outcomes |
| Gini of cost delta | distribution of savings/losses | 0 = equal, 1 = concentrated |
| Worst-off type | which household type has largest cost delta | Identifies systematically disadvantaged types |
| Opt-out rate | fraction of timesteps where households opt out | High opt-out may indicate misaligned incentives |

### 5.2 Grid Metrics

| Metric | Definition |
|--------|------------|
| Peak transformer load | Max kVA / rating |
| Peak reduction vs baseline | % |
| Voltage violations | % of timesteps outside ±10% |
| Line loading violations | % of timesteps above 100% |
| Energy curtailed | Total kWh curtailed vs. baseline export |
| Load shed events | Count and depth of load shed activations |

### 5.3 Communication Metrics

| Metric | Definition |
|--------|------------|
| Messages/agent/hour | Per-agent message count |
| Duty cycle utilization | % of 1% limit used by each agent |
| Total neighborhood messages | Sum across all agents |
| Payload bytes per message | Average and max |

---

## 6. Outputs

The simulation produces:
- **per-household-timeseries.csv** — for each household: timestep, load, PV, import/export, cost, flex offers, accepted/rejected
- **fairness-report.json** — summary of FR-06 compliance per approach and per type
- **grid-stats.csv** — transformer loading, voltage, losses per timestep
- **communication-report.json** — duty cycle, message counts
- **plots/** — time series, histograms, sensitivity curves

Key plots:
1. Cost delta distribution (histogram, per approach)
2. Cost delta per household type (grouped bar chart)
3. Transformer peak reduction (time series, baseline vs. coordination)
4. Sensitivity: fairness metric vs. household mix (heat map)
5. Parameter sweep: budget size vs. FR-06 violation rate (line chart)

---

## 7. Parameters to Sweep

| Parameter | Values to test | Rationale |
|-----------|----------------|-----------|
| Household mix | 5 different compositions | Vary PV-heavy, EV-heavy, balanced |
| Neighborhood size | 10, 50, 100, 200 | Scalability test |
| Grid limit / headroom | Tight (90% utilization) vs. Loose (60%) | Stress test fairness override |
| Time horizon | 1 month, 3 months, 1 year | Seasonal effects |
| §14a event frequency | None, low, high | Interaction test |
| Approach-specific parameters | Budget reset period, rotation interval, emergency threshold | Tuning |

---

## 8. Implementation

### 8.1 Technology Stack

| Component | Choice | Reason |
|-----------|--------|--------|
| Language | Python 3.11+ | pandapower, numpy ecosystem |
| Grid simulation | pandapower | Industry standard for LV load flow |
| Data handling | pandas, numpy | Time series, matrix operations |
| Configuration | YAML or TOML | Human-readable run configs |
| Plots | matplotlib + seaborn | Standard visualization |
| Parameter sweep | custom loop or optuna | Lightweight, no heavy framework needed |
| Entry point | CLI: `python sim.py --config configs/default.yaml` | Simple, scriptable |

### 8.2 Directory Structure

```
simulation/
├── sim.py                 # Entry point
├── core/
│   ├── loop.py            # Main simulation loop
│   └── dual_run.py        # Baseline vs. coordination orchestration
├── agents/
│   ├── base.py            # Agent base class
│   ├── types.py           # T1–T10 agent implementations
│   └── config.py          # Type defaults and config schema
├── coordinator/
│   ├── base.py            # FairnessStrategy base class
│   ├── approach_a.py      # Self-selection
│   ├── approach_b.py      # Minimum price
│   ├── approach_c.py      # Rotation tracking
│   ├── approach_d.py      # Proportional
│   ├── approach_e.py      # Merit + budget
│   ├── approach_f.py      # Priority access
│   ├── approach_g.py      # Narrow (symmetric)
│   ├── approach_h.py      # Emergency
│   └── approach_i.py      # Hybrid (B+C)
├── grid/
│   ├── network.py         # pandapower network builder
│   └── loadflow.py        # Run load flow, collect results
├── data/
│   ├── loader.py          # Load EPEX, profiles, PV
│   └── profiles/          # Cached profile data
├── metrics/
│   ├── fairness.py        # FR-06 metrics
│   ├── grid_metrics.py    # Grid performance
│   └── comms.py           # Communication load
├── output/
│   └── plots.py           # Plotting helpers
├── configs/
│   ├── default.yaml       # Default run config
│   └── sweep/             # Configs for parameter sweeps
└── requirements.txt
```

---

## 9. Usage

```bash
# Single run
python sim.py --config configs/default.yaml

# Parameter sweep (vary household mix)
python sim.py --sweep mix --values "balanced,pv_heavy,ev_heavy"

# Compare approaches
python sim.py --approach A --approach B --approach I

# Dry-run / debug (1 day, verbose)
python sim.py --days 1 --verbose
```

### 9.1 Dependencies

```
pandapower>=2.14
numpy>=1.24
pandas>=2.0
matplotlib>=3.7
seaborn>=0.12
pyyaml>=6.0
```

---

## 10. Limitations (Documented)

| Limitation | Impact | Mitigation |
|------------|--------|------------|
| Simplified EMS models | Real EMS behavior (OpenEMS, evcc) may differ | Model parameters calibrated to literature; field validation planned |
| No user behavior model | Manual overrides, non-economic decisions not captured | Noted; field pilot needed to calibrate |
| No communication errors | Assumes perfect message delivery | Add packet loss model in later iteration |
| Synthetic load/PV profiles | May miss local weather/consumption patterns | Use real data where available; sensitivity sweep covers variability |
| §14a model is stochastic | Grid operator behavior is jurisdiction-specific | Make event parameters configurable per region |
| Single grid topology | Results may not generalize to all LV grids | Test 2–3 different topologies in sweep |

---

## 11. Relationship to Existing Documents

| Document | Where simulation feeds in |
|----------|--------------------------|
| fairness-analysis.md | Simulation tests all 9 approaches (A–I) from the catalog |
| Requirements.md §3 (FR-06) | Simulation quantifies FR-06 compliance |
| Brainstorming.md §8 Q6 | Simulation results inform flex matching algorithm decision |
| Brainstorming.md §8 Q7 | Simulation determines data retention needs for tracking-based approaches |
| Brainstorming.md §10 rec. 6 | This is the implementation of recommendation 6 |
| prototype-build.md | Simulation parameters (duty cycle, message sizes) calibrated from prototype |
