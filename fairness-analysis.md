# FR-06 Economic Fairness — Analysis (Superseded)

**Status:** Historical reference. FR-06 is now an **informational metric** — infrastructure safety is the sole hard constraint. See `simulation-spec.md` for the updated focus on grid utilization and `simulation_v2/` for the implementation.

**Based on:** Requirements.md §2b, §3 FR-06; Brainstorming §6, §8 Q6/Q7.

---

## 1. Problem Statement

**FR-06 (verbatim, Requirements.md §3):**
> The optimization logic MUST NOT apply strategies that result in financial loss to any household compared to their baseline pricing model. Each household must have visibility into the financial impact of coordination decisions and the ability to opt out of participation.

**Undefined:** The comparison algorithm, the baseline scenario, and the financial impact calculation method. Decided before Phase 2.

The core difficulty: The system is a **signaling/coordination layer** with no visibility into household-internal economics (no balancing accounting, no billing, no knowledge of individual contracts). Yet FR-06 demands that coordination never harms any household financially. This creates a fundamental tension: the entity making coordination decisions has no direct access to the information needed to verify those decisions are fair.

**Priority hierarchy (Requirements.md §2a):**
1. Infrastructure safety (non-negotiable)
2. Economic fairness
3. When they conflict, infrastructure safety always wins

**Phase 1** (individual allocation, no inter-household communication) has no fairness problem — each household self-regulates within its contractual limit. No coordination decisions affect another household's economics.

**Phase 2** adds inter-household coordination: flex offers/requests, load shed signals, optional coordinator matching. These create winners (households that benefit from neighbor flexibility) and potential losers (households that are asked to curtail or shift).

---

## 2. Household Typology & Economics

### 2.1 Type Overview

From Requirements.md §2b. Each type has a different pricing model, different optimization goal, and — critically — a different definition of what "financial loss" means.

| # | Type | Pricing Model | Optimization Goal |
|---|------|---------------|-------------------|
| T1 | No PV | Fixed tariff | Minimize consumption cost |
| T2 | PV only (EEG) | Fixed feed-in | Maximize self-consumption |
| T3 | PV only (Dynamic) | EPEX Spot | Shift consumption to low-price periods |
| T4 | PV + Battery | Dynamic | Arbitrage (charge low, discharge high) |
| T5 | Battery only | Dynamic | Arbitrage (cheap charge, expensive discharge) |
| T6 | Heat pump | §14a network charges | Shift to low-tariff periods |
| T7 | EV + Wallbox | Dynamic | Coordinate charging with price signals |
| T8 | EV + Wallbox + Heat pump + Battery | Mixed | Full optimization across all assets |
| T9 | Balcony solar (Balkonkraftwerk) | Self-consumption | Maximize generation; curtail if export limit exceeded |
| T10 | Balcony solar + Battery | Dynamic | Self-consumption + arbitrage |

### 2.2 Per-Type Economic Analysis

#### T1 — No PV, Fixed Tariff

| Aspect | Detail |
|--------|--------|
| Revenue streams | None |
| Cost basis | Fixed €/kWh for all consumption (e.g., 30 ct/kWh) |
| Baseline without system | Pay tariff rate for every kWh consumed |
| Coordination actions available | Shift consumption (via EMS: heat pump, standby loads) |
| Curtailment impact | No direct loss — shifted consumption costs the same per kWh |
| Shifting impact | Time-shifting doesn't change total bill under flat tariff |
| §14a relevance | None |
| Net effect | **Hard to harm this type financially** — flat tariff means time-indifferent pricing. Only absolute consumption increase would hurt, which coordination would not request. |

#### T2 — PV only (EEG, Fixed Feed-in Tariff)

| Aspect | Detail |
|--------|--------|
| Revenue streams | EEG feed-in tariff per kWh exported (guaranteed for 20 years, ~7-13 ct/kWh depending on installation year) |
| Cost basis | Fixed €/kWh for imported consumption |
| Baseline without system | Export all PV surplus at EEG rate; import shortfall at tariff rate |
| Coordination actions available | Curtail PV export (reduce feed-in) |
| Curtailment impact | **Direct revenue loss** — every kWh not exported loses the EEG payment |
| Shifting impact | Cannot shift PV generation; can shift consumption to align with PV production |
| §14a relevance | None |
| Net effect | **Easiest to harm.** Asking this household to curtail PV means immediate, measurable lost income. The household has limited flexibility: only consumption shifting and PV curtailment. |

#### T3 — PV only (Dynamic/EPEX Spot)

