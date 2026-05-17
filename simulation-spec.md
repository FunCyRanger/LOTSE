# FR-06 Fairness Simulation — Specification

**Purpose:** Evaluate fairness approaches (fairness-analysis.md §4) under realistic grid and market conditions.
**Implements:** simulation-plan.md.
**Prerequisite for:** Phase 2 coordination algorithm selection.

---

## 1. Overview

The simulation tests whether a coordination strategy violates FR-06 (no household is financially worse off than without the system). It does this by running **two passes** over the same input data:

- **Baseline pass (Run A):** Each household's EMS model self-optimizes. No inter-household coordination signals. This is the counterfactual "without the system."
- **Coordination pass (Run B):** Same agents, same external conditions. A coordinator broadcasts flex requests or load shed signals per a selected fairness approach. Agents may deviate from their baseline action in response.

**FR-06 is violated** if any household's cumulative cost in Run B exceeds its cumulative cost in Run A.

### 1.1 What it tests

- Detection of FR-06 violations per approach and per household type
- Ranking of approaches by fairness, grid benefit, and communication load
- Sensitivity to neighborhood composition (mix of T1–T10)
- Parameter sensitivity (budget size, rotation period, emergency threshold)
- Communication feasibility under LoRa 1% duty cycle at 100+ households

### 1.2 What it does not test

- Real EMS behavior (the models are simplified decision boundaries)
- User behavior (manual overrides, non-economic decisions)
- Communication errors (packet loss, latency, collisions)
- Social dynamics (neighbor pressure, opt-out psychology)
- Specific real-neighborhood outcomes (requires field pilot)

---

## 2. Architecture

```
                         Simulation Core
         ┌─────────────────────────────────────────┐
         │  Discrete-time loop, Δt = 15 min        │
         │  96 steps/day × 365 days = 35,040 steps │
         │                                         │
         │  Per step:                              │
         │  1. Read price, load, PV for timestep   │
         │  2. Each agent: baseline_action()        │
         │  3. Record baseline cost                │
         │  4. Coordinator: process_flex/shed()    │
         │  5. Each agent: coordination_action()   │
         │  6. Record coordination cost            │
         │  7. Every 4 steps: run load flow        │
         └────┬──────────┬──────────┬──────────────┘
              │          │          │
     ┌────────▼──┐ ┌────▼───┐ ┌───▼──────────┐
     │ Agent Layer│ │Coord.  │ │ Grid Model   │
     │ 10 types  │ │Layer   │ │ (pandapower) │
     │ T1–T10    │ │ A–I    │ │ LV feeder    │
     │ EMS logic │ │strat.  │ │ load flow    │
     └───────────┘ └────────┘ └──────────────┘
```

### 2.1 Simulation loop

For each timestep:

1. **External state:** Read synthetic EPEX price, load profile value, PV generation for current timestep.
2. **Baseline actions:** Each agent computes `baseline_action(td)` — what the household would do without coordination. Resulting action includes `net_grid_kw`, battery dispatch, EV charging, etc.
3. **Baseline cost:** `action.cost_ct(price, config, dt_h)` computes the financial cost of this action under the household's pricing model.
4. **Grid utilization:** Sum of all agents' `net_grid_kw` / total neighborhood limit → `grid_utilization_pct`.
5. **Coordinator signals:** The fairness strategy's `process_flex()` and `process_load_shed()` generate `CoordSignal` per agent.
6. **Coordination actions:** Each agent computes `coordination_action(td, signal)` — may deviate from baseline based on the received signal.
7. **Coordination cost:** Same cost function applied to the coordinated action.
8. **Load flow** (every 4 steps): Run pandapower AC unbalanced load flow on the LV network. Record transformer loading, voltages, line loads.
9. **Communication accounting:** Increment message counters per agent.

### 2.2 Dual-run equivalence

Both runs see identical external conditions (price, load, PV) at every timestep. Agent internal state (battery SOC, EV SOC, thermal storage temperature) evolves independently per run. The baseline run's state trajectory represents "what would have happened without coordination." The coordination run's state trajectory may diverge because the agent responds to signals.

