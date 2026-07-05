# HA Setup — LOTSE Mesh Data Sharing

Every household runs its own Home Assistant + MQTT broker. Each Heltec V3 has the `mqtt` channel with downlink enabled. Each HA publishes its own meter data into the LoRa mesh using its own node's decimal number — no single point of failure, no extra hardware beyond the node and Tasmota sensor.

```
Household A: Tasmota → HA → MQTT → Heltec V3 → LoRa → Heltec V3 → MQTT → HA :Household B
```

**LoRa is the only inter-household link.** No shared MQTT broker, no shared WiFi between houses, no VPN, no bridge scripts.

## Prerequisites

- Heltec V3 flashed with stock Meshtastic and connected to your local MQTT broker ([mesh-setup.md](mesh-setup.md))
- MQTT broker running in your Home Assistant instance (Mosquitto add-on or standalone)
- Your node's decimal number and hex ID from the Meshtastic Web UI (**About** page)

## Installation

 ### Step 1 — Install Sender Blueprint

This blueprint publishes your meter data into the LoRa mesh. Each household needs exactly one automation from this blueprint.

1. **Settings → Automations → Blueprints → Import Blueprint**
2. Paste this URL and click **Import**:
   `https://raw.githubusercontent.com/FunCyRanger/LOTSE/refs/heads/main/sender-blueprint.yaml`
3. Click **Create Automation**, fill in the form:
   - **Node Number** — from the Meshtastic Web UI (About page). Required.
   - **LoRa Region** — `EU_868` by default. Change for your country.
   - **Grid Import Energy (gEI)** — pick your cumulative import energy sensor. **Required** (needed for Energy Dashboard).
   - **MQTT Channel** — `1` by default.
   - All other fields are optional — leave empty to exclude from the payload.
   - **Grid quality sensors** (gA1-3, gF, gPF, gQ1-3, gS1-3) appear if you have a 3-phase meter that reports them.
4. **Save**. Your node publishes measurement data every interval (default 5 min).

### Step 1b — Install Sender Config Blueprint (recommended)

This publishes your node's system configuration (battery capacity, solar specs) so neighbors see capacity-weighted SOC and solar utilization. Runs on HA startup, daily, and when triggered.

1. **Settings → Automations → Blueprints → Import Blueprint**
2. Paste this URL:
   `https://raw.githubusercontent.com/FunCyRanger/LOTSE/refs/heads/main/sender-config-blueprint.yaml`
3. Click **Create Automation**, fill in:
   - **Node Number** (same as sender blueprint)
   - **Battery Capacity / Solar Peak Power / Panel Angle / Panel Azimuth** — optional system specs
4. **Save**.

### Step 2 — Install LOTSE Mesh Coordinator Integration

This integration does everything on the receiving side: it subscribes to the MQTT mesh topic, creates per-node sensors for every neighbor, builds combined aggregation sensors (totals, averages, min/max), computes a solar forecast from your weather entity, and adds an optional dashboard. No YAML files needed.

1. **HACS → Custom Repositories** → add `https://github.com/FunCyRanger/LOTSE` with category **Integration**
2. **HACS → Integrations** → search **LOTSE Mesh Coordinator** → **Install**
3. **Restart** Home Assistant
4. **Settings → Devices & Services → Add Integration** → search **LOTSE Mesh Coordinator** → select your weather entity → **Submit**
5. (Optional) **Configure** → **Options** → add manual solar panels if you have panels not associated with a mesh node

### Step 3 — Configure Energy Dashboard

1. **Settings → Energy**
2. Edit your **Solar production** source:
   - **Solar Production** sensor → select `Solar Production with Forecast` (`sensor.solar_production_forecast`)
   - **Solar forecast** dropdown → select **LOTSE Mesh Coordinator**
3. Add **Grid consumption** → `Combined Mesh Grid Import` (`sensor.combined_mesh_gei`)
4. Add **Return to grid** → `Combined Mesh Grid Export` (`sensor.combined_mesh_geo`)
5. (Optional) **Configure** the integration → **Options** → add manual solar panels

## What you get

Per-node sensors appear automatically as neighbors send data:
```
sensor.node_2892010403_gp    sensor.node_2892010403_gip   sensor.node_2892010403_gep
sensor.node_2892010403_sp    sensor.node_2892010403_se    sensor.node_2892010403_bs
sensor.node_2892010403_bc    sensor.node_2892010403_sk    sensor.node_2892010403_sa
... (27 keys, ~20 per node)
```