| Aspect | Detail |
|--------|--------|
| Revenue streams | EPEX Spot price for exported kWh (varies hourly, can be negative) |
| Cost basis | EPEX Spot price for imported kWh |
| Baseline without system | Export at spot price; import at spot price |
| Coordination actions available | Curtail PV export, shift consumption |
| Curtailment impact | Lost spot-price revenue — but spot prices can be negative at high solar yield (if price < 0, curtailment saves money actually) |
| Shifting impact | Can reduce import costs by shifting to low-price hours |
| §14a relevance | None |
| Net effect | More nuanced than T2. At times of negative prices, curtailment is beneficial. At positive prices, lost revenue. The household's own EMS already shifts loads to optimize spot exposure — coordination could interfere or help. |

#### T4 — PV + Battery, Dynamic

| Aspect | Detail |
|--------|--------|
| Revenue streams | Spot price arbitrage (charge battery at low price, discharge at high); PV export at spot |
| Cost basis | Spot price for imports |
| Baseline without system | EMS optimizes battery dispatch: charge at low-price hours, discharge at high-price hours, maximize self-consumption of PV |
| Coordination actions available | Battery charge/discharge shifting, PV curtailment, consumption shifting |
| Curtailment impact | Lost PV revenue; but battery can store excess instead of exporting |
| Shifting impact | Battery is the most flexible asset — can shift charging by hours without loss, if round-trip efficiency (typically 85-90%) is accounted for |
| §14a relevance | None |
| Net effect | Highly flexible but opportunity-cost-sensitive. The EMS's battery schedule is the baseline — any deviation may lose arbitrage profit. Coordination requests that shift battery dispatch must account for the round-trip efficiency loss and missed price spreads. |

#### T5 — Battery only, Dynamic

| Aspect | Detail |
|--------|--------|
| Revenue streams | Spot arbitrage only |
| Cost basis | Spot price for imports |
| Baseline without system | EMS arbitrage: charge at low price (e.g., 2 ct/kWh at 4 AM), discharge at high price (e.g., 25 ct/kWh at 8 PM) |
| Coordination actions available | Shift battery charge/discharge schedule |
| Curtailment impact | N/A (no generation) |
| Shifting impact | **Costly if schedule is disrupted** — the battery's entire value comes from timing. Being asked to charge at a high-price hour or discharge at a low-price hour directly loses money. |
| §14a relevance | None |
| Net effect | Maximum sensitivity to timing shifts. Baseline arbitrage profit is calculable; coordination-induced deviations are measurable as lost spread × kWh × round-trip loss. |

#### T6 — Heat Pump, §14a Network Charges

| Aspect | Detail |
|--------|--------|
| Revenue streams | None (heat pump is a consumer) |
| Cost basis | Reduced network charges (§14a, typically ~€100-200/year reduction) in exchange for accepting curtailment by grid operator |
| Baseline without system | §14a-controlled: grid operator may curtail heat pump to 4.2 kW during grid stress events (up to 3h, limited/year). Otherwise, heat pump runs on own schedule. |
| Coordination actions available | Pre-heat (shift heat pump run time), reduce heating power |
| Curtailment impact | §14a already allows curtailment. The system's coordination adds another layer — but the household already has reduced network charges as compensation. |
| Shifting impact | Pre-heating water/thermal mass can shift load by hours without comfort loss. The heat pump's thermal storage is a natural buffer. |
| §14a relevance | **This is the key type for §14a interaction.** The system's load shed signals may align with or conflict with the §14a curtailment schedule. |
| Net effect | Protected by regulatory bargain: reduced network charges are the compensation for accepting curtailment. But if the system adds curtailment beyond what §14a allows, that exceeds the compensation. Needs careful boundary. |

#### T7 — EV + Wallbox, Dynamic

| Aspect | Detail |
|--------|--------|
| Revenue streams | None |
| Cost basis | Spot price for charging; may use §14a reduced network charges if enrolled |
| Baseline without system | EMS schedules charging at cheapest hours (typically nighttime or PV surplus times) |
| Coordination actions available | Delay charging, reduce charging power, (in V2G case) discharge |
| Curtailment impact | Delayed charging still happens — no energy loss, just time shift |
| Shifting impact | Very flexible if EV is parked for hours. But if delayed past departure time, user experience suffers. Hard deadline matters. |
| §14a relevance | Wallbox may be §14a-capable |
| Net effect | High flexibility with low-to-zero financial cost if shifting stays within connection window. Risk is user experience (car not charged in time), not financial. |

#### T8 — EV + Wallbox + Heat Pump + Battery, Mixed