### 2.3 Faithfulness to the real system

The simulation mirrors the Phase 2 architecture (Brainstorming §6):
- Agents are autonomous — they decide whether to respond to signals
- Coordination is voluntary (except during grid emergencies where infrastructure > fairness)
- No balancing accounting — the system never settles payments
- Phase 1 individual limits remain the hard ceiling (agents refuse requests that would exceed their limit)

---

## 3. Timestep Model

| Parameter | Default | Description |
|-----------|---------|-------------|
| `timestep_min` | 15 | Simulation time step in minutes |
| `duration_days` | 365 | Total simulation duration |
| `year` | 2023 | Reference year for profiles and date indexing |
| Steps per run | 35,040 | 96 steps/day × 365 days |

At each timestep, the simulation builds a `TimestepData` struct:

```
TimestepData {
    price_ct: float       // synthetic EPEX price in ct/kWh
    load_w: float         // household load in W (from BDEW profile)
    pv_w: float           // PV generation in W (from solar model)
    hour: int             // hour of day (0–23)
    dayofyear: int        // day of year (1–365)
    dt_h: float           // timestep duration in hours
    par14a_active: bool   // §14a curtailment event active
}
```

---

## 4. Data Model

### 4.1 Core types

| Type | Fields | Purpose |
|------|--------|---------|
| `TimestepData` | price_ct, load_w, pv_w, hour, dayofyear, dt_h, par14a_active | External state at one timestep |
| `AgentConfig` | household_type, pv_kwp, battery_kwh, ev_kwh, hp_kw, grid_limit_w, tariff_rate_ct, eeg_rate_ct, ... | Static household parameters |
| `AgentState` | battery_soc, ev_soc, thermal_temp, cumulative costs, flex counters | Dynamic per-agent state |
| `Action` | net_grid_kw, curtailment_kw, battery_charge/discharge_kw, ev_charge_kw, hp_kw, shed_kw | Energy action at one timestep |
| `CoordSignal` | flex_request_kw, load_shed, reduction_pct | Coordination signal from coordinator to agent |
| `SimulationResult` | agent_results, grid_results, fairness_metrics, grid_summary, comms_summary, per_agent | Full simulation output |

### 4.2 Action cost function

The cost of an action depends on the household type's pricing model:

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

### 5.1 Common interface

```python
class BaseAgent:
    def baseline_action(self, td: TimestepData) -> Action
    def coordination_action(self, td: TimestepData, signal: CoordSignal) -> Action
    def compute_flexibility(self, action: Action) -> float  # headroom to limit
```

Each type implements a simplified EMS logic capturing the relevant economic decision boundary.

### 5.2 Per-type specification

| Type | Baseline logic | Coordination response | Notes |
|------|---------------|---------------------|-------|
| T1 | Consume load: `net = load` | No response | No flexibility |
| T2 | Self-consume PV, export surplus at EEG rate | Curtails PV only under load shed with reduction_pct | Loses EEG revenue when curtailed |
| T3 | Same as T2, export at spot price | Curtails PV if price < 0 (beneficial) or under load shed | Negative-price curtailment is financially beneficial |
| T4 | Battery arbitrage: charge when price < threshold, discharge when price > threshold. PV self-consumed | On load shed: discharge battery if SOC > 30% | State: battery SOC. Round-trip efficiency 90% |
| T5 | Pure price arbitrage: charge < 6 ct/kWh, discharge > 8 ct/kWh | On load shed: same forced discharge | No PV, no load |
| T6 | Heat pump with 45°C thermal setpoint. Pre-heat when price < 3 ct/kWh. COP=3.5. Thermal buffer 30 kWh. | On load shed or flex request: shed heat pump if thermal temp > 35°C | Respects §14a active state (does not heat during §14a events) |
| T7 | EV charges within connection window (arrival 17:00–departure 8:00) if SOC < 90% | On load shed: stop EV charging | State: EV SOC. Always finds a "cheapest window" (simplified) |
| T8 | Composes T6 + T7 + T4 in priority order: heat pump first, then EV, then battery | Same as baseline (no additional coordination response) | State shared across sub-models |
| T9 | Balcony solar: `net = load - small_pv` | No response | No digital control |
| T10 | Balcony solar + small battery: same logic as T5 at 1/5 scale | No response | Limited flexibility |

