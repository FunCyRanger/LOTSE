# HA Setup — Per-Household LoRa Data Sharing

Every household runs its own Home Assistant + MQTT broker. Each Heltec V3 has the `mqtt` channel with downlink enabled. Each HA publishes its own meter data into the LoRa mesh using its own node's decimal number — no single point of failure, no extra hardware beyond the node and Tasmota sensor.

```
Household 1:                        Household 2:
Tasmota ──MQTT──► HA automation          Tasmota ──MQTT──► HA automation
                    │                                              │
                    ▼ msh/.../mqtt/ (from:node1)                   ▼ msh/.../mqtt/ (from:node2)
              Heltec V3 (mqtt ch+downlink)                    Heltec V3 (mqtt ch+downlink)
                    │                                              │
                    ▼ LoRa 868                                     ▼ LoRa 868
               all neighbors                                   all neighbors
```

**LoRa is the only inter-household link.** No shared MQTT broker, no shared WiFi between houses, no VPN, no bridge scripts.

---

## Prerequisites

- Heltec V3 flashed with stock Meshtastic and connected to your local MQTT broker ([mesh-setup.md](mesh-setup.md))
- MQTT broker running in your Home Assistant instance (Mosquitto add-on or standalone)
- Your node's decimal number and hex ID from the Meshtastic Web UI (**About** page)

---

## Quick Start

### Step 1 — Install Sender Blueprint

1. In HA: **Settings → Automations → Blueprints → Import Blueprint**
2. Paste this URL and click **Import**:
   `https://raw.githubusercontent.com/FunCyRanger/LOTSE/refs/heads/main/sender-blueprint.yaml`
3. Click **Create Automation**, fill in the form:
   - **Node Number** — from the Web UI (required)
   - **LoRa Region** — pre-filled to `EU_868`, change for your country (required)
   - **Grid Import Power (gIP)** — pick your sensor (required)
   - **MQTT Channel** — pre-filled to 1 (required)
   - All other fields are optional — leave empty to exclude from the payload
4. Save — your node publishes on the next interval automatically

### Step 2 — Install Auto-Discovery

1. Copy or download [`auto-discovery-automation.yaml`](auto-discovery-automation.yaml)
2. In HA: **Settings → Automations → Create Automation → Edit in YAML**, paste and save

No edits needed — the automation extracts the region from the MQTT topic dynamically. Neighbor sensors appear automatically when the first message arrives.

### Step 3 — Install Combined Package

1. Copy [`mesh-combined-sensors.yaml`](mesh-combined-sensors.yaml) into your HA `config/packages/` directory
2. Restart Home Assistant

All aggregate sensors (combined grid power, solar, battery SOC, energy) appear in HA.

### Step 4 — Configure Energy Dashboard

1. In HA: **Settings → Energy**
2. **Grid consumption** → select `Combined Mesh Grid Import`
3. **Return to grid** → select `Combined Mesh Grid Export`
4. **Solar production** → select `Combined Mesh Solar Energy`

### Step 5 — Verify

After the first send interval (default 5 minutes) elapses:
- Neighbor sensors appear under **Settings → Devices & Services → Devices**
- Combined sensors show summed values on the **Overview** dashboard
- The **Energy** dashboard shows your first recorded data point

New neighbors that join later are handled automatically — no additional setup needed.

---

## Data Format

JSON payload with keys grouped by category. Sign convention: import/charge = positive, export/discharge = negative.

### Grid

| Key | Meaning | Unit | Priority |
|-----|---------|------|----------|
| gP | Net power (+import, -export) | kW | important |
| gIP | Import power only (always ≥0) | kW | **required** |
| gEP | Export power only (always ≥0) | kW | important |
| gP1 | Phase 1 power | kW | important |
| gP2 | Phase 2 power | kW | important |
| gP3 | Phase 3 power | kW | important |
| gV1 | Phase 1 voltage | V | optional |
| gV2 | Phase 2 voltage | V | optional |
| gV3 | Phase 3 voltage | V | optional |
| gEI | Cumulative energy import | kWh | **important** |
| gEO | Cumulative energy export | kWh | **important** |

### Solar

| Key | Meaning | Unit | Priority |
|-----|---------|------|----------|
| sP | Power | kW | important |
| sE | Cumulative energy | kWh | important |

### Battery

| Key | Meaning | Unit | Priority |
|-----|---------|------|----------|
| bP | Power (+charge, -discharge) | kW | important |
| bS | State of charge | % | optional |
| bEI | Cumulative energy in | kWh | optional |
| bEO | Cumulative energy out | kWh | optional |

### Wallbox (EV charger)

| Key | Meaning | Unit | Priority |
|-----|---------|------|----------|
| wP | Power | kW | optional |
| wE | Cumulative energy | kWh | optional |
| wS | State of charge | % | optional |

**Minimal payload (grid-only, just the required field):**
```
{"gIP": 1.5}
```

**Example payload (all keys):**
```
{"gP":-1.2,"gIP":0.0,"gEP":1.2,"gP1":-0.4,"gP2":-0.4,"gP3":-0.4,"gV1":230,"gV2":229,"gV3":231,"gEI":12.5,"gEO":3.2,"sP":3.5,"sE":15.2,"bP":1.0,"bS":85,"bEI":8.5,"bEO":2.3,"wP":0.0,"wE":2.1,"wS":80}
```