Combined aggregation sensors (entity IDs unchanged from previous versions):
```
sensor.combined_mesh_gp      — total neighborhood grid power
sensor.combined_mesh_gei     — cumulative import energy (Energy Dashboard)
sensor.combined_mesh_geo     — cumulative export energy (Energy Dashboard)
sensor.combined_mesh_sp      — total solar power
sensor.combined_mesh_se      — cumulative solar energy (Energy Dashboard)
sensor.combined_mesh_bs      — average neighbor SOC
sensor.combined_mesh_soc_weighted — capacity-weighted SOC
sensor.combined_solar_utilization  — % of installed PV currently generated
sensor.solar_production_forecast   — Energy Dashboard bridge sensor
... (25 sensors total)
```

A **LOTSE Neighborhood** dashboard is auto-created in your HA sidebar showing all combined sensors on one page.

## If you're upgrading from v2.x

- Delete the old auto-discovery automation (**Settings → Automations** → `Mesh: Auto-discover neighbors`)
- Delete old YAML package files from your HA `packages/` directory (`mesh-combined-rest.yaml`, `mesh-combined-sensors.yaml`, `mesh-combined-template.yaml`)
- The integration auto-removes stale entities (`combined_solar_panel_angle`, `combined_solar_panel_azimuth`, `forecast_correction_factor`, `solar_roughness_index`) on first startup

## Data Format

JSON payload with keys grouped by category. Sign convention: import/charge = positive, export/discharge = negative.

### Measurement keys (sender blueprint)

| Key | Meaning | Unit | Priority |
|-----|---------|------|----------|
| gP | Net power (+import, -export) | kW | important |
| gIP | Import power only (always ≥0) | kW | recommended |
| gEP | Export power only (always ≥0) | kW | important |
| gP1–3 | Phase 1–3 power | kW | important |
| gV1–3 | Phase 1–3 voltage | V | optional |
| gEI | Cumulative energy import | kWh | **mandatory** |
| gEO | Cumulative energy export | kWh | important |
| gA1–3 | Phase 1–3 current | A | optional |
| gF | Grid frequency | Hz | optional |
| gPF | Power factor | % | optional |
| gQ | Total reactive power | VAr | optional |
| gQ1–3 | Phase 1–3 reactive power | VAr | optional |
| gS | Total apparent power | VA | optional |
| gS1–3 | Phase 1–3 apparent power | VA | optional |
| sP | Solar power | kW | important |
| sE | Solar cumulative energy | kWh | important |
| bS | Battery state of charge | % | optional |
| bP | Battery power | kW | optional |
| bEI | Battery energy in | kWh | optional |
| bEO | Battery energy out | kWh | optional |
| wP | Wallbox power | kW | optional |
| wE | Wallbox energy | kWh | optional |
| wS | Wallbox SOC | % | optional |

### Config keys (sender-config blueprint)

| Key | Meaning | Unit |
|-----|---------|------|
| bC | Battery capacity | kWh |
| sK | Solar peak power | kWp |
| sA | Panel tilt angle | ° |
| sZ | Panel azimuth | ° |

**Size:** ~208 bytes with all 20 measurement keys (fits). Adding 1 grid-quality key still fits (~219 B); adding more grid keys exceeds 220 B — choose the few that matter most for your neighborhood.

**Edge cases:**
- Sensors with state `unavailable`/`unknown`/`none`/`NaN` are omitted from the payload
- Power values clamped to ±500 kW (guards against sensor glitches)
- Energy values clamped to ≥0 (rejects negative cumulative energy)
- SOC clamped to 0–100%
- Unit mismatch detection: kWh sensor in a kW slot → key omitted

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|------|
| No neighbor sensors appear | First message not yet sent | Wait one send interval (5 min + random delay). Check MQTT topic `msh/+/2/json/mqtt/+` for incoming messages (Mosquitto add-on → Listen). |
| Forecast shows 0 kWh | Weather entity not configured or forecast unavailable | Check integration options have a weather entity selected. Verify the weather entity provides hourly forecasts. |
| Energy Dashboard gap | Send interval too long | In the sender blueprint, reduce **Send Interval** to 2 min. |
| Stale neighbor values | Node offline or LoRa range | Check neighbor's node is powered. Verify both nodes are within LoRa range (~1–2 km urban, more rural). |