| Aspect | Detail |
|--------|--------|
| Revenue streams | Arbitrage (battery), PV export, §14a discounts |
| Cost basis | Spot prices, reduced network charges |
| Baseline without system | Complex multi-asset optimization by EMS (e.g., evcc, OpenEMS) considering PV, battery, heat pump, EV |
| Coordination actions available | All of the above — battery, PV, heat pump, EV |
| Curtailment impact | Depends on which asset is curtailed |
| Shifting impact | Most flexible type, but also highest opportunity cost risk due to interdependent optimization |
| §14a relevance | Multiple assets may be §14a-capable |
| Net effect | **Hardest to assess.** The EMS's multi-asset optimization creates interdependencies: asking the battery to charge at noon (for grid benefit) might conflict with storing PV surplus. The baseline is the EMS's global optimum — any deviation may cascade across assets. |

#### T9 — Balcony Solar Only

| Aspect | Detail |
|--------|--------|
| Revenue streams | Self-consumption of generated power (~280-600 kWh/year for a plug-in PV system) |
| Cost basis | Fixed tariff for imports |
| Baseline without system | Self-consume as much generated power as possible; no curtailment (typical balcony solar has no digital control) |
| Coordination actions available | **None** (most systems lack digital control interface) |
| Curtailment impact | Only if digital control is retrofitted — otherwise this type cannot be coordinated |
| Shifting impact | N/A |
| §14a relevance | None |
| Net effect | **By limitation, cannot be economically harmed by coordination** — the system cannot control balcony solar. Noted in Requirements.md as a known limitation. |

#### T10 — Balcony Solar + Battery, Dynamic

| Aspect | Detail |
|--------|--------|
| Revenue streams | Self-consumption + small-scale arbitrage |
| Cost basis | Spot price for imports |
| Baseline without system | Use generation for self-consumption; battery stores surplus or arbitrages |
| Coordination actions available | Limited — small battery, limited EMS capability |
| Curtailment impact | Same as T9 for PV; battery faces same arbitrage exposure as T5 but at smaller scale |
| Shifting impact | Small capacity limits impact |
| §14a relevance | None |
| Net effect | Financially similar to T5 but at much lower scale — opportunity costs are proportionally smaller. |

### 2.3 Key Insight: Incommensurable Baselines

Each type has a **different unit of financial impact**:
- T1: flat €/kWh (time-independent)
- T2: fixed €/kWh foregone (time-independent for each kWh)
- T3-T5, T7, T10: time-varying (spot price)
- T6: annual regulatory benefit (time-aggregated)
- T8: compound optimization (interdependent across assets)
- T9: immeasurable (no control interface)

There is no single metric that captures "fairness" across all types. Any fairness approach must either:
(a) Let each household self-assess its own cost (requires the system to accept self-reported values), or
(b) Define a proxy metric that works across types (may miss type-specific costs), or
(c) Rely on the system's inability to force action (if nothing is ever compelled, no household can be harmed).

---

## 3. System Constraints on the Solution

These are hard architectural constraints that any fairness mechanism must respect.

### 3.1 No Visibility into Household Economics

The system is a signaling/coordination layer (FR-03). It has:
- Smart meter values (grid import/export, in W and cumulative kWh)
- What each household offers as flexibility (kW, time window)
- Optional: §14a state from the household EMS

It does NOT have:
- The household's electricity tariff or pricing model
- The household's energy contract terms
- Battery SOC or state
- EV departure time or required range
- Heat pump storage temperature
- Household appliance schedules

Any fairness mechanism that requires the system to compute "financial impact" must either infer it (imprecise, privacy-invasive) or receive it from the household (self-reported).

### 3.2 No Balancing Accounting

Deliberately excluded (Requirements.md §1, Brainstorming §1). The system does not perform energy accounting, settlement, or billing. This means:
- No compensation payments between households
- No energy credit tracking
- No financial settlement layer

Any fairness mechanism must work without monetary transfer between participants.

### 3.3 Communication Bandwidth

LoRa 868 MHz (preferred transport) has:
- ~50 bytes per message per ~50 seconds per device
- 1% duty cycle (ETSI EN 300.220)
- At 100+ households: each agent ~1 message per 10 minutes

This constrains how much data per household can be exchanged: flex offers, status updates, and fairness metadata must fit within a few dozen bytes per message.

MQTT alternative removes the bandwidth constraint but adds recurring cost (~€3-4/month for VPS) and internet dependency.

### 3.4 Privacy (GDPR, MsbG)

- Data processing must be local where possible
- No per-household data may leave the household without explicit consent
- MsbG §§49-70 regulate smart meter data handling
- The system's outbound-only constraint already limits data exposure

A fairness mechanism that broadcasts per-household financial data would violate this. The mechanism must work with (a) local-only data, or (b) aggregate/anonymized data, or (c) self-reported data with household control.

### 3.5 Voluntary vs Mandatory Signals

From Brainstorming §1 signal table:

