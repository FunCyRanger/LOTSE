# HA-Mesh Setup — Per-Household LoRa Data Sharing

**Architecture:** Every household runs its own Home Assistant + MQTT broker. Each Heltec V3 has the `mqtt` channel with downlink enabled. Each HA publishes its own meter data into the LoRa mesh using its own node's decimal number — no single point of failure, no extra hardware beyond the node and Tasmota sensor.

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

## 1. Node Configuration (Web UI — do this on EVERY node)

### MQTT Settings

| Field | Value |
|-------|-------|
| MQTT Enabled | ✅ Check |
| Address | Your local MQTT broker IP (e.g., `192.168.1.100`) |
| Port | `1883` |
| JSON Output Enabled | ✅ Check |
| Username/Password | If your broker requires auth |
| TLS | Uncheck (local network) |

### Channel Configuration

| Channel | Role | Uplink | Downlink |
|---------|------|--------|----------|
| Primary (LongFast) | Default LoRa | ✅ Leave checked (for mesh discovery) | ☐ Unchecked |
| `mqtt` (index 1) | All meter data | ✅ **Check this** | ✅ **Check this** |

### Creating the `mqtt` channel

Create a NEW channel with these settings:

| Setting | Value |
|---------|-------|
| Name | **`mqtt`** (exactly this, lowercase) |
| PSK | Default/random |
| Uplink Enabled | ✅ Check |
| Downlink Enabled | ✅ Check |

**Reboot the node** — channel changes don't take effect until reboot.

### Find Your Node Number

From Web UI → **About** page, note:

| Identifier | Example | Where used |
|------------|---------|------------|
| Decimal Node Number | `2892010904` | `from` field in send automation |
| Hex Node ID (with `!`) | `!acaad598` | Topic path (for receive) |
| Region string | `EU_868` | Part of MQTT topic |

---

## Quick Start: HA Setup in 5 Steps

After your Heltec V3 is configured (step 1 above), set up Home Assistant:

### Step 1 — Install Sender Blueprint

1. In HA: **Settings → Automations → Blueprints → Import Blueprint**
2. Paste this URL and click **Import**:
   `https://raw.githubusercontent.com/FunCyRanger/LOTSE/refs/heads/main/blueprints/ha/sender.yaml`
3. Click **Create Automation**, fill in the form:
   - **Node Number** — from the Web UI (required)
   - **LoRa Region** — pre-filled to EU_868, change for your country (required)
   - **Grid Import Power (gIP)** — pick your sensor (required)
   - **MQTT Channel** — pre-filled to 1 (required)
   - All other fields are optional — leave empty to exclude from the payload
4. Save — your node publishes on the next interval automatically

### Step 2 — Install Auto-Discovery

1. Find the auto-discovery automation template further down in this guide (section "Auto-Discovery via MQTT")
2. Copy it and replace `{YOUR_REGION}`, `{YOUR_NODE_HEX}`, and `{YOUR_NODE_DECIMAL}` with your values
3. In HA: **Settings → Automations → Create → Edit in YAML**, paste and save

Neighbor sensors appear automatically when the first message arrives. No need to add sensors manually.

### Step 3 — Install Combined Package

1. Copy `packages/mesh_combined.yaml` into your HA `config/packages/` directory
2. Restart Home Assistant

All aggregate sensors (combined grid power, solar, battery SOC, energy imports/exports) appear in HA.

### Step 4 — Configure Energy Dashboard

1. In HA: **Settings → Energy**
2. **Grid consumption** → search `combined import` → select `Combined Mesh Grid Import`
3. **Return to grid** → search `combined export` → select `Combined Mesh Grid Export`
4. **Solar production** → search `combined solar` → select `Combined Mesh Solar Energy`

### Step 5 — Verify

After the first send interval (default 5 minutes) elapses:
- Your neighbor's sensors appear under **Settings → Devices & Services → Devices**
- Combined sensors show summed values on the **Overview** dashboard
- The **Energy** dashboard shows your first recorded data point

New neighbors that join later are handled automatically — no additional setup needed.

---

## Data Format (Reference)

JSON payload with keys grouped by category. Sign convention: import/charge = positive, export/discharge = negative.

### Grid

| Key | Meaning | Unit | Priority |
|-----|---------|------|----------|
| gP | Net power (+import, -export) | kW | **mandatory** |
| gIP | Import power only (always ≥0) | kW | important |
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
| bS | State of charge | % | **mandatory** |
| bEI | Cumulative energy in | kWh | optional |
| bEO | Cumulative energy out | kWh | optional |

### Wallbox (EV charger)

| Key | Meaning | Unit | Priority |
|-----|---------|------|----------|
| wP | Power | kW | optional |
| wE | Cumulative energy | kWh | optional |
| wS | State of charge | % | optional |

**Example payload (all keys):**
```
{"gP":-1.2,"gIP":0.0,"gEP":1.2,"gP1":-0.4,"gP2":-0.4,"gP3":-0.4,"gV1":230,"gV2":229,"gV3":231,"gEI":12.5,"gEO":3.2,"sP":3.5,"sE":15.2,"bP":1.0,"bS":85,"bEI":8.5,"bEO":2.3,"wP":0.0,"wE":2.1,"wS":80}
```

**Size:** ~170 bytes with all keys — fits within Meshtastic's ~220-byte limit.

> **Energy Dashboard:** HA's energy dashboard requires cumulative energy sensors (kWh, `total_increasing`).
> Use `gEI` (grid import), `gEO` (grid export), and `sE` (solar) as the primary inputs.
> Power sensors can work via Riemann sum helper (unit: kW). Use `gIP` for consumption,
> `gEP` for production — no sign-splitting needed. Cumulative sensors are still more accurate.
> **Include cumulative sensors (`gEI`, `gEO`, `sE`) if your meter provides them.**

---

