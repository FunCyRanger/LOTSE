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

Choose one of two approaches:

**Option 1: mqtt channel for everything (recommended)**

| Channel | Role | Uplink | Downlink |
|---------|------|--------|----------|
| Primary (LongFast) | Default LoRa | ✅ Leave checked (for mesh discovery) | ☐ Unchecked |
| `mqtt` (index 1) | All meter data | ✅ **Check this** | ✅ **Check this** |

With this setup, your node receives MQTT downlink on the `mqtt` channel and publishes received LoRa meter data to MQTT on the same channel.

**Option 2: primary channel for receive (legacy)**

| Channel | Role | Uplink | Downlink |
|---------|------|--------|----------|
| Primary (LongFast) | Receive LoRa → MQTT | ✅ Check | ☐ Unchecked |
| `mqtt` (index 1) | MQTT → LoRa send | ☐ Unchecked | ✅ Check |

### Creating the `mqtt` channel

Create a NEW channel with these settings:

| Setting | Value |
|---------|-------|
| Name | **`mqtt`** (exactly this, lowercase) |
| PSK | Default/random |
| Uplink Enabled | See table above |
| Downlink Enabled | See table above |

**Reboot the node** — channel changes don't take effect until reboot.

### Find Your Node Number

From Web UI → **About** page, note:

| Identifier | Example | Where used |
|------------|---------|------------|
| Decimal Node Number | `2892010904` | `from` field in send automation |
| Hex Node ID (with `!`) | `!acaad598` | Topic path (for receive) |
| Region string | `EU_868` | Part of MQTT topic |

---

## 2. Data Format

JSON payload with three fields:

| Field | Meaning | Type | Unit |
|-------|---------|------|------|
| IMP | Current import power from grid | float | kW |
| EXP | Export power to grid | float | kW |
| SOC | Battery state of charge | int | % |

**Example payload:** `{"IMP":0.3,"EXP":0.0,"SOC":85}`

**Size:** ~35-50 bytes — well within Meshtastic's ~220-byte limit.

---

## 3. Home Assistant: Sender Automation (per household)

Create one automation that triggers periodically and publishes your meter data to your node's downlink topic.

**Replace these values** for your household in the template:
- `{YOUR_REGION}` — e.g., `EU_868`
- `{YOUR_NODE_DECIMAL}` — your node's decimal number (unquoted integer)
- `{INTERVAL}` — how often to send, e.g., `/5` (every 5 min) or `/1` (every 1 min)
- Entity IDs — replace with your HA sensor entities

> ⚠️ **Critical:** The topic must end with `/` — `msh/{YOUR_REGION}/2/json/mqtt/`. Omitting the trailing `/` will silently fail; the node will not receive the message.

### JSON format (recommended)

```yaml
alias: "Meter Data → LoRa Mesh (JSON)"
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
         "payload": "{\"IMP\":{{ states('sensor.your_imp_sensor')|float(0)|round(2) }},\"EXP\":{{ states('sensor.your_exp_sensor')|float(0)|round(2) }},\"SOC\":{{ states('sensor.your_soc_sensor')|int(0) }}",
         "channel": 1}
mode: single
```

Fields: `IMP` (current import power, kW), `EXP` (export power, kW), `SOC` (battery state of charge, %). Omit any field you don't have.

**How it works:** Your node receives this MQTT message. It checks `from` — matches its own decimal number. It checks the channel is `"mqtt"` with downlink enabled. It injects the payload into the LoRa mesh. All other nodes receive it.

---

## 4. Home Assistant: Receiver Sensors (per neighbor)

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

#### State topic depends on your uplink channel

| If you use... | State topic is... |
|---------------|-------------------|
| mqtt channel (recommended) | `msh/{YOUR_REGION}/2/json/mqtt/!{YOUR_NODE_HEX}` |
| primary (LongFast) channel | `msh/{YOUR_REGION}/2/json/LongFast/!{YOUR_NODE_HEX}` |

#### JSON payload (recommended)