| Signal | Binding? |
|--------|----------|
| Grid Limit | ✅ Mandatory (hard ceiling) |
| Load Shed | ⚠️ Hard recommendation |
| §14a Signal | ✅ Yes (but outside the system) |
| Flex Offer | ❌ Voluntary |
| Flex Request | ❌ Voluntary |
| Tariff/Price | ❌ Informational |
| Health/Status | ❌ Informational |

Only Grid Limit and §14a (external) are mandatory. All Phase 2 coordination signals are voluntary or "hard recommendations." This means: **the system never forces a household to take a financially harmful action.** The EMS decides whether to respond to each signal.

This is the strongest built-in fairness guarantee — by design, every household can say no.

### 3.6 Phase 1 Individual Limits as Hard Ceiling

Each household has a configured individual limit (from grid connection contract). This limit is the absolute maximum import/export. Coordination in Phase 2 only operates within this headroom. This prevents any coordination scenario where a household is forced to accept more import/export than its infrastructure allows.

---

## 4. Approach Catalog

Each approach is described with: mechanism, how it would work in the system, pros, cons, and open questions. No recommendation is made — this is a collection for decision.

### A. Self-Selection (Voluntary-Only)

**Mechanism:** All Phase 2 coordination signals are non-binding. Each household's EMS evaluates each flex request against its own economic optimization and decides autonomously whether to respond. No tracking, no compensation, no central fairness logic.

**How it would work:**
- Coordinator broadcasts flex request: "Need 5 kW reduction for 1 hour"
- Each household's EMS computes: does responding benefit me?
  - Battery owner: "Yes, I can charge later at a cheaper price, and I'm being paid/receive priority" (if any incentive exists)
  - PV-EEG owner: "No, curtailing loses feed-in revenue"
  - EV owner: "Yes, I have 6 hours until departure"
- Only households that see net benefit respond
- No household is harmed because no household is compelled

**Pros:**
- Aligns perfectly with existing architecture (voluntary signals already designed)
- Zero additional system complexity
- No privacy issues (economics stays in the household)
- Works at any scale
- Compatible with LoRa bandwidth constraints (simple yes/no responses)

**Cons:**
- Always burdens the same households (those whose incentives naturally align: batteries, flexible EV owners)
- Never helps during grid emergencies (voluntary only, but emergencies override fairness anyway per priority hierarchy)
- No mechanism to encourage participation from households that rarely benefit
- May systematically favor certain household types, leading to long-term imbalance
- No transparency — households don't know if they're contributing fairly

**Open questions:**
- Is long-term imbalance between household types acceptable under FR-06 if every individual action is voluntary?
- How to handle the "always asks the same people" problem without tracking?
- What happens if no one volunteers and grid protection is needed?

---

### B. Flex Offer with Self-Assessed Minimum Price

**Mechanism:** Each household's agent attaches a minimum acceptable compensation (in €/kWh or €/kW/h) to its flex offers. The coordinator matches using merit order (cheapest first), but never accepts an offer below the household's self-declared minimum. No actual money changes hands — the price is a **ranking signal**.

**How it would work:**
- Household EMS computes: "I can shift 3 kW for 1 hour, minimum price 8 ct/kWh" (based on its own economics)
- Agent broadcasts the offer: `{flex_kw: 3, duration_h: 1, min_price: 8}`
- Coordinator collects all offers, sorts by min_price, accepts cheapest until demand is met
- Accepted households receive **priority access** (or some non-monetary benefit) rather than payment
- Rejected offers get feedback: "your price was above clearing price"

**Pros:**
- Self-assessment naturally captures type-specific economics without the system understanding them
- Merit order is economically efficient
- Long-term fairness emerges naturally — households that offer cheap get selected more, but they also set their own price
- Transparent — each household controls its own offer price
- Compatible with "no balancing accounting" — the price is just a ranking, not a payment

**Cons:**
- Requires a non-monetary incentive for participation (e.g., priority access, reputation)
- Strategic bidding: households may set prices above true cost to extract surplus
- No verification: the system cannot check if a self-assessed price is honest
- Adds data to each flex offer (a few extra bytes — manageable)
- Without actual compensation, the "price" is meaningless for households with no interest in future priority

**Open questions:**
- What non-monetary benefit makes the price meaningful? Priority access (approach F)? Rotating priority? Reputation?
- How to prevent or detect strategic bidding?
- Is a "price" signal meaningful without actual monetary settlement?

---

### C. Participation Tracking with Rotation

**Mechanism:** Each household's agent tracks its own flex contributions (kWh shifted, kW reduced, hours contributed). The coordinator periodically assigns a "fairness deficit" ranking and rotates requests to balance contributions over time.

**How it would work:**
- Agent maintains local counters: `{energy_shifted_kwh: number, requests_accepted: number, hours_contributed: number}`
- Periodically (e.g., weekly), agents share a lightweight fairness metric: `{fairness_score: number}` — a locally computed composite
- Coordinator uses the metric to prioritize agents that have contributed less
- Rotation cycles through eligible households