## Sender Automation (Reference)

Create one automation that triggers periodically and publishes your meter data to your node's downlink topic.

### 3.1 Install the Blueprint (recommended)

A pre-built automation blueprint is available at:
`https://raw.githubusercontent.com/FunCyRanger/LOTSE/refs/heads/main/blueprints/ha/sender.yaml`

Import it via **Settings → Automations → Blueprints → Import Blueprint** (paste the URL
or copy the file contents directly). It lets you select your sensors from a dropdown
instead of editing YAML by hand.

**Setup:**

1. In HA: **Settings → Automations → Blueprints → Import Blueprint**
2. Paste the URL or copy the file contents from
   `https://raw.githubusercontent.com/FunCyRanger/LOTSE/refs/heads/main/blueprints/ha/sender.yaml`
3. Click **Import**
4. Click **Create Automation** from the newly imported blueprint
5. Fill in the form:
   - **Node Number** — your decimal node number from Meshtastic Web UI
   - **LoRa Region** — pre-filled to EU_868, change for your country (required)
   - **Send Interval** — how often to publish (default 5 min)
   - **Grid Import Power (gIP)** — pick your grid import sensor (required)
   - **MQTT Channel** — pre-filled to 1 (required)
   - All other fields are optional — leave empty to exclude from the payload
6. Click **Save** — your node will start publishing on the next interval

The blueprint automatically handles the `from` field, channel index, and trailing slash.

### 3.2 Manual fallback

If you prefer to edit YAML directly, copy the template below and replace the placeholders.

**Replace these values** for your household in the template:
- `{YOUR_REGION}` — e.g., `EU_868`
- `{YOUR_NODE_DECIMAL}` — your node's decimal number (unquoted integer)
- `{INTERVAL}` — how often to send, e.g., `/5` (every 5 min) or `/1` (every 1 min)
- Entity IDs — replace with your HA sensor entities

> ⚠️ **Critical:** The topic must end with `/` — `msh/{YOUR_REGION}/2/json/mqtt/`. Omitting the trailing `/` will silently fail; the node will not receive the message.

### Template

```yaml
alias: "Meter Data → LoRa Mesh"
description: "Send meter readings as JSON into the LoRa mesh"
trigger:
  - platform: time_pattern
    minutes: "/{INTERVAL}"
    seconds: 0
condition: []
action:
  - service: mqtt.publish
    data:
      qos: 0
      retain: false
      topic: "msh/{YOUR_REGION}/2/json/mqtt/"
      payload: >
        {"from": {YOUR_NODE_DECIMAL}, "type": "sendtext",
         "payload": "{"
          "\"gP\":{{ states('sensor.grid_power')|float(0)|round(2) }},"
          "\"gIP\":{{ states('sensor.grid_import_power')|float(0)|round(2) }},"
          "\"gEP\":{{ states('sensor.grid_export_power')|float(0)|round(2) }},"
          "\"gP1\":{{ states('sensor.p1_power')|float(0)|round(2) }},"
         "\"gP2\":{{ states('sensor.p2_power')|float(0)|round(2) }},"
         "\"gP3\":{{ states('sensor.p3_power')|float(0)|round(2) }},"
         "\"gV1\":{{ states('sensor.p1_voltage')|float(0)|round(1) }},"
         "\"gV2\":{{ states('sensor.p2_voltage')|float(0)|round(1) }},"
         "\"gV3\":{{ states('sensor.p3_voltage')|float(0)|round(1) }},"
         "\"gEI\":{{ states('sensor.grid_energy_import')|float(0)|round(2) }},"
         "\"gEO\":{{ states('sensor.grid_energy_export')|float(0)|round(2) }},"
         "\"sP\":{{ states('sensor.solar_power')|float(0)|round(2) }},"
         "\"sE\":{{ states('sensor.solar_energy')|float(0)|round(2) }},"
         "\"bP\":{{ states('sensor.battery_power')|float(0)|round(2) }},"
         "\"bS\":{{ states('sensor.battery_soc')|int(0) }},"
         "\"bEI\":{{ states('sensor.battery_energy_in')|float(0)|round(2) }},"
         "\"bEO\":{{ states('sensor.battery_energy_out')|float(0)|round(2) }},"
         "\"wP\":{{ states('sensor.wallbox_power')|float(0)|round(2) }},"
         "\"wE\":{{ states('sensor.wallbox_energy')|float(0)|round(2) }},"
         "\"wS\":{{ states('sensor.wallbox_soc')|int(0) }}"
         "}",
         "channel": 1}
mode: single
```

**Delete lines** for sensors your household doesn't have (e.g., remove the five wallbox lines if you have no EV charger). Keep at minimum `gP` and `bS`; for energy dashboard support include `gEI`, `gEO`, `sE`, `gIP`, and `gEP` if available.

> **Channel index:** The template uses `"channel": 1` — this must match the `mqtt` channel's index in your Meshtastic channel list (the primary `LongFast` is 0, your first non-primary is 1). If you reorder channels, update this value.

**How it works:** Your node receives this MQTT message. It checks `from` — matches its own decimal number. It checks the channel is `"mqtt"` with downlink enabled. It injects the payload into the LoRa mesh. All other nodes receive it.

---

## Receiver Sensors (Reference)

### 4.1 Find Neighbors' Identifiers

From each neighbor's Meshtastic Web UI or from an observed MQTT message, collect:

| Identifier | Example |
|------------|---------|
| Hex Node ID | `!a1b2c3d4` |
| Decimal Node Number | `2712679380` |

### 4.2 Subscribe to Their Messages

All neighbor messages arrive on a single topic: your node's uplink topic. The `from` field distinguishes who sent each message.