Add to `configuration.yaml`. One block per field per neighbor.

```yaml
mqtt:
  sensor:
    - name: "Neighbor A IMP"
      unique_id: "neighbor_a_imp"
      state_topic: "{STATE_TOPIC}"
      value_template: >
        {% if value_json.from == NEIGHBOR_A_DECIMAL %}
          {{ value_json.payload.IMP | float(0) }}
        {% else %}
          {{ this.state }}
        {% endif %}
      unit_of_measurement: "kW"
      device_class: "power"
      state_class: "measurement"

    - name: "Neighbor A EXP"
      unique_id: "neighbor_a_exp"
      state_topic: "{STATE_TOPIC}"
      value_template: >
        {% if value_json.from == NEIGHBOR_A_DECIMAL %}
          {{ value_json.payload.EXP | float(0) }}
        {% else %}
          {{ this.state }}
        {% endif %}
      unit_of_measurement: "kW"
      device_class: "power"
      state_class: "measurement"

    - name: "Neighbor A SOC"
      unique_id: "neighbor_a_soc"
      state_topic: "{STATE_TOPIC}"
      value_template: >
        {% if value_json.from == NEIGHBOR_A_DECIMAL %}
          {{ value_json.payload.SOC | int(0) }}
        {% else %}
          {{ this.state }}
        {% endif %}
      unit_of_measurement: "%"
      device_class: "battery"
      state_class: "measurement"
```

**Why `{YOUR_NODE_HEX}` in the topic?** Your node publishes received LoRa messages to `msh/{R}/2/json/mqtt/{YOUR_NODE_HEX}` (or `LongFast/` if using the primary channel). Every neighbor's messages arrive on this same topic. The `from` field distinguishes who sent each message.

### 4.3 Filter Out Your Own Messages

Your own node also publishes its received traffic — including your own messages echoed back. The `if value_json.from == NEIGHBOR_A_DECIMAL` check ensures you only create sensors for actual neighbors, not yourself. Add no sensor block for your own decimal number.

### 4.4 Optional: Auto-Discovery via MQTT (JSON payload)

If you use the JSON payload format (`IMP`, `EXP`, `SOC`) and want to avoid manually adding sensor blocks for each new neighbor, create this automation. It watches your uplink topic and uses MQTT discovery to auto-generate sensors for every new `from` it sees.

**Add this automation in HA Settings → Automations → Create Automation → Edit in YAML:**