**Pros:**
- Explicit fairness mechanism — measurable and adjustable
- Transparent — each household can see its own contribution
- Long-term balance regardless of household type

**Cons:**
- Requires a comparable fairness metric across different types — hard to define (is 1 kWh shift from a battery equivalent to 1 kWh curtailment from PV?)
- Metric computation needs household-internal data — privacy-invasive if shared raw
- History storage burden (each agent stores its own history, per Brainstorming Q7)
- Coordinator needs to receive fairness metrics — adds communication overhead
- Hard to rotate fairly during emergencies (time-pressured, few eligible households)

**Open questions:**
- What fairness metric works across all 10 types? Hours contributed? kWh shifted? Economic impact?
- How to compute a comparable score without sharing sensitive data?
- Rotation interval: daily, weekly, monthly? What works for both sudden emergency and sustained coordination?
- How to handle opt-out — does the fairness score freeze, decay, or get penalized?

---

### D. Proportional Load Sharing

**Mechanism:** When curtailment or load shed is needed, each household contributes proportionally to its available flexibility headroom (its configured limit minus its current load). All households share the burden equally in relative terms.

**How it would work:**
- Each household's agent knows: `{individual_limit, current_load, headroom}`
- Coordinator broadcasts: "Neighborhood needs 20 kW reduction"
- Each agent computes: `my_share = headroom * (20 / sum_of_all_headrooms)`
- Agent sends flex offer or self-curtails for its share
- Proportional: a 5 kW limit household with 2 kW headroom contributes twice as much as a 3 kW limit household with 1 kW headroom

**Pros:**
- Simple, transparent, provably fair in proportional terms
- No baseline economics needed
- Works during emergencies (clear allocation rule)
- Compatible with LoRa broadcast + local computation

**Cons:**
- ignores different cost structures — proportional kW reduction is not proportional economic impact
- A battery owner may lose €0.10/kWh while a PV-EEG owner loses €0.13/kWh for the same reduction
- Households with small headroom contribute little regardless of their asset type
- Requires each household to share its headroom — minor privacy concern
- May ask a household to curtail when it's economically harmful (conflicts with voluntary principle)

**Open questions:**
- Does proportional fairness satisfy FR-06 if economic impact is not proportional?
- Should headroom be measured against individual limit or against nominal household load?
- How to handle households that have already contributed significantly in the recent past?

---

### E. Merit-Order with Long-Term Budget

**Mechanism:** Combine the economic efficiency of merit ordering with a long-term fairness budget. Each household has a renewable budget of "curtailment tokens" or a monetary-like credit. Offers are accepted in merit order, but debited from the provider's budget. When a household's budget is exhausted, it cannot be asked again until the budget resets.

**How it would work:**
- Period (e.g., month) starts: each household receives a budget (equal initial allocation)
- When flex is needed: coordinator collects offers with self-assessed minimum price
- Matches cheapest first, debits accepted households' budgets
- Households with depleted budgets are skipped for the remainder of the period
- Budgets reset each period
- Metric types: time-based (hours of contribution), energy-based (kWh shifted), or abstract (tokens)

**Pros:**
- Combines economic efficiency (merit order) with long-term fairness (budget cap)
- Prevents over-asking the same households
- Transparent and auditable
- Budget allocation can be equal per household (simplest) or weighted by contractual capacity

**Cons:**
- Needs a budget metric that works across types
- Requires coordinator to track budgets — communication overhead
- What happens when all budgets are exhausted but curtailment is still needed?
- During emergencies, budgets may be insufficient — but infrastructure safety > fairness
- Complex: two systems (merit order + budget tracking)

**Open questions:**
- Budget metric: equal tokens per household? Weighted by limit? By connected capacity?
- Reset period: day, week, month? Should align with §14a or grid operator constraints.
- What happens at budget zero during a real emergency? (Infrastructure safety overrides.)
- How to prevent last-day-of-cycle gaming?

---

### F. Opt-Out Normal, Priority Access for Contributors

**Mechanism:** Households that offer flexibility earn priority access for future flex requests. Non-participating households are passive: they receive meter reading, limit enforcement, and signals, but the coordinator never requests flexibility from them first.

**How it would work:**
- Two tiers of access:
  - **Active:** Households that have contributed flexibility in the past N days can submit flex requests with priority
  - **Passive:** Households that have not contributed still receive grid limit broadcasts and meter reading, but their flex requests are queued behind active households
- Incentive: "If you help the neighborhood when you can, the neighborhood helps you when you need it"
- The status is local per household and can change over time

**Pros:**
- Natural incentive alignment without monetary transfers
- Households self-select based on their own economics
- Passive participants are still counted fairly (they contribute to grid protection via Phase 1)
- No complex fairness metric needed

