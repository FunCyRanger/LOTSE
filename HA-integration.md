# Home Assistant Integration — Round-Trip Test

For **stock Meshtastic firmware** (validated against v2.7.9). The critical MQTT/JSON downlink requirements ("mqtt" channel name, `from` field validation) are standard upstream behavior.

## Architecture

```
[IR Sensor Values in HA]
    │
    ▼ MQTT publish
[LOTSE2 (on home WiFi)]  ← gateway with "mqtt" channel + downlink
    │
    ▼ LoRa 868 MHz
[LOTSE1 (on home WiFi)]  ← receives packet, publishes back to MQTT
    │
    ▼ MQTT subscribe
[Home Assistant] → verify round-trip
```

---

## 1. Node Configuration (Web UI)

### On BOTH LOTSE1 and LOTSE2

**MQTT Settings:**
| Field | Value |
|-------|-------|
| MQTT Enabled | ✅ Check |
| Address | Your Home Assistant IP (e.g., `192.168.1.100`) |
| Port | `1883` |
| JSON Output Enabled | ✅ Check (**CRITICAL**) |
| Username | Your MQTT username (if auth required) |
| Password | Your MQTT password (if auth required) |
| TLS | ☐ Uncheck (for local network) |

**Primary Channel (index 0, usually `LongFast`):**
| Setting | Value |
|---------|-------|
| Uplink Enabled | ✅ Check |
| Downlink Enabled | Doesn't matter for uplink |

### ONLY on LOTSE2 (the injector/gateway)

**Create a NEW channel:**
| Setting | Value |
|---------|-------|
| Name | **`mqtt`** (exactly this — lowercase recommended) |
| PSK | Default/random (anything works) |
| Uplink Enabled | ☐ Can be unchecked |
| Downlink Enabled | ✅ **Check this — CRITICAL** |

**Then REBOOT LOTSE2** — channel changes don't take effect until reboot.

### On LOTSE1 (the receiver)

- Do NOT create an "mqtt" channel
- OR if you do, leave **Downlink Disabled**

You only want **one node** (LOTSE2) injecting MQTT messages into the LoRa mesh.

---

## 2. Get Your Identifiers

From Web UI → **About** or **Info** page, for **each node**:

| Identifier | Example | Where Used |
|------------|---------|------------|
| Hex Node ID (with `!` prefix) | `!a1b2c3d4` | MQTT topic paths |
| Decimal Node Number | `2712679380` | JSON `from` field — **most critical** |
| Region | `EU_868`, `EU868`, or `EU` | Topic structure |

**Finding decimal if not shown:**
1. Use MQTT Explorer and look at the `from` field in any JSON message
2. Or calculate: `!a1b2c3d4` → drop `!`, parse hex `0xa1b2c3d4` to decimal

**Confirming with MQTT Explorer:**
- Connect to your HA MQTT broker
- Subscribe to `msh/#`
- Reboot nodes — observe topics that appear
- Note the EXACT region string (varies: `EU_868`, `EU868`, `EU`, etc.)

Expected topics:
```
msh/{REGION}/2/json/LongFast/!{LOTSE1_HEXID}
msh/{REGION}/2/json/LongFast/!{LOTSE2_HEXID}
```

---

## 3. Home Assistant: Sender Automation

**Trigger:** Every 2 minutes (or adjust as needed)

**Action:** MQTT publish to the `mqtt` channel topic

### Automation YAML

```yaml
alias: "IR Sensor → LoRa (LOTSE2)"
description: "Send meter values to mesh via MQTT downlink"
trigger:
  - platform: time_pattern
    minutes: "/2"
condition: []
action:
  - service: mqtt.publish
    data:
      qos: 0
      retain: false
      topic: "msh/{YOUR_REGION}/2/json/mqtt/"
      payload: >
        {
          "from": {LOTSE2_DECIMAL_NODE_NUM},
          "type": "sendtext",
          "payload": "PWR:{{ states('sensor.ir_stromzahler_elz_wert')|int(0) }}W,IMP:{{ states('sensor.ir_stromzahler_elz_elz_pv_1_8_0')|float(0) }}kWh,EXP:{{ states('sensor.ir_stromzahler_elz_elz_pv_2_8_0')|float(0) }}kWh"
        }
mode: single
```

### Replace These Placeholders

| Placeholder | Example | Notes |
|-------------|---------|-------|
| `{YOUR_REGION}` | `EU_868` | From MQTT Explorer observation |
| `{LOTSE2_DECIMAL_NODE_NUM}` | `2712679380` | **Decimal number, NOT hex, NOT quoted** |

### ⚠️ Critical Notes (from firmware source `MQTT.cpp`)

1. **Topic must be `/json/mqtt/`**, NOT `/json/LongFast/`
   - Line 363: `Channels::mqttChannel = "mqtt"` — hardcoded channel name check

2. **`from` must equal LOTSE2's own decimal node number**
   - Line 135: `json["from"]->AsNumber() == nodeDB->getNodeNum()`
   - Wrong `from` = silent failure ("not a valid envelope")

3. **JSON structure required:**
   ```json
   {"from": DECIMAL_NUM, "type": "sendtext", "payload": "your message"}
   ```

---

## 4. Home Assistant: Receiver Entity

### Option A: MQTT Sensor (shows last received message)