**Replace:**
- `{YOUR_REGION}` — your region string (e.g., `EU_868`)
- `{YOUR_NODE_HEX}` — **your own** node's hex ID (e.g., `!acaad598`)
- `NEIGHBOR_A_DECIMAL` — neighbor's decimal number (unquoted integer)
- `{STATE_TOPIC}` — see note below

The state topic is `msh/{YOUR_REGION}/2/json/mqtt/!{YOUR_NODE_HEX}`.

Add to `configuration.yaml`. One block per field per neighbor. Below is the grid section as an example — repeat the same pattern for `gIP`, `gEP`, solar (`sP`, `sE`), battery (`bP`, `bS`, `bEI`, `bEO`), and wallbox (`wP`, `wE`, `wS`) keys (changing the key, unit, and device_class per §2). Or use the auto-discovery automation (§4.4) instead.

```yaml
mqtt:
  sensor:
    - name: "Neighbor A gP"
      unique_id: "neighbor_a_gp"
      state_topic: "{STATE_TOPIC}"
      value_template: >
        {% if value_json.from == NEIGHBOR_A_DECIMAL %}
          {{ (value_json.payload | from_json({})).gP | float(0) }}
        {% else %}
          {{ this.state }}
        {% endif %}
      unit_of_measurement: "kW"
      device_class: "power"
      state_class: "measurement"

    - name: "Neighbor A gP1"
      unique_id: "neighbor_a_gp1"
      state_topic: "{STATE_TOPIC}"
      value_template: >
        {% if value_json.from == NEIGHBOR_A_DECIMAL %}
          {{ (value_json.payload | from_json({})).gP1 | float(0) }}
        {% else %}
          {{ this.state }}
        {% endif %}
      unit_of_measurement: "kW"
      device_class: "power"
      state_class: "measurement"

    - name: "Neighbor A gP2"
      unique_id: "neighbor_a_gp2"
      state_topic: "{STATE_TOPIC}"
      value_template: >
        {% if value_json.from == NEIGHBOR_A_DECIMAL %}
          {{ (value_json.payload | from_json({})).gP2 | float(0) }}
        {% else %}
          {{ this.state }}
        {% endif %}
      unit_of_measurement: "kW"
      device_class: "power"
      state_class: "measurement"

    - name: "Neighbor A gP3"
      unique_id: "neighbor_a_gp3"
      state_topic: "{STATE_TOPIC}"
      value_template: >
        {% if value_json.from == NEIGHBOR_A_DECIMAL %}
          {{ (value_json.payload | from_json({})).gP3 | float(0) }}
        {% else %}
          {{ this.state }}
        {% endif %}
      unit_of_measurement: "kW"
      device_class: "power"
      state_class: "measurement"

    - name: "Neighbor A gV1"
      unique_id: "neighbor_a_gv1"
      state_topic: "{STATE_TOPIC}"
      value_template: >
        {% if value_json.from == NEIGHBOR_A_DECIMAL %}
          {{ (value_json.payload | from_json({})).gV1 | float(0) }}
        {% else %}
          {{ this.state }}
        {% endif %}
      unit_of_measurement: "V"
      device_class: "voltage"
      state_class: "measurement"

    - name: "Neighbor A gV2"
      unique_id: "neighbor_a_gv2"
      state_topic: "{STATE_TOPIC}"
      value_template: >
        {% if value_json.from == NEIGHBOR_A_DECIMAL %}
          {{ (value_json.payload | from_json({})).gV2 | float(0) }}
        {% else %}
          {{ this.state }}
        {% endif %}
      unit_of_measurement: "V"
      device_class: "voltage"
      state_class: "measurement"

    - name: "Neighbor A gV3"
      unique_id: "neighbor_a_gv3"
      state_topic: "{STATE_TOPIC}"
      value_template: >
        {% if value_json.from == NEIGHBOR_A_DECIMAL %}
          {{ (value_json.payload | from_json({})).gV3 | float(0) }}
        {% else %}
          {{ this.state }}
        {% endif %}
      unit_of_measurement: "V"
      device_class: "voltage"
      state_class: "measurement"

    - name: "Neighbor A gEI"
      unique_id: "neighbor_a_gei"
      state_topic: "{STATE_TOPIC}"
      value_template: >
        {% if value_json.from == NEIGHBOR_A_DECIMAL %}
          {{ (value_json.payload | from_json({})).gEI | float(0) }}
        {% else %}
          {{ this.state }}
        {% endif %}
      unit_of_measurement: "kWh"
      device_class: "energy"
      state_class: "total_increasing"

    - name: "Neighbor A gEO"
      unique_id: "neighbor_a_geo"
      state_topic: "{STATE_TOPIC}"
      value_template: >
        {% if value_json.from == NEIGHBOR_A_DECIMAL %}
          {{ (value_json.payload | from_json({})).gEO | float(0) }}
        {% else %}
          {{ this.state }}
        {% endif %}
      unit_of_measurement: "kWh"
      device_class: "energy"
      state_class: "total_increasing"
```

Repeat for solar (`sP`, `sE`), battery (`bP`, `bS`, `bEI`, `bEO`), and wallbox (`wP`, `wE`, `wS`) using the units and device classes from §2.

**Why `{YOUR_NODE_HEX}` in the topic?** Your node publishes received LoRa messages to `msh/{R}/2/json/mqtt/{YOUR_NODE_HEX}`. Every neighbor's messages arrive on this same topic. The `from` field distinguishes who sent each message.

### 4.3 Filter Out Your Own Messages

Your own node also publishes its received traffic — including your own messages echoed back. The `if value_json.from == NEIGHBOR_A_DECIMAL` check ensures you only create sensors for actual neighbors, not yourself. Add no sensor block for your own decimal number.

### 4.4 Optional: Auto-Discovery via MQTT

Create this automation to avoid manually adding sensor blocks per §4.2. It watches your uplink topic and uses MQTT discovery to auto-generate sensors for every new neighbor. Only fields present in the payload get a sensor — no useless 0-value entries.