### 5.3 Agent state

State persisted across timesteps and evolves independently in baseline vs. coordination runs:

- `battery_soc`: 0–1, updated by charge/discharge with 90% round-trip efficiency
- `ev_soc`: 0–0.9, charged at 95% efficiency within connection window
- `thermal_temp`: 20–60°C, driven by heat pump input and passive cooling

### 5.4 Flexibility computation

`compute_flexibility(action)` returns headroom in kW:
```
headroom = (grid_limit_w - max(0, net_grid_kw × 1000)) / 1000
```
This is the amount of additional import the household could accept without exceeding its Phase 1 individual limit.

---

## 6. Coordinator Strategies (A–I)

### 6.1 Common interface

```python
class FairnessStrategy:
    def process_flex(self, agents, actions, demand_kw: float) -> list[CoordSignal]
    def process_load_shed(self, agents, actions, grid_utilization_pct: float) -> list[CoordSignal]
```

`process_flex` is called during normal operation. `process_load_shed` is called when grid utilization exceeds 100%. The shed signal overrides the flex signal if both are active.

### 6.2 Per-approach specification

| Approach | Flex selection logic | Load shed logic | State kept |
|----------|---------------------|-----------------|------------|
| **A: Self-Selection** | Round-robin: split demand equally | Shed all at 20% reduction if util ≥ 100% | None |
| **B: Min Price** | Sort offers by self-assessed price, accept cheapest first. T2 price = EEG rate, others = 3 ct/kWh | Same as A | `participation_score` per agent |
| **C: Rotation** | Sort eligible agents by cumulative contribution (lowest first), accept from least-used | Same as A | `scores` per agent |
| **D: Proportional** | Each agent contributes flex_headroom / total_headroom × demand | Shed proportional to (util% - 90%) | None |
| **E: Merit+Budget** | Like B but with cumulative `max_budget_kwh` cap per 30-day period | Same as A | `budget` per agent |
| **F: Priority** | Sort agents by cumulative contribution (highest first), most-contributing get first access. Contributions tracked + shed events credited at 50% | Same as A | `contributions` per agent |
| **G: Narrow** | Round-robin: cycle through agent indices, regardless of flexibility or type | Same as A | `last_idx` |
| **H: Emergency** | Normal: same as A. Emergency: proportional shed | Proportional shed by headroom share | None |
| **I: Hybrid B+C** | Sort by min price, tie-break by budget used (lowest first). Budget cap = 30 kWh | Same as A | `budget` per agent |

### 6.3 Load shed trigger

All approaches use the same load shed trigger:
- If `grid_utilization_pct >= 100`: broadcast `load_shed=True` with `reduction_pct=20` (or calculated).
- The load shed signal is a **hard recommendation** — agents may refuse (but infrastructure safety overrides fairness per the priority hierarchy).

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
- Computed every 4 timesteps (hourly resolution) to keep runtime manageable
- Non-convergent cases retry with Iwamoto-NR, then mark as non-convergent

### 7.3 Household-to-bus mapping

`net._household_bus_map` maps agent index to pandapower bus index. At load flow time, each agent's `net_grid_kw / 1000` is set as the bus load in MW.

---

## 8. Input Data

### 8.1 Price model

Synthetic price in Euro-cents/kWh. Generated from four components:

1. **Base price:** Log-normal distribution, `mean=2.5, sigma=0.5` (median ~12 ct/kWh)
2. **Hour cycle:** Morning peak (hours 7–10: 1.8×), evening peak (hours 17–21: 2.0×), night trough (hours 0–6: 0.8×)
3. **Seasonal cycle:** Cosine modulation, amplitude ±30%, peak in winter
4. **Spikes:** Additional log-normal noise term