Add to `configuration.yaml`:

```yaml
mqtt:
  sensor:
    - name: "LOTSE1 Received Meter Data"
      unique_id: "lotse1_meter_data"
      state_topic: "msh/{YOUR_REGION}/2/json/LongFast/!{LOTSE1_HEXID}"
      value_template: >
        {% if value_json.type == "text" and value_json.payload.text is defined %}
          {{ value_json.payload.text }}
        {% else %}
          {{ this.state }}
        {% endif %}
      icon: mdi:radio
```

### Option B: Automation on Receive

```yaml
alias: "LoRa → HA (LOTSE1 received)"
description: "Log and notify when LOTSE1 receives a mesh message"
trigger:
  - platform: mqtt
    topic: "msh/{YOUR_REGION}/2/json/LongFast/!{LOTSE1_HEXID}"
    value_template: |
      {% if value_json.type == "text" %}on{% endif %}
    payload: "on"
condition:
  - condition: template
    value_template: "{{ trigger.payload_json.payload.text is defined }}"
action:
  - service: persistent_notification.create
    data:
      title: "LoRa Received"
      message: "{{ trigger.payload_json.payload.text }}"
  - service: input_text.set_value
    data:
      value: "{{ trigger.payload_json.payload.text }}"
    target:
      entity_id: input_text.last_lora_message
mode: queued
max: 10
```

---

## 5. Expected Message Flow

### Send (HA → LOTSE2 → LoRa)

**HA publishes to:**
```
Topic: msh/{REGION}/2/json/mqtt/
Payload: {"from": LOTSE2_DEC_NUM, "type": "sendtext", "payload": "PWR:1234W,IMP:50000.0kWh,EXP:1000.0kWh"}
```

**LOTSE2:**
- Receives MQTT
- Validates `from` matches its own node number
- Validates channel name is `"mqtt"` with downlink enabled
- Injects as TEXT_MESSAGE_APP portnum into LoRa mesh

### Receive (LoRa → LOTSE1 → HA)

**LOTSE1:**
- Receives LoRa packet
- Primary channel has `uplink_enabled = true`
- Publishes to MQTT

**HA sees:**
```
Topic: msh/{REGION}/2/json/LongFast/!{LOTSE1_HEXID}
Payload:
{
  "from": LOTSE2_DEC_NUM,
  "to": 4294967295,
  "channel": 0,
  "type": "text",
  "payload": {
    "text": "PWR:1234W,IMP:50000.0kWh,EXP:1000.0kWh"
  },
  "sender": "!{LOTSE2_HEXID}",
  "timestamp": 1712505600
}
```

---

## 6. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| No `msh/` topics appear in MQTT Explorer | MQTT disabled, wrong IP, or JSON disabled | Double-check MQTT settings, enable JSON, check broker connectivity |
| Message never enters mesh | Wrong `from` value | **Must be LOTSE2's DECIMAL node number**, NOT hex string |
| LOTSE2 serial: `"not a valid envelope"` | `from` field wrong, or `sender` field present | Remove `sender` field entirely if copying uplink JSON |
| LOTSE2 serial: `"channel not called 'mqtt'"` | Topic has `LongFast` instead of `mqtt` | Topic must end with `/json/mqtt/`, NOT `/json/LongFast/` |
| Both nodes inject duplicate messages | Both have downlink enabled on "mqtt" channel | Only enable downlink on ONE node (LOTSE2) |
| JSON message too long | Text > ~220 bytes | Keep payload concise — LoRa is slow |

### Best Debug Tools

1. **MQTT Explorer** — see exactly what's being published
2. **Serial Monitor** — LOTSE2 logs the exact failure reason
   ```bash
   pio device monitor -p /dev/ttyUSB0 -b 115200
   ```

### Key Log Messages to Watch For

| Log Message | Meaning |
|-------------|---------|
| `JSON payload ..., length ...` | Success — message accepted for sending |
| `not a valid envelope` | `from` field wrong or JSON structure invalid |
| `channel not called 'mqtt' or without downlink` | Topic wrong or channel config wrong |
| `payload too long, drop` | Keep message shorter |

---

## 7. Reference: Firmware Validation Logic (from `meshtastic-fork-clean/src/mqtt/MQTT.cpp`)

```cpp
// Line 129-138: isValidJsonEnvelope — ALL must be true
return (
  (sender != owner.id) &&              // if "sender" present, not our own
  (hopLimit is number, if present) &&  // optional field validation
  (from EXISTS && from IS NUMBER && from == nodeDB->getNodeNum()) &&  // CRITICAL
  (type EXISTS && type IS STRING) &&   // must be "sendtext"
  (payload EXISTS)                      // the actual message
);

// Line 361-367: Channel name check
// We allow downlink JSON packets only on a channel literally named "mqtt"
const meshtastic_Channel &sendChannel = channels.getByName(channelName);
if (!(strncasecmp(channels.getGlobalId(sendChannel.index),
        Channels::mqttChannel, strlen(Channels::mqttChannel)) == 0 &&
      sendChannel.settings.downlink_enabled)) {
    LOG_WARN("JSON downlink received on channel not called 'mqtt'...");
    return;  // SILENTLY DROPPED
}
```

From `Channels.cpp:22`:
```cpp
const char *Channels::mqttChannel = "mqtt";
```