**Add this automation in HA Settings → Automations → Create Automation → Edit in YAML:**

```yaml
alias: "Mesh: Auto-discover neighbors"
description: "Creates sensors via MQTT discovery for each new mesh node"
trigger:
  - platform: mqtt
    topic: "msh/{YOUR_REGION}/2/json/mqtt/!{YOUR_NODE_HEX}"
condition:
  - condition: template
    value_template: >
      {{ trigger.payload_json.from is defined
         and trigger.payload_json.payload is defined
         and trigger.payload_json.from | string != '{YOUR_NODE_DECIMAL}' }}
variables:
  from: "{{ trigger.payload_json.from }}"
action:
  # GRID

  - service: mqtt.publish
    data:
      qos: 0
      retain: true
      topic: "homeassistant/sensor/mesh_neighbor/{{ from }}-gp/config"
      payload: >
        {"name": "Node {{ from }} gP",
         "state_topic": "msh/{YOUR_REGION}/2/json/mqtt/!{YOUR_NODE_HEX}",
         "value_template": "{% raw %}{% if value_json.from == {% endraw %}{{ from }}{% raw %} %}{{ (value_json.payload | from_json({})).gP | float(0) }}{% endif %}{% endraw %}",
         "unit_of_measurement": "kW", "device_class": "power", "state_class": "measurement",
         "unique_id": "mesh_{{ from }}_gp",
         "device": {"identifiers": ["mesh_node_{{ from }}"], "name": "Node {{ from }}", "model": "Heltec V3", "manufacturer": "Meshtastic"}}

  - delay:
      seconds: 1

  - if:
      - condition: template
        value_template: "{{ (trigger.payload_json.payload | from_json({})).gP1 is defined }}"
    then:
      - service: mqtt.publish
        data:
          qos: 0
          retain: true
          topic: "homeassistant/sensor/mesh_neighbor/{{ from }}-gp1/config"
          payload: >
            {"name": "Node {{ from }} gP1",
             "state_topic": "msh/{YOUR_REGION}/2/json/mqtt/!{YOUR_NODE_HEX}",
             "value_template": "{% raw %}{% if value_json.from == {% endraw %}{{ from }}{% raw %} %}{{ (value_json.payload | from_json({})).gP1 | float(0) }}{% endif %}{% endraw %}",
             "unit_of_measurement": "kW", "device_class": "power", "state_class": "measurement",
             "unique_id": "mesh_{{ from }}_gp1",
             "device": {"identifiers": ["mesh_node_{{ from }}"], "name": "Node {{ from }}", "model": "Heltec V3", "manufacturer": "Meshtastic"}}

  - delay:
      seconds: 1

  - if:
      - condition: template
        value_template: "{{ (trigger.payload_json.payload | from_json({})).gP2 is defined }}"
    then:
      - service: mqtt.publish
        data:
          qos: 0
          retain: true
          topic: "homeassistant/sensor/mesh_neighbor/{{ from }}-gp2/config"
          payload: >
            {"name": "Node {{ from }} gP2",
             "state_topic": "msh/{YOUR_REGION}/2/json/mqtt/!{YOUR_NODE_HEX}",
             "value_template": "{% raw %}{% if value_json.from == {% endraw %}{{ from }}{% raw %} %}{{ (value_json.payload | from_json({})).gP2 | float(0) }}{% endif %}{% endraw %}",
             "unit_of_measurement": "kW", "device_class": "power", "state_class": "measurement",
             "unique_id": "mesh_{{ from }}_gp2",
             "device": {"identifiers": ["mesh_node_{{ from }}"], "name": "Node {{ from }}", "model": "Heltec V3", "manufacturer": "Meshtastic"}}

  - delay:
      seconds: 1

  - if:
      - condition: template
        value_template: "{{ (trigger.payload_json.payload | from_json({})).gP3 is defined }}"
    then:
      - service: mqtt.publish
        data:
          qos: 0
          retain: true
          topic: "homeassistant/sensor/mesh_neighbor/{{ from }}-gp3/config"
          payload: >
            {"name": "Node {{ from }} gP3",
             "state_topic": "msh/{YOUR_REGION}/2/json/mqtt/!{YOUR_NODE_HEX}",
             "value_template": "{% raw %}{% if value_json.from == {% endraw %}{{ from }}{% raw %} %}{{ (value_json.payload | from_json({})).gP3 | float(0) }}{% endif %}{% endraw %}",
             "unit_of_measurement": "kW", "device_class": "power", "state_class": "measurement",
             "unique_id": "mesh_{{ from }}_gp3",
             "device": {"identifiers": ["mesh_node_{{ from }}"], "name": "Node {{ from }}", "model": "Heltec V3", "manufacturer": "Meshtastic"}}

  - delay:
      seconds: 1

  - if:
      - condition: template
        value_template: "{{ (trigger.payload_json.payload | from_json({})).gV1 is defined }}"
    then:
      - service: mqtt.publish
        data:
          qos: 0
          retain: true
          topic: "homeassistant/sensor/mesh_neighbor/{{ from }}-gv1/config"
          payload: >
            {"name": "Node {{ from }} gV1",
             "state_topic": "msh/{YOUR_REGION}/2/json/mqtt/!{YOUR_NODE_HEX}",
             "value_template": "{% raw %}{% if value_json.from == {% endraw %}{{ from }}{% raw %} %}{{ (value_json.payload | from_json({})).gV1 | float(0) }}{% endif %}{% endraw %}",
             "unit_of_measurement": "V", "device_class": "voltage", "state_class": "measurement",
             "unique_id": "mesh_{{ from }}_gv1",
             "device": {"identifiers": ["mesh_node_{{ from }}"], "name": "Node {{ from }}", "model": "Heltec V3", "manufacturer": "Meshtastic"}}

  - delay:
      seconds: 1

  - if:
      - condition: template
        value_template: "{{ (trigger.payload_json.payload | from_json({})).gV2 is defined }}"
    then:
      - service: mqtt.publish
        data:
          qos: 0
          retain: true
          topic: "homeassistant/sensor/mesh_neighbor/{{ from }}-gv2/config"
          payload: >
            {"name": "Node {{ from }} gV2",
             "state_topic": "msh/{YOUR_REGION}/2/json/mqtt/!{YOUR_NODE_HEX}",
             "value_template": "{% raw %}{% if value_json.from == {% endraw %}{{ from }}{% raw %} %}{{ (value_json.payload | from_json({})).gV2 | float(0) }}{% endif %}{% endraw %}",
             "unit_of_measurement": "V", "device_class": "voltage", "state_class": "measurement",
             "unique_id": "mesh_{{ from }}_gv2",
             "device": {"identifiers": ["mesh_node_{{ from }}"], "name": "Node {{ from }}", "model": "Heltec V3", "manufacturer": "Meshtastic"}}

  - delay:
      seconds: 1

  - if:
      - condition: template
        value_template: "{{ (trigger.payload_json.payload | from_json({})).gV3 is defined }}"
    then:
      - service: mqtt.publish
        data:
          qos: 0
          retain: true
          topic: "homeassistant/sensor/mesh_neighbor/{{ from }}-gv3/config"
          payload: >
            {"name": "Node {{ from }} gV3",
             "state_topic": "msh/{YOUR_REGION}/2/json/mqtt/!{YOUR_NODE_HEX}",
             "value_template": "{% raw %}{% if value_json.from == {% endraw %}{{ from }}{% raw %} %}{{ (value_json.payload | from_json({})).gV3 | float(0) }}{% endif %}{% endraw %}",
             "unit_of_measurement": "V", "device_class": "voltage", "state_class": "measurement",
             "unique_id": "mesh_{{ from }}_gv3",
             "device": {"identifiers": ["mesh_node_{{ from }}"], "name": "Node {{ from }}", "model": "Heltec V3", "manufacturer": "Meshtastic"}}

  - delay:
      seconds: 1

  - if:
      - condition: template
        value_template: "{{ (trigger.payload_json.payload | from_json({})).gIP is defined }}"
    then:
      - service: mqtt.publish
        data:
          qos: 0
          retain: true
          topic: "homeassistant/sensor/mesh_neighbor/{{ from }}-gip/config"
          payload: >
            {"name": "Node {{ from }} gIP",
             "state_topic": "msh/{YOUR_REGION}/2/json/mqtt/!{YOUR_NODE_HEX}",
             "value_template": "{% raw %}{% if value_json.from == {% endraw %}{{ from }}{% raw %} %}{{ (value_json.payload | from_json({})).gIP | float(0) }}{% endif %}{% endraw %}",
             "unit_of_measurement": "kW", "device_class": "power", "state_class": "measurement",
             "unique_id": "mesh_{{ from }}_gip",
             "device": {"identifiers": ["mesh_node_{{ from }}"], "name": "Node {{ from }}", "model": "Heltec V3", "manufacturer": "Meshtastic"}}

  - delay:
      seconds: 1

  - if:
      - condition: template
        value_template: "{{ (trigger.payload_json.payload | from_json({})).gEP is defined }}"
    then:
      - service: mqtt.publish
        data:
          qos: 0
          retain: true
          topic: "homeassistant/sensor/mesh_neighbor/{{ from }}-gep/config"
          payload: >
            {"name": "Node {{ from }} gEP",
             "state_topic": "msh/{YOUR_REGION}/2/json/mqtt/!{YOUR_NODE_HEX}",
             "value_template": "{% raw %}{% if value_json.from == {% endraw %}{{ from }}{% raw %} %}{{ (value_json.payload | from_json({})).gEP | float(0) }}{% endif %}{% endraw %}",
             "unit_of_measurement": "kW", "device_class": "power", "state_class": "measurement",
             "unique_id": "mesh_{{ from }}_gep",
             "device": {"identifiers": ["mesh_node_{{ from }}"], "name": "Node {{ from }}", "model": "Heltec V3", "manufacturer": "Meshtastic"}}

  - delay:
      seconds: 1

  - if:
      - condition: template
        value_template: "{{ (trigger.payload_json.payload | from_json({})).gEI is defined }}"
    then:
      - service: mqtt.publish
        data:
          qos: 0
          retain: true
          topic: "homeassistant/sensor/mesh_neighbor/{{ from }}-gei/config"
          payload: >
            {"name": "Node {{ from }} gEI",
             "state_topic": "msh/{YOUR_REGION}/2/json/mqtt/!{YOUR_NODE_HEX}",
             "value_template": "{% raw %}{% if value_json.from == {% endraw %}{{ from }}{% raw %} %}{{ (value_json.payload | from_json({})).gEI | float(0) }}{% endif %}{% endraw %}",
             "unit_of_measurement": "kWh", "device_class": "energy", "state_class": "total_increasing",
             "unique_id": "mesh_{{ from }}_gei",
             "device": {"identifiers": ["mesh_node_{{ from }}"], "name": "Node {{ from }}", "model": "Heltec V3", "manufacturer": "Meshtastic"}}

  - delay:
      seconds: 1

  - if:
      - condition: template
        value_template: "{{ (trigger.payload_json.payload | from_json({})).gEO is defined }}"
    then:
      - service: mqtt.publish
        data:
          qos: 0
          retain: true
          topic: "homeassistant/sensor/mesh_neighbor/{{ from }}-geo/config"
          payload: >
            {"name": "Node {{ from }} gEO",
             "state_topic": "msh/{YOUR_REGION}/2/json/mqtt/!{YOUR_NODE_HEX}",
             "value_template": "{% raw %}{% if value_json.from == {% endraw %}{{ from }}{% raw %} %}{{ (value_json.payload | from_json({})).gEO | float(0) }}{% endif %}{% endraw %}",
             "unit_of_measurement": "kWh", "device_class": "energy", "state_class": "total_increasing",
             "unique_id": "mesh_{{ from }}_geo",
             "device": {"identifiers": ["mesh_node_{{ from }}"], "name": "Node {{ from }}", "model": "Heltec V3", "manufacturer": "Meshtastic"}}

  - delay:
      seconds: 1

  # SOLAR

  - if:
      - condition: template
        value_template: "{{ (trigger.payload_json.payload | from_json({})).sP is defined }}"
    then:
      - service: mqtt.publish
        data:
          qos: 0
          retain: true
          topic: "homeassistant/sensor/mesh_neighbor/{{ from }}-sp/config"
          payload: >
            {"name": "Node {{ from }} sP",
             "state_topic": "msh/{YOUR_REGION}/2/json/mqtt/!{YOUR_NODE_HEX}",
             "value_template": "{% raw %}{% if value_json.from == {% endraw %}{{ from }}{% raw %} %}{{ (value_json.payload | from_json({})).sP | float(0) }}{% endif %}{% endraw %}",
             "unit_of_measurement": "kW", "device_class": "power", "state_class": "measurement",
             "unique_id": "mesh_{{ from }}_sp",
             "device": {"identifiers": ["mesh_node_{{ from }}"], "name": "Node {{ from }}", "model": "Heltec V3", "manufacturer": "Meshtastic"}}

  - delay:
      seconds: 1

  - if:
      - condition: template
        value_template: "{{ (trigger.payload_json.payload | from_json({})).sE is defined }}"
    then:
      - service: mqtt.publish
        data:
          qos: 0
          retain: true
          topic: "homeassistant/sensor/mesh_neighbor/{{ from }}-se/config"
          payload: >
            {"name": "Node {{ from }} sE",
             "state_topic": "msh/{YOUR_REGION}/2/json/mqtt/!{YOUR_NODE_HEX}",
             "value_template": "{% raw %}{% if value_json.from == {% endraw %}{{ from }}{% raw %} %}{{ (value_json.payload | from_json({})).sE | float(0) }}{% endif %}{% endraw %}",
             "unit_of_measurement": "kWh", "device_class": "energy", "state_class": "total_increasing",
             "unique_id": "mesh_{{ from }}_se",
             "device": {"identifiers": ["mesh_node_{{ from }}"], "name": "Node {{ from }}", "model": "Heltec V3", "manufacturer": "Meshtastic"}}

  - delay:
      seconds: 1

  # BATTERY

  - service: mqtt.publish
    data:
      qos: 0
      retain: true
      topic: "homeassistant/sensor/mesh_neighbor/{{ from }}-bp/config"
      payload: >
        {"name": "Node {{ from }} bP",
         "state_topic": "msh/{YOUR_REGION}/2/json/mqtt/!{YOUR_NODE_HEX}",
         "value_template": "{% raw %}{% if value_json.from == {% endraw %}{{ from }}{% raw %} %}{{ (value_json.payload | from_json({})).bP | float(0) }}{% endif %}{% endraw %}",
         "unit_of_measurement": "kW", "device_class": "power", "state_class": "measurement",
         "unique_id": "mesh_{{ from }}_bp",
         "device": {"identifiers": ["mesh_node_{{ from }}"], "name": "Node {{ from }}", "model": "Heltec V3", "manufacturer": "Meshtastic"}}

  - delay:
      seconds: 1

  - service: mqtt.publish
    data:
      qos: 0
      retain: true
      topic: "homeassistant/sensor/mesh_neighbor/{{ from }}-bs/config"
      payload: >
        {"name": "Node {{ from }} bS",
         "state_topic": "msh/{YOUR_REGION}/2/json/mqtt/!{YOUR_NODE_HEX}",
         "value_template": "{% raw %}{% if value_json.from == {% endraw %}{{ from }}{% raw %} %}{{ (value_json.payload | from_json({})).bS | int(0) }}{% endif %}{% endraw %}",
         "unit_of_measurement": "%", "device_class": "battery", "state_class": "measurement",
         "unique_id": "mesh_{{ from }}_bs",
         "device": {"identifiers": ["mesh_node_{{ from }}"], "name": "Node {{ from }}", "model": "Heltec V3", "manufacturer": "Meshtastic"}}

  - delay:
      seconds: 1

  - if:
      - condition: template
        value_template: "{{ (trigger.payload_json.payload | from_json({})).bEI is defined }}"
    then:
      - service: mqtt.publish
        data:
          qos: 0
          retain: true
          topic: "homeassistant/sensor/mesh_neighbor/{{ from }}-bei/config"
          payload: >
            {"name": "Node {{ from }} bEI",
             "state_topic": "msh/{YOUR_REGION}/2/json/mqtt/!{YOUR_NODE_HEX}",
             "value_template": "{% raw %}{% if value_json.from == {% endraw %}{{ from }}{% raw %} %}{{ (value_json.payload | from_json({})).bEI | float(0) }}{% endif %}{% endraw %}",
             "unit_of_measurement": "kWh", "device_class": "energy", "state_class": "total_increasing",
             "unique_id": "mesh_{{ from }}_bei",
             "device": {"identifiers": ["mesh_node_{{ from }}"], "name": "Node {{ from }}", "model": "Heltec V3", "manufacturer": "Meshtastic"}}

  - delay:
      seconds: 1

  - if:
      - condition: template
        value_template: "{{ (trigger.payload_json.payload | from_json({})).bEO is defined }}"
    then:
      - service: mqtt.publish
        data:
          qos: 0
          retain: true
          topic: "homeassistant/sensor/mesh_neighbor/{{ from }}-beo/config"
          payload: >
            {"name": "Node {{ from }} bEO",
             "state_topic": "msh/{YOUR_REGION}/2/json/mqtt/!{YOUR_NODE_HEX}",
             "value_template": "{% raw %}{% if value_json.from == {% endraw %}{{ from }}{% raw %} %}{{ (value_json.payload | from_json({})).bEO | float(0) }}{% endif %}{% endraw %}",
             "unit_of_measurement": "kWh", "device_class": "energy", "state_class": "total_increasing",
             "unique_id": "mesh_{{ from }}_beo",
             "device": {"identifiers": ["mesh_node_{{ from }}"], "name": "Node {{ from }}", "model": "Heltec V3", "manufacturer": "Meshtastic"}}

  - delay:
      seconds: 1

  # WALLBOX

  - if:
      - condition: template
        value_template: "{{ (trigger.payload_json.payload | from_json({})).wP is defined }}"
    then:
      - service: mqtt.publish
        data:
          qos: 0
          retain: true
          topic: "homeassistant/sensor/mesh_neighbor/{{ from }}-wp/config"
          payload: >
            {"name": "Node {{ from }} wP",
             "state_topic": "msh/{YOUR_REGION}/2/json/mqtt/!{YOUR_NODE_HEX}",
             "value_template": "{% raw %}{% if value_json.from == {% endraw %}{{ from }}{% raw %} %}{{ (value_json.payload | from_json({})).wP | float(0) }}{% endif %}{% endraw %}",
             "unit_of_measurement": "kW", "device_class": "power", "state_class": "measurement",
             "unique_id": "mesh_{{ from }}_wp",
             "device": {"identifiers": ["mesh_node_{{ from }}"], "name": "Node {{ from }}", "model": "Heltec V3", "manufacturer": "Meshtastic"}}

  - delay:
      seconds: 1

  - if:
      - condition: template
        value_template: "{{ (trigger.payload_json.payload | from_json({})).wE is defined }}"
    then:
      - service: mqtt.publish
        data:
          qos: 0
          retain: true
          topic: "homeassistant/sensor/mesh_neighbor/{{ from }}-we/config"
          payload: >
            {"name": "Node {{ from }} wE",
             "state_topic": "msh/{YOUR_REGION}/2/json/mqtt/!{YOUR_NODE_HEX}",
             "value_template": "{% raw %}{% if value_json.from == {% endraw %}{{ from }}{% raw %} %}{{ (value_json.payload | from_json({})).wE | float(0) }}{% endif %}{% endraw %}",
             "unit_of_measurement": "kWh", "device_class": "energy", "state_class": "total_increasing",
             "unique_id": "mesh_{{ from }}_we",
             "device": {"identifiers": ["mesh_node_{{ from }}"], "name": "Node {{ from }}", "model": "Heltec V3", "manufacturer": "Meshtastic"}}

  - delay:
      seconds: 1

  - if:
      - condition: template
        value_template: "{{ (trigger.payload_json.payload | from_json({})).wS is defined }}"
    then:
      - service: mqtt.publish
        data:
          qos: 0
          retain: true
          topic: "homeassistant/sensor/mesh_neighbor/{{ from }}-ws/config"
          payload: >
            {"name": "Node {{ from }} wS",
             "state_topic": "msh/{YOUR_REGION}/2/json/mqtt/!{YOUR_NODE_HEX}",
             "value_template": "{% raw %}{% if value_json.from == {% endraw %}{{ from }}{% raw %} %}{{ (value_json.payload | from_json({})).wS | int(0) }}{% endif %}{% endraw %}",
             "unit_of_measurement": "%", "device_class": "battery", "state_class": "measurement",
             "unique_id": "mesh_{{ from }}_ws",
             "device": {"identifiers": ["mesh_node_{{ from }}"], "name": "Node {{ from }}", "model": "Heltec V3", "manufacturer": "Meshtastic"}}
mode: single
```