Result ranges from 0–50 ct/kWh, with occasional negative hours (simulated by the clip not removing values below 0 — the model does produce values near zero but specifically does not clip at zero; negative prices are handled by T3's self-curtailment logic).

### 8.2 Load profiles

BDEW H0 standard household load profile, seasonally differentiated:

| Season | Days | Shape characteristics |
|--------|------|----------------------|
| Winter (doy 0–90) | 90 | Morning peak 0.72, evening peak 0.72, night trough 0.26 |
| Spring (doy 90–181) | 91 | Moderate: morning 0.48, evening 0.60 |
| Summer (doy 181–273) | 92 | Low: morning 0.42, evening 0.56 |
| Fall (doy 273–365) | 92 | Medium: morning 0.50, evening 0.66 |

Profiles are scaled to `annual_consumption_kwh` per household (default 3500–5000 depending on type) and multiplied by per-household Gaussian noise `N(1.0, 0.1)`.

### 8.3 PV generation

Clear-sky irradiance model at 51°N latitude (central Germany):
```
cos_zenith = sin(lat) × sin(declination) + cos(lat) × cos(declination) × cos(15 × (solar_time - 12))
clear_sky = 1000 × cos_zenith^1.2
clouds ~ Beta(2, 5) × 0.6 + 0.4  (= cloudy days more likely than clear)
irradiance = clear_sky × clouds
pv_w = irradiance / 1000 × kWp × 1000 × 0.85
```

### 8.4 §14a events

Stochastic model (disabled by default):
- `events_per_year`: number of curtailment events (default 5)
- `max_duration_h`: per-event duration (default 3 hours)
- Events are placed randomly in the year
- When active, heat pumps (T6, T8) will not heat

---

## 9. Configuration Schema

### 9.1 YAML structure

```yaml
# Simulation parameters
duration_days: 365
timestep_min: 15
year: 2023
seed: 42

# Neighborhood
n_households: 10
grid_limit_w: 5000          # per-household Phase 1 limit (W)

# Household type mix (fractions)
household_mix:
  T1: 0.10   T2: 0.10   T3: 0.10
  T4: 0.15   T5: 0.05   T6: 0.10
  T7: 0.15   T8: 0.10   T9: 0.10   T10: 0.05

# Fairness approach (A–I)
approach: A

# Type-specific parameters
type_defaults:
  T2:  {pv_kwp: 7.0, annual_consumption_kwh: 4000}
  T4:  {pv_kwp: 10.0, battery_kwh: 10.0, battery_kw: 5.0}
  T7:  {ev_kwh: 50.0, ev_kw: 11.0, ev_arrival_hour: 17, ev_departure_hour: 8}
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

# LoRa communication model
lora:
  sf: 7
  bandwidth_khz: 125
  duty_cycle_pct: 1.0
```

### 9.2 Type-specific configuration keys

| Key | Default | Types | Description |
|-----|---------|-------|-------------|
| `annual_consumption_kwh` | 4000 | All | Scaling for load profile |
| `pv_kwp` | 0 | T2, T3, T4, T8, T9, T10 | Installed PV capacity in kWp |
| `battery_kwh` | 0 | T4, T5, T8, T10 | Battery energy capacity in kWh |
| `battery_kw` | 0 | T4, T5, T8, T10 | Battery power capacity in kW |
| `ev_kwh` | 0 | T7, T8 | EV battery capacity in kWh |
| `ev_kw` | 0 | T7, T8 | EV charging power in kW |
| `ev_arrival_hour` | 17 | T7, T8 | Hour EV arrives home |
| `ev_departure_hour` | 8 | T7, T8 | Hour EV departs for work |
| `hp_kw` | 0 | T6, T8 | Heat pump power in kW |
| `hp_buffer_kwh` | 0 | T6, T8 | Thermal buffer in kWh |
| `grid_limit_w` | 5000 | All | Phase 1 individual limit in W |

---

## 10. CLI Reference

### 10.1 Usage

```bash
python simulation/sim.py [OPTIONS]
```

### 10.2 Options

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--config` | `-c` | `configs/default.yaml` | Configuration file path |
| `--approach` | `-a` | from config | Fairness approach (A–I) |
| `--days` | `-d` | from config | Simulation duration in days |
| `--output` | `-o` | `results/` | Output directory |
| `--verbose` | `-v` | False | Print per-step progress |

### 10.3 Exit codes

| Code | Meaning |
|------|---------|
| 0 | Simulation completed, no FR-06 violations |
| 1 | Simulation completed, FR-06 violations detected |

### 10.4 Examples

```bash
# Default run (approach A, 10 households, 1 year)
python simulation/sim.py

# Specific approach, shorter duration
python simulation/sim.py --approach D --days 30

# Verbose, custom output
python simulation/sim.py --approach I --verbose --output /tmp/my_run

# Compare all approaches
for a in A B C D E F G H I; do
    python simulation/sim.py --approach $a --days 30 --output results/$a
done
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
fairness:
  max_cost_delta_ct: 12.11
  mean_cost_delta_ct: -3.45
  violations_count: 4
  gini: -2.584
  total_savings_ct: 34
  total_baseline_cost_ct: ...      # cumulative baseline cost (ct)
  total_coord_cost_ct: ...         # cumulative coordination cost (ct)
per_type:
  T4:
    count: 2
    mean_delta_ct: 12.1
    max_delta_ct: 12.1
    violations: 2
  T7:
    count: 2
    mean_delta_ct: -34.1
    max_delta_ct: -34.1
    violations: 0
  ...
grid:
  max_trafo_loading_pct: 5.2
  p95_trafo_loading_pct: 3.3
  hours_above_100pct: 0
  converged_steps: 8760
comms:
  msg_per_agent_per_hour: 12.62
  duty_cycle_used_pct: 0.001
  duty_cycle_ok: true
per_agent:
  - idx: 0
    type: T1
    baseline_cost_ct: ...
    coord_cost_ct: ...
    delta_ct: ...
    messages_sent: 10512
    flex_offers: 0
    shed_events: 0
```

### 11.2 Plots

Generated when matplotlib is available. Saved to the output directory:

- `fairness_{approach}.png`: 2×2 grid with:
  - Bar chart: per-household cost delta
  - Bar chart: per-type mean/max cost delta
  - Bar chart: grid metrics (max trafo, P95, hours >100%)
  - Bar chart: communication metrics (messages/hour, duty cycle)

---

## 12. Metrics

### 12.1 Fairness (FR-06)

| Metric | Definition | Interpretation |
|--------|------------|----------------|
| `max_cost_delta_ct` | max_i (coord_cost_i - baseline_cost_i) | Worst-case household loss |
| `mean_cost_delta_ct` | average across all households | System-level savings (negative = savings) |
| `total_savings_ct` | sum(baseline_cost) - sum(coord_cost) | Total neighborhood benefit |
| `violations_count` | number of households with delta > 0.01 ct | Binary FR-06 fail count |
| `gini` | Gini coefficient of cost deltas | Distribution equality (0 = equal) |
| `per_type` | per-type mean, max, violation count | Identifies systematically disadvantaged types |

FR-06 is technically violated if `violations_count > 0`. The priority hierarchy (§2a) permits violations during grid emergencies, but the simulation records them regardless of context.

### 12.2 Grid

| Metric | Definition |
|--------|------------|
| `max_trafo_loading_pct` | Maximum transformer utilization |
| `p95_trafo_loading_pct` | 95th percentile loading |
| `hours_above_100pct` | Number of timesteps exceeding transformer rating |
| `hours_above_90pct` | Number of timesteps above 90% |

### 12.3 Communication

| Metric | Definition |
|--------|------------|
| `total_messages` | Sum of all agent messages over the run |
| `msg_per_agent_per_hour` | Average message rate |
| `duty_cycle_used_pct` | Estimated LoRa airtime ÷ window × 100 |
| `duty_cycle_ok` | True if duty_cycle_used ≤ 1% |

Message accounting:
- 1 message per heartbeat (every timestep)
- 2 messages per flex exchange (request + response)
- 1 message per load shed event

---

## 13. Implementation

### 13.1 Technology stack

| Component | Choice | Version |
|-----------|--------|---------|
| Language | Python | 3.11+ |
| Grid simulation | pandapower | ≥2.14 |
| Data handling | pandas, numpy | ≥2.0, ≥1.24 |
| Configuration | PyYAML | ≥6.0 |
| Plots | matplotlib + seaborn | ≥3.7, ≥0.12 |

### 13.2 Directory structure

```
simulation/
├── sim.py                          # Entry point
├── requirements.txt                # Python dependencies
├── configs/default.yaml            # Default configuration
├── core/
│   ├── types.py                    # Data classes (Action, AgentConfig, etc.)
│   └── loop.py                     # Main simulation loop + dual-run
├── agents/
│   ├── base.py                     # BaseAgent abstract class
│   ├── types.py                    # T1–T10 implementations
│   └── config.py                   # Agent configuration builder
├── coordinator/
│   └── approaches.py               # Fairness strategies A–I
├── grid/
│   └── network.py                  # pandapower LV feeder + load flow
├── data/
│   └── loader.py                   # Profile generation (load, PV, price)
├── metrics/
│   └── metrics.py                  # Fairness, grid, comms metrics
└── output/
    └── plots.py                    # Plot generation
```

### 13.3 Dependencies

```
pandapower>=2.14
numpy>=1.24
pandas>=2.0
matplotlib>=3.7
seaborn>=0.12
pyyaml>=6.0
requests>=2.31
```

---

## 14. Limitations

| Limitation | Impact | Reason |
|------------|--------|--------|
| Simplified EMS models | Real OpenEMS/evcc behavior may differ, affecting absolute cost deltas | Each model captures the profit-maximizing decision boundary, not full EMS logic |
| No user behavior | Manual overrides, non-economic decisions, social pressure not captured | Would require stochastic user model with limited empirical basis |
| No communication errors | Assumes perfect message delivery | LoRa packet loss and CSMA/CA contention not modeled |
| Synthetic prices | May not capture real market dynamics (e.g., extreme spikes, negative-price clustering) | Real EPEX data can be substituted via `load_epex_spot()` |
| Single grid topology | Results may not generalize to all LV grids | Configurable: any topology can be specified in `feeder_config` |
| Simplified EV charging | EV always finds a cheapest window — no battery degradation, no departure deadline | Captures first-order flexibility but overestimates shiftability |
| Battery round-trip | Fixed 90% efficiency, no degradation, no minimum SOC reserve | Standard assumption for lithium-ion, no aging effects |
| No reactive power | Load flow uses only active power (PF=1.0) | Simplification for LV residential (typical for small customers) |
| §14a events stochastic | Grid operator behavior is jurisdiction-specific | Configurable parameters; add real event patterns from grid operator data |

---

## 15. References

| Document | Section | Relation |
|----------|---------|----------|
| fairness-analysis.md | §4 | Approach catalog (A–I) that the simulation implements |
| fairness-analysis.md | §2 | Household type economic analysis |
| fairness-analysis.md | §6 | Comparison matrix (criteria for evaluation) |
| simulation-plan.md | §2 | Architecture design |
| simulation-plan.md | §8 | Implementation guide |
| Requirements.md | §3 FR-06 | Requirement being tested |
| Brainstorming.md | §6 | Phase 2 fairness validation sketch |
| Brainstorming.md | §8 Q6, Q7 | Open decisions the simulation informs |
| Requirements.md | §2b | 10 household types with pricing models |
| Requirements.md | §2a | Priority hierarchy (infrastructure > fairness) |