**Cons:**
- Creates two tiers — passive households may feel excluded
- A household that genuinely cannot offer flexibility (e.g., T2 PV-EEG limited by its EMS) is permanently passive
- Incentive is weak if the household rarely needs flexibility from others
- Needs coordinator tracking — which households are active

**Open questions:**
- What defines "active"? Minimum contribution threshold? Last contribution recency?
- How long does priority status last?
- Is it fair to permanently exclude households that cannot offer flexibility (T2, T9)?
- Could this create a social divide in the neighborhood?

---

### G. Narrow Interpretation (Algorithm Fairness Only)

**Mechanism:** FR-06 is interpreted as a constraint on the optimization *algorithm*, not on individual outcomes. If the matching algorithm is provably symmetric (treats all household types identically, uses no type-discriminatory criteria), the system satisfies FR-06 regardless of outcome. The algorithm must be fair by design.

**How it would work:**
- The coordinator uses a rotation or oldest-first matching algorithm that treats all households symmetrically
- No per-household financial data is accessed or needed
- "Financial loss" is not measured — the algorithm is fair if it cannot discriminate

**Pros:**
- Sidesteps the impossible measurement problem
- No privacy concerns
- Simple to implement and verify
- Aligns with "the system cannot know household economics"

**Cons:**
- A symmetric algorithm can still produce asymmetric outcomes — does FR-06 require outcome fairness or process fairness?
- May feel like a regulatory loophole
- Households that lose money might still complain — and rightly so
- Difficult to convince stakeholders without outcome verification

**Open questions:**
- Does FR-06's text imply outcome fairness or process fairness? ("result in financial loss" suggests outcome.)
- Would this interpretation withstand regulatory or community scrutiny?
- How to verify algorithm symmetry in practice? Independent audit?

---

### H. Emergency-Only Coordination + Self-Selection Normal

**Mechanism:** Phase 2 coordination is split into two regimes:
- **Normal operation (within grid limits):** Pure self-selection (Approach A). No fairness mechanism needed.
- **Grid emergency (limit reached):** Proportional load sharing (Approach D) applies. The priority hierarchy (infrastructure > fairness) applies.

**How it would work:**
- Normal: coordinator may broadcast flex requests, but households respond voluntarily
- Emergency: coordinator broadcasts load shed with proportional allocation. Infrastructure safety overrides economic fairness.

**Pros:**
- Simple — only one fairness model to implement (proportional for emergencies)
- Normal operation is zero-overhead
- Aligns with the existing architecture (priority hierarchy already established)
- Fairness concern is limited to rare emergency events

**Cons:**
- During rare but critical emergencies, proportional sharing still ignores different cost structures
- The line between "normal" and "emergency" must be defined — what threshold triggers emergency mode?
- Normal-mode self-selection may still create long-term imbalance (but without infrastructure risk, is imbalance acceptable?)

**Open questions:**
- Where is the threshold between normal and emergency? 90% of aggregate limit? 100%? Some dynamic value?
- Does self-selection during normal operation violate FR-06 if it creates long-term imbalance but harms nobody?
- How to transition between regimes smoothly?

---

### I. Hybrid: Self-Assessed Price + Rotation Budget

**Mechanism:** Combine approaches B and C. Each household sets its own minimum price (self-assessed). The coordinator tracks cumulative contribution in a fairness budget. Selection uses merit order first, then rotation to break ties, with budget constraints to prevent overuse.

**How it would work:**
- Households submit flex offers with `{kw, duration, min_price}`
- Coordinator maintains a fairness budget per household, tracking accepted contributions in kWh-weighted-by-price units
- Matching algorithm: sort by price, then by budget (lowest budget first)
- Accept until demand met; debit budgets
- If two offers have the same price, the one with lower cumulative budget is chosen
- Budgets decay or reset periodically

**Pros:**
- Combines the best of economic efficiency (price signal) and long-term fairness (budget)
- Transparent: households see the clearing price and their budget
- Self-assessment avoids the incommensurable-baseline problem
- Rotation breaks ties fairly

**Cons:**
- Most complex approach — needs coordinator logic and periodic recalculation
- Requires a budget metric that incorporates both energy and price (compound value)
- Communication overhead for budget synchronization
- Strategic bidding still possible; may be harder to detect

**Open questions:**
- Budget metric: kWh × price? Normalized by household limit? Something else?
- Budget decay rate vs reset period — both needed?
- How does this handle the 100+ agent case with LoRa bandwidth limits?

---

## 5. Legal & Regulatory Constraints

### 5.1 §14a EnWG (Grid-Serving Control)