**Replace** the placeholders with your own values before importing:
- `{YOUR_REGION}` — e.g., `EU_868`
- `{YOUR_NODE_HEX}` — your receiving node's hex ID (e.g., `!a1b2c3d4` — the `!` is part of the id, **keep it**)
- `{YOUR_NODE_DECIMAL}` — your decimal node number (unquoted integer) to exclude your own messages

**How it works:**
1. Every message with `gP` in the payload triggers the automation
2. The condition skips your own messages (`from == YOUR_NUM`)
3. Publishes retained MQTT discovery configs for `gP`, `bP`, `bS` (always) plus any other fields present in the payload
4. HA auto-creates sensors, all grouped under one device per node
5. The 1-second delays between each publish prevent HA from creating separate device entries for each sensor
6. Sensors are permanent — retained configs survive HA and node restarts

**Result in HA:** Each neighbor appears as one device with only the sensors their household actually sends.

---

### 4.5 Combined Sensors

Add to `configuration.yaml` to aggregate all neighbors' readings into single sensors. New neighbors are included automatically.

> **Quick start:** A ready-to-use HA package with all combined sensors (power + energy) is at
> `packages/mesh_combined.yaml`. Drop it into `config/packages/` and restart HA — no replacements needed.

```yaml
template:
  - sensor:
      - name: "Combined Mesh Grid Power"
        unique_id: "combined_mesh_gp"
        unit_of_measurement: "kW"
        device_class: "power"
        state_class: "measurement"
        state: >
          {% set entities = expand(states.sensor)
             | selectattr('entity_id', 'search', 'node_\\d+_gp$') | list %}
          {{ entities | map(attribute='state') | map('float', 0) | sum | round(2) }}

      - name: "Combined Mesh Grid Import Power"
        unique_id: "combined_mesh_gip"
        unit_of_measurement: "kW"
        device_class: "power"
        state_class: "measurement"
        state: >
          {% set entities = expand(states.sensor)
             | selectattr('entity_id', 'search', 'node_\\d+_gip$') | list %}
          {{ entities | map(attribute='state') | map('float', 0) | sum | round(2) }}

      - name: "Combined Mesh Grid Export Power"
        unique_id: "combined_mesh_gep"
        unit_of_measurement: "kW"
        device_class: "power"
        state_class: "measurement"
        state: >
          {% set entities = expand(states.sensor)
             | selectattr('entity_id', 'search', 'node_\\d+_gep$') | list %}
          {{ entities | map(attribute='state') | map('float', 0) | sum | round(2) }}

      - name: "Combined Mesh Solar Power"
        unique_id: "combined_mesh_sp"
        unit_of_measurement: "kW"
        device_class: "power"
        state_class: "measurement"
        state: >
          {% set entities = expand(states.sensor)
             | selectattr('entity_id', 'search', 'node_\\d+_sp$') | list %}
          {{ entities | map(attribute='state') | map('float', 0) | sum | round(2) }}

      - name: "Average Neighbor SOC"
        unique_id: "avg_neighbor_soc"
        unit_of_measurement: "%"
        device_class: "battery"
        state_class: "measurement"
        state: >
          {% set entities = expand(states.sensor)
             | selectattr('entity_id', 'search', 'node_\\d+_bs$') | list %}
          {% set vals = entities | map(attribute='state') | map('int', 0) | list %}
          {{ (vals | sum / vals | length) | round(0) if vals | length > 0 else 0 }}
```

