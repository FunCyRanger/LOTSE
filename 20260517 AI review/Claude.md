I have read all four project files in full. Here is my structured review:

---

## LEM2 – Project Review: Feasibility & Errors

### Overall Assessment

The project is a **very well thought-out, pure planning project** (no code present). The documentation is exceptionally thorough for an early phase. The core idea — decentralized energy management at the neighborhood level via ESP32 + LoRa + smart meter reading — is technically feasible in principle. However, there are several concrete errors and open risks.

---

### What is Good (Strengths)

**Concept & Architecture:** The two-phase approach (Phase 1: local + without coordinator; Phase 2: flexibility trading) is pragmatic and robust. Each agent operates independently — grid protection remains intact even if coordination fails.

**Regulatory:** §14a EnWG, MsbG, GDPR, CE/RED compliance, and ETSI EN 300.220 are all correctly addressed. This is unusually good for an early-stage project.

**Hardware Choice:** LilyGO T3 S3 + WattWächter TTL is a sensible, solder-free combination. The evaluation matrix of alternatives is comprehensible.

**Cost Framework:** The targets (€48–55 per household for the prototype) are realistic and well-documented.

---

### Concrete Errors

**1. Wrong OBIS code `36.7.0`**
In `prototype-build.md` §P2.1, `36.7.0` is listed as "Current power (Wirkleistung Lieferung)". This code is not IEC 62056-21 standard. The correct OBIS for active power feed-in is **`-1:16.7.0`** (negative, for bidirectional meters) or manufacturer-specific. Some meters use `2.8.0` only for cumulative feed-in, not instantaneous power. This can cause silent parsing errors.

**2. SML library: wrong PlatformIO identifier**
`pio pkg install --library "m-/SML"` is not a valid PlatformIO registry name. The established library is `mzi_/sml` in the PlatformIO registry, or one installs it directly via Git URL. As specified, the install command fails.

**3. Baud rate problem with Holley DTZ541 not addressed**
The test matrix lists Holley DTZ541 at 115200 baud, but the entire circuit diagram and firmware documentation are designed for 9600 baud. There is no auto-baud-rate detection. A user with a Holley meter gets garbage output and does not know why.

**4. tinytronics.nl is not a German distributor**
In the BOM, `tinytronics.nl` is listed as a "German source". This is a Dutch shop. Although within the EU, it is misleading for the CE/RED requirement "available through German distributors".

**5. Phase inconsistency in the Prototype Build (P3–P5)**
Steps P3 (test receiver), P4 (range test), and P5 (latency measurement) test inter-household LoRa communication with GridLimit broadcasts — but according to the requirements (Brainstorming §5.1, Q2 and Q4), there is **no inter-household communication in Phase 1**. The grid limit is configured locally. The Prototype Build thus tests Phase 2 infrastructure and calls it Phase 1 validation. This creates unnecessary complexity and confusion in the prototype.

**6. Missing `platformio.ini`**
The build guide shows comments about what should go in `platformio.ini`, but does not provide an actual file. For a developer wanting to get started, this critical entry point is missing.

---

### Open Risks & Gaps

**LoRa duty cycle with multiple households:** With 10 households each sending a reading every 5 seconds (as assumed in the latency budget), the 1% duty cycle limit is quickly approached. A TDMA or CSMA/CA strategy for Phase 2 is missing. Phase 1 is unaffected (no radio needed), but this needs to be clearly documented.

**PIN procurement takes longer than stated:** The document says "2–4 weeks". In practice, requesting the PIN from the meter operator (Messstellenbetreiber) often takes 4–12 weeks, and some operators (especially for old Ferraris meters not yet converted) simply reject the request. This is a real blocker for FR-02 (instantaneous power).

**Balcony solar curtailment hardly feasible:** Balcony solar systems are listed in the household type catalog with "curtail if grid export limit exceeded". The vast majority of modern balcony solar systems, however, have no digital control interface. In practice (without hardware modification), this is not implementable and should be explicitly noted as a known limitation.

**§14a implementation is more complex than depicted:** The §14a signal path is treated as simple forwarding. However, the BNetzA ruling requires a registered interface, logging obligations, and possibly certification. This is significantly more than an MQTT topic.

**Economic fairness check (FR-06) without algorithm:** The requirement that no household be worse off than without LEM is well-intentioned — but there is neither a data structure nor a calculation method for it. This needs to be defined before Phase 2 implementation.

**Missing README.md:** The GitHub main page of the repo is empty. A visitor sees no description, no entry document. AGENTS.md fills this role but is not linked as a README.

---

### Priorities for Next Steps

Critical (fix before implementation):
- Correct OBIS code `36.7.0`
- Fix SML library identifier
- Add `platformio.ini` for T3 S3 as an actual file
- Cleanly separate Phase 1 vs. Phase 2 in the Prototype Build

Recommended:
- Add README.md
- Explicitly address Holley DTZ541 baud rate (configurable `METER_BAUD`)
- Document balcony solar curtailment limitation
- Estimate PIN wait time more realistically (up to 12 weeks)

---

**Conclusion:** The project is very solid for a concept phase. The concept is feasible, the most important design decisions are well-founded. With the corrections mentioned — especially the OBIS error, the library identifier, and the phase separation in the Prototype Build — it is ready for the first practical implementation.