```yaml
alias: "Mesh: Auto-discover neighbors"
description: "Creates IMP/EXP/SOC sensors via MQTT discovery for each new mesh node"
trigger:
  - platform: mqtt
    topic: "msh/{YOUR_REGION}/2/json/mqtt/!{YOUR_NODE_HEX}"
condition:
  - condition: template
    value_template: >
      {{ trigger.payload_json.from is defined
         and trigger.payload_json.payload.IMP is defined
         and trigger.payload_json.from | string != '{YOUR_NODE_DECIMAL}' }}
variables:
  from: "{{ trigger.payload_json.from }}"
action:
  - service: mqtt.publish
    data:
      qos: 0
      retain: true
      topic: "homeassistant/sensor/mesh_neighbor/{{ from }}-imp/config"
      payload: >
        {"name": "Node {{ from }} IMP",
         "state_topic": "msh/{YOUR_REGION}/2/json/mqtt/!{YOUR_NODE_HEX}",
         "value_template": "{% raw %}{% if value_json.from == {% endraw %}{{ from }}{% raw %} %}{{ value_json.payload.IMP | float(0) }}{% endif %}{% endraw %}",
         "unit_of_measurement": "kW",
         "device_class": "power",
         "state_class": "measurement",
         "unique_id": "mesh_{{ from }}_imp",
         "device": {"identifiers": ["mesh_node_{{ from }}"], "name": "Node {{ from }}", "model": "Heltec V3", "manufacturer": "Meshtastic"}}

  - delay:
      seconds: 1

  - service: mqtt.publish
    data:
      qos: 0
      retain: true
      topic: "homeassistant/sensor/mesh_neighbor/{{ from }}-exp/config"
      payload: >
        {"name": "Node {{ from }} EXP",
         "state_topic": "msh/{YOUR_REGION}/2/json/mqtt/!{YOUR_NODE_HEX}",
         "value_template": "{% raw %}{% if value_json.from == {% endraw %}{{ from }}{% raw %} %}{{ value_json.payload.EXP | float(0) }}{% endif %}{% endraw %}",
         "unit_of_measurement": "kW",
         "device_class": "power",
         "state_class": "measurement",
         "unique_id": "mesh_{{ from }}_exp",
         "device": {"identifiers": ["mesh_node_{{ from }}"], "name": "Node {{ from }}", "model": "Heltec V3", "manufacturer": "Meshtastic"}}

  - delay:
      seconds: 1

  - service: mqtt.publish
    data:
      qos: 0
      retain: true
      topic: "homeassistant/sensor/mesh_neighbor/{{ from }}-soc/config"
      payload: >
        {"name": "Node {{ from }} SOC",
         "state_topic": "msh/{YOUR_REGION}/2/json/mqtt/!{YOUR_NODE_HEX}",
         "value_template": "{% raw %}{% if value_json.from == {% endraw %}{{ from }}{% raw %} %}{{ value_json.payload.SOC | int(0) }}{% endif %}{% endraw %}",
         "unit_of_measurement": "%",
         "device_class": "battery",
         "state_class": "measurement",
         "unique_id": "mesh_{{ from }}_soc",
         "device": {"identifiers": ["mesh_node_{{ from }}"], "name": "Node {{ from }}", "model": "Heltec V3", "manufacturer": "Meshtastic"}}
mode: single
```

**Replace** the placeholders with your own values before importing:
- `{YOUR_REGION}` — e.g., `EU_868`
- `{YOUR_NODE_HEX}` — your receiving node's hex ID (e.g., `!a1b2c3d4` — the `!` is part of the id, **keep it**)
- `{YOUR_NODE_DECIMAL}` — your decimal node number (unquoted integer) to exclude your own messages

**How it works:**
1. Every message triggers the automation
2. The condition skips your own messages (`from == YOUR_NUM`) and non-meter messages
3. Publishes 3 retained MQTT discovery configs (IMP, EXP, SOC) for the node's `from` number
4. HA auto-creates 3 sensors, all grouped under one device per node
5. The 1-second delays between each publish prevent HA from creating separate device entries for each sensor
6. Sensors are permanent — retained configs survive HA and node restarts

**Result in HA:** For each neighbor you see 3 sensors (`IMP`, `EXP`, `SOC`) under one device entry (e.g., "Node 2712679380").

---

## 5. Adding More Households

| Step | What to do |
|------|-----------|
| New neighbor joins | They install a Heltec V3 + Tasmota, configure their node per §1, add the send automation per §3 |
| Existing households see them | Either: add a sensor block per §4.2 with their decimal number, or use the auto-discovery automation (§4.4) |
| No changes needed on the mesh | The new node is already on the shared LoRa channel; all existing nodes will receive its messages automatically |

---

## 6. Expected Message Flow

Examples use the JSON format (recommended).

### Send direction

```
HA publishes to:        msh/EU_868/2/json/mqtt/
Payload (JSON):
  {"from": 2892010904, "type": "sendtext",
   "payload": "{\"IMP\":0.3,\"EXP\":0.0,\"SOC\":85}",
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
  payload: {"IMP": 0.3, "EXP": 0.0, "SOC": 85}

Your node publishes to MQTT:
  Topic: msh/EU_868/2/json/mqtt/!your_node_hex
  Payload: {"from": 2712679380, "type": "text",
            "payload": {"IMP": 0.3, "EXP": 0.0, "SOC": 85},
            "channel": 1, ...}

Your HA receives it, checks from == NEIGHBOR_DECIMAL,
  valued_json.payload.IMP → sensor value
```