**How it works:** Regex `node_\d+_gp$` matches every auto-discovered grid power sensor (`sensor.node_2896876952_gp`). `map('float', 0)` handles `unknown`/`unavailable` without errors. SOC uses `| int` and averages instead of summing.

---

## 5. Adding More Households

| Step | What to do |
|------|-----------|
| New neighbor joins | Heltec V3 per §1, install the sender blueprint (§3.1) or use the manual template (§3.2) |
| Existing households see them | Auto-discovery (§4.4) creates sensors automatically from the first received message |
| No changes needed on the mesh | The new node is already on the shared LoRa channel; all existing nodes will receive its messages automatically |

---

## 6. Expected Message Flow

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
  (value_json.payload | from_json({})).gP → sensor value
```

---

## Energy Dashboard (Reference)

### 7.1 Which sensors to use

The energy dashboard works best with **cumulative energy sensors** (`total_increasing`, kWh):

| Dashboard section | Sensor from mesh | Aggregate (optional) |
|-------------------|-----------------|---------------------|
| Grid consumption | `gEI` per neighbor | `Combined Mesh Grid Import` |
| Grid return/production | `gEO` per neighbor | `Combined Mesh Grid Export` |
| Solar production | `sE` per neighbor | `Combined Mesh Solar Energy` |

Power sensors can be used via Riemann sum helpers (set unit to kW in the helper — default is W):
- Use `gIP` for grid consumption, `gEP` for grid return/production — no sign-splitting needed
- `sP` for solar production
Cumulative sensors are still more accurate — **prefer `gEI`, `gEO`, `sE` where available.**

### 7.2 Combined energy sensors (template)

> The `packages/mesh_combined.yaml` package includes these sensors plus all power aggregates —
> drop it into `config/packages/` instead of copying individual YAML blocks below.

Add to `configuration.yaml` to sum cumulative energy across all neighbors:

```yaml
template:
  - sensor:
      - name: "Combined Mesh Grid Import"
        unique_id: "combined_mesh_gei"
        unit_of_measurement: "kWh"
        device_class: "energy"
        state_class: "total_increasing"
        state: >
          {% set entities = expand(states.sensor)
             | selectattr('entity_id', 'search', 'node_\\d+_gei$') | list %}
          {{ entities | map(attribute='state') | map('float', 0) | sum | round(2) }}

      - name: "Combined Mesh Grid Export"
        unique_id: "combined_mesh_geo"
        unit_of_measurement: "kWh"
        device_class: "energy"
        state_class: "total_increasing"
        state: >
          {% set entities = expand(states.sensor)
             | selectattr('entity_id', 'search', 'node_\\d+_geo$') | list %}
          {{ entities | map(attribute='state') | map('float', 0) | sum | round(2) }}

      - name: "Combined Mesh Solar Energy"
        unique_id: "combined_mesh_se"
        unit_of_measurement: "kWh"
        device_class: "energy"
        state_class: "total_increasing"
        state: >
          {% set entities = expand(states.sensor)
             | selectattr('entity_id', 'search', 'node_\\d+_se$') | list %}
          {{ entities | map(attribute='state') | map('float', 0) | sum | round(2) }}
```

### 7.3 Sign convention reminder

The mesh uses **import/charge = positive, export/discharge = negative**. For the energy dashboard:
- `gEI` (cumulative import) and `gIP` (import power) are always ≥0 — use as-is for grid consumption
- `gEO` (cumulative export) and `gEP` (export power) are always ≥0 — use as-is for grid return/production
- `sE` (cumulative solar) is always ≥0 — use as-is for solar production
- No sign adjustment needed

### 7.4 Linking in the Energy Dashboard

All three combined sensors are available from `packages/mesh_combined.yaml`.

In HA Settings → Energy:
1. **Grid consumption** → `Combined Mesh Grid Import` (cumulative, preferred) or `Combined Mesh Grid Import Power` (Riemann sum)
2. **Return to grid** → `Combined Mesh Grid Export` (cumulative, preferred) or `Combined Mesh Grid Export Power` (Riemann sum)
3. **Solar production** → `Combined Mesh Solar Energy` (cumulative, preferred) or per-neighbor `sP` (Riemann sum)
4. **Battery** → `Combined Mesh Grid Import` as the grid sensor (battery in/out is already included in net grid energy)