- §14a allows grid operators to curtail controllable devices (heat pumps, EV wallboxes, battery storage) in exchange for reduced network charges
- The system is NOT in the §14a signal path (FR-07, Brainstorming §7.1)
- However, if the system issues load shed signals that *correlate with* §14a events, households may receive double curtailment
- FR-06 implication: A household with §14a devices has already traded reduced network charges for accepting curtailment. The system's load shed adds additional curtailment beyond the §14a bargain. This could exceed fair compensation unless the system respects §14a state.
- BNetzA requirement for registered interfaces and logging (Claude.md review note) may apply to any system influencing §14a-capable devices

### 5.2 EEG (Feed-In Tariffs)

- PV households with fixed EEG feed-in tariffs have a guaranteed payment for exported electricity
- Curtailing PV export reduces EEG-compensated feed-in — this is a direct financial loss
- Under EEG, there is no obligation to accept curtailment from a non-grid-operator entity
- The system must not cause loss of EEG revenue — this is the clearest case FR-06 protects

### 5.3 MsbG (Metering Law)

- §§49-70 regulate processing of smart meter data
- Per-household financial calculations (e.g., for fairness tracking) may constitute processing of meter data
- Local processing on the agent is preferred; transmitting financial metrics over the coordination channel may require consent
- The agent (household side) computing its own fair share is internal data processing; transmitting results may be data processing subject to MsbG

### 5.4 GDPR

- Any fairness mechanism that shares per-household economic or consumption data over the coordination channel must have a legal basis
- Self-assessed minimum prices (Approach B) may not be personal data; participation history (Approach C, E, I) might be
- Data minimization principle: the system should compute what it needs, transmit as little as possible
- Local-processing-only mechanisms (A, D, H) have the strongest GDPR alignment

### 5.5 Balancing Energy / Market Regulation

- Direct compensation between households for flexibility would likely be classified as energy trading or balancing energy, with regulatory implications (EnWG §3, StromNZV)
- This is the reason "no balancing accounting" is a deliberate architecture choice
- Any fairness mechanism that implies a *quid pro quo* of energy (e.g., "you curtail now, get priority later") should be reviewed for whether it constitutes energy trading
- Non-monetary, non-energy mechanisms (priority access, rotations) are safer from a regulatory perspective

### 5.6 Anti-Discrimination

- A fairness mechanism that systematically disadvantages certain household types could face community acceptance issues, even if technically legal
- Types T2 (PV-EEG) and T9 (balcony solar) are disproportionately vulnerable to being passively excluded — their economics rarely align with flexibility requests
- Any multi-tier system (Approach F) should include a clear justification and opt-in transparency

---

## 6. Comparison Matrix

| Criterion | A: Self-Selection | B: Min Price | C: Rotation | D: Proportional | E: Merit+Budget | F: Priority | G: Narrow | H: Emergency | I: Hybrid |
|-----------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Simplicity** | ★★★★★ | ★★★☆☆ | ★★☆☆☆ | ★★★★☆ | ★★☆☆☆ | ★★★☆☆ | ★★★★★ | ★★★★☆ | ★☆☆☆☆ |
| **LoRa-compatible** | ✅ yes | ✅ yes | ⚠️ moderate | ✅ yes | ⚠️ moderate | ✅ yes | ✅ yes | ✅ yes | ⚠️ moderate |
| **Privacy (GDPR)** | ★★★★★ | ★★★★☆ | ★★★☆☆ | ★★★★☆ | ★★★☆☆ | ★★★★☆ | ★★★★★ | ★★★★★ | ★★★☆☆ |
| **FR-06 verifiability** | ★★☆☆☆ | ★★★☆☆ | ★★★★☆ | ★★☆☆☆ | ★★★★☆ | ★★★☆☆ | ★☆☆☆☆ | ★★☆☆☆ | ★★★★☆ |
| **Incentive alignment** | ★★★☆☆ | ★★★★☆ | ★★★☆☆ | ★★☆☆☆ | ★★★★☆ | ★★★★★ | ★☆☆☆☆ | ★★★☆☆ | ★★★★☆ |
| **Emergency suitability** | ★☆☆☆☆ | ★★★☆☆ | ★★☆☆☆ | ★★★★★ | ★★★☆☆ | ★★☆☆☆ | ★★★☆☆ | ★★★★★ | ★★★☆☆ |
| **Works for T2 (PV-EEG)** | ✅ no | ⚠️ maybe | ✅ yes | ✅ yes | ✅ yes | ❌ no | ✅ yes | ✅ yes | ✅ yes |
| **Works for all 10 types** | ✅ yes | ✅ yes | ⚠️ partially | ✅ yes | ✅ yes | ❌ unless opt-in | ✅ yes | ✅ yes | ✅ yes |
| **No balancing-relevant accounting** | ✅ yes | ⚠️ borderline | ✅ yes | ✅ yes | ⚠️ borderline | ✅ yes | ✅ yes | ✅ yes | ⚠️ borderline |