**Size:** ~170 bytes with all keys, ~10 bytes with just `gIP` — both fit within Meshtastic's ~220-byte limit.

**Edge cases:**
- Sensors with state `unavailable`, `unknown`, `none`, `NaN`, `inf` are **omitted** from the payload (no key sent)
- Power values are **clamped** to ±500 kW — guards against sensor glitches or unit mismatches (e.g., kWh sensor wired to a kW slot)
- Energy values (`gEI`, `gEO`, `sE`, `bEI`, `bEO`, `wE`) are **clamped** at ≥ 0 — negative cumulative energy is rejected
- Battery/Wallbox SOC is **clamped** to 0–100%
- **Unit mismatch detection**: If a sensor's `unit_of_measurement` belongs to the wrong category (e.g., `kWh` in a power slot, `kW` in an energy slot), the key is omitted. If no unit is set, the value passes through as-is

---

## Energy Dashboard

### Which sensors to use

| Dashboard slot | Best sensor |
|---------------|-------------|
| Grid consumption | `Combined Mesh Grid Import` (cumulative `gEI`) |
| Return to grid | `Combined Mesh Grid Export` (cumulative `gEO`) |
| Solar production | `Combined Mesh Solar Energy` (cumulative `sE`) |

### Sign convention reminder

The mesh uses **import/charge = positive, export/discharge = negative**:
- `gEI` (cumulative import) and `gIP` (import power) are always ≥0 — use as-is
- `gEO` (cumulative export) and `gEP` (export power) are always ≥0 — use as-is
- `sE` (cumulative solar) is always ≥0 — use as-is
- No sign adjustment needed

### Linking in the Energy Dashboard

All three combined sensors are available from [`mesh-combined-sensors.yaml`](mesh-combined-sensors.yaml).

In HA Settings → Energy:
1. **Grid consumption** → `Combined Mesh Grid Import` (cumulative, preferred) or `Combined Mesh Grid Import Power` (Riemann sum)
2. **Return to grid** → `Combined Mesh Grid Export` (cumulative, preferred) or `Combined Mesh Grid Export Power` (Riemann sum)
3. **Solar production** → `Combined Mesh Solar Energy` (cumulative, preferred) or per-neighbor `sP` (Riemann sum)
4. **Battery** → `Combined Mesh Grid Import` as the grid sensor (battery in/out is already included in net grid energy)

---

## Expected Message Flow

### Send direction

```
HA publishes to:        msh/EU_868/2/json/mqtt/
Payload (JSON):
  {"from": 2892010904, "type": "sendtext",
   "payload": "{\"gP\":-1.2,\"gP1\":-0.4,\"gP2\":-0.4,\"gP3\":-0.4,\"bS\":85,\"sP\":3.5}",
   "channel": 1}

Your node receives MQTT:
  ✅ "from" == 2892010904 (matches own number)
  ✅ channel is "mqtt" with downlink
  ✅ injects into LoRa mesh on mqtt channel
```

### Receive direction

```
LoRa message arrives at your node:
  from: 2712679380 (neighbor's decimal)
  payload: {"gP": -1.2, "gP1": -0.4, "gP2": -0.4, "gP3": -0.4, "bS": 85, "sP": 3.5}

Your node publishes to MQTT:
  Topic: msh/EU_868/2/json/mqtt/!your_node_hex
  Payload: {"from": 2712679380, "type": "text",
            "payload": {"gP": -1.2, "gP1": -0.4, "gP2": -0.4, "gP3": -0.4, "bS": 85, "sP": 3.5},
            "channel": 1, ...}

Your HA receives it, checks from == NEIGHBOR_DECIMAL,
  value_json.payload.gP → sensor value
```

---

## Adding More Households

| Step | What to do |
|------|-----------|
| New neighbor joins | Configure their Heltec V3 per [mesh-setup.md](mesh-setup.md) and install the sender blueprint |
| Existing households see them | Auto-discovery creates sensors automatically from the first received message |
| No changes needed on the mesh | The new node is already on the shared LoRa channel; all existing nodes will receive its messages automatically |

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|------|
| Blueprint import fails with "invalid config" | Node number or sensor fields have wrong types | Ensure Node Number is a plain decimal (no quotes). Check sensor entities exist and are numeric. |
| Sensors don't appear after first message | Auto-discovery not running | Verify `auto-discovery-automation.yaml` is saved and enabled in HA → Automations. Check MQTT topic `msh/{region}/2/json/mqtt/!{your_hex}` for incoming messages (Mosquitto add-on → Listen). |
| Combined sensors show 0 or "unavailable" | Package file not loaded | Confirm `mesh-combined-sensors.yaml` is in `config/packages/` and `packages:` is uncommented in `configuration.yaml` (or use `!include_dir_merge_named packages`). Restart HA. |
| Energy dashboard shows gaps | Send interval too long | In the sender blueprint, adjust "Send interval" (default 5 min) to 2 min. Note this increases LoRa channel usage. |
| Neighbor values are stale | Node went offline or LoRa range issue | Check neighbor's node is still powered. Increase send interval. Verify both nodes are within LoRa range (~1-2 km urban, more rural). |