Ratings: ★★★★★ excellent, ★★★★☆ good, ★★★☆☆ fair, ★★☆☆☆ poor, ★☆☆☆☆ inadequate

Key: "No balancing-relevant accounting" flags approaches that track contributions in a way that could be interpreted as energy accounting or settlement.

---

## 7. Cross-Cutting Themes

### 7.1 The Self-Selection Floor

All approaches except G (narrow) rely on some form of self-selection as a minimum guarantee: households can always opt out. This means the worst-case outcome for any household is the same as without the system. FR-06's "must not result in financial loss" is automatically satisfied if:
- All coordination signals are voluntary (A, F)
- There is a meaningful opt-out mechanism (B, C, E, H, I)
- Grid emergencies explicitly invoke the "infrastructure > fairness" overrides

Only during emergency mode (where infrastructure safety overrides fairness) can a household theoretically be compelled to act against its financial interest — and the priority hierarchy explicitly permits this.

### 7.2 Verifiability vs. The Incommensurable Baseline

The most fundamental tension: FR-06 demands outcome fairness, but the system cannot measure outcomes because it lacks access to household-internal prices and decisions.

Approaches that embrace this limitation (A, D, G, H) give up on direct verification.
Approaches that work around it (B, C, E, I) introduce complexity, privacy concerns, or regulatory risk.

The tradeoff is: **Can FR-06 be verified without access to household-internal data?** If not, the system needs a proxy or self-reporting mechanism.

### 7.3 Data Retention Dependence (Brainstorming Q7)

Tracking-based mechanisms (C, E, I) depend on data retention. Brainstorming Q7 (data retention) is still open:
- Without history: current-value-only approaches (A, B, D, F, G, H) are feasible
- With agent-local history: local tracking approaches (C, E, I variant) work per household
- With coordinator history: coordinator-based approaches (C, E, I) work but raise privacy concerns

Fairness mechanism choice informs but does not force the Q7 decision.

### 7.4 Phase Gating

All approaches work in Phase 1 (Phase 1 has no inter-household coordination, so no fairness issue exists). The choice determines Phase 2 architecture:
- Approaches A, D, G, H: additive to Phase 1, no protocol changes needed
- Approaches B, C, E, I: require new message types or extended existing messages
- Approach F: requires new protocol messages for priority status

---

## 8. Open Questions

These need resolution before a fairness approach can be selected:

**Q-F1:** Is FR-06 about **process fairness** (algorithm treats all households equally) or **outcome fairness** (no household experiences financial loss in practice)?

**Q-F2:** Who bears the burden of verification? The system (proving no harm) or the household (proving harm and opting out)?

**Q-F3:** Does voluntary participation (Approach A, H) inherently satisfy FR-06, or does the system have an obligation to actively prevent imbalance?

**Q-F4:** What is the threshold that triggers "infrastructure safety > economic fairness"? At what grid utilization level does the override activate?

**Q-F5:** Should fairness enforcement be **proactive** (system prevents unfair patterns) or **reactive** (households opt out when they detect unfairness)?

**Q-F6:** Can a non-monetary incentive work as a substitute for price? What form? Priority access? Reputation? Community recognition?

**Q-F7:** Do the approaches requiring tracking (C, E, I) conflict with the "no balancing accounting" architectural decision?

**Q-F8:** What is the minimum set of data a household must expose to the coordination layer for any fairness approach to work?

**Q-F9:** How do §14a events interact with fairness tracking? If a household is already curtailed by §14a, should the system's fairness accounting credit or exclude that period?

**Q-F10:** Should the fairness mechanism be the same for all neighborhood sizes (5 vs 100+ households), or should it scale?

---

## 9. References

| Source | Section | Relevance |
|--------|---------|-----------|
| Requirements.md | §2a | Priority hierarchy (infrastructure > fairness) |
| Requirements.md | §2b | 10 household types with pricing models |
| Requirements.md | §3 (FR-06) | Functional requirement text |
| Requirements.md | §3 (FR-07) | §14a compatibility constraints |
| Brainstorming.md | §1 (signal table) | Voluntary vs mandatory signals |
| Brainstorming.md | §5.1 | Phase 1: no coordinator, individual limits |
| Brainstorming.md | §6 (Phase 2) | Fairness validation design sketch |
| Brainstorming.md | §8 Q6 | Flex matching algorithm (open) |
| Brainstorming.md | §8 Q7 | Data retention (open) |
| Brainstorming.md | §10 rec. 6 | Simulation recommendation for fairness validation |
| AGENTS.md | Architecture invariants | Phase structure, no balancing accounting |
