# Data Communication — Architecture Comparison

**Goal:** Get smart meter readings from Tasmota IR sensor → LoRa mesh → every neighbor's home automation, as simply as possible.

## Your setup (same for all approaches)

```
WiFi LAN (same network for all)
  ├── Tasmota IR sensor (publishes MQTT)
  ├── Heltec V3 (stock Meshtastic, can do MQTT + LoRa)
  ├── MQTT broker (Mosquitto or similar)
  └── Home Assistant (or other automation)
```

Each household has this. Neighbors communicate via LoRa 868 MHz between their Heltec V3s.

## The key insight: receive is easy, send is hard

| Direction | Complexity | How |
|-----------|-----------|-----|
| **Receive** LoRa → HA | **Trivial** | Enable MQTT + uplink on every Meshtastic node. All LoRa messages appear as MQTT on the broker. HA subscribes to `msh/+/2/json/LongFast/+` |
| **Send** Tasmota → LoRa mesh | **The problem** | Tasmota speaks MQTT, but Meshtastic needs specific JSON on a specific topic to inject into the mesh. Three ways in: MQTT downlink, USB serial, or custom firmware |

Every approach below solves SEND differently. RECEIVE is always the same:
- Each node has MQTT + JSON uplink enabled
- All LoRa messages land on `msh/{REGION}/2/json/LongFast/{NODE_HEX}`
- HA creates an MQTT sensor per neighbor topic

---

## Approach A: Python Serial API (recommended for POC)

A small Python script runs on a Raspberry Pi (or any always-on computer) connected via USB to the Heltec V3.

```
Tasmota ──MQTT──► Pi (Python script) ──USB serial──► Heltec V3 ──LoRa──► all nodes
                     │                                           
                     ▼ logs all received messages locally
                     ▼ publishes to HA lotse/+/power (optional)
```

**SEND:**
```python
import meshtastic.serial_interface
import paho.mqtt.client as mqtt

def on_tasmota_message(client, userdata, msg):
    power_w = parse_power(msg.payload)          # extract from JSON
    iface.sendText(f"HH1 PWR:{power_w:.0f}")    # broadcast to LoRa

iface = meshtastic.serial_interface.SerialInterface()
mqtt_client.on_message = on_tasmota_message
mqtt_client.subscribe("tele/tasmota_ir/SENSOR")
```

**RECEIVE:**
```python
def on_receive(packet):
    text = packet.get("payload", {}).get("text", "")
    # "HH2 PWR:567"
    log_to_file(text)
    publish_to_ha_mqtt(text)

iface.on_receive = on_receive
```

**HA side:** MQTT sensor subscribes to `lotse/+/power` → creates entities
**No MQTT config on Heltec V3** — USB serial is the transport. Stock firmware.

| | |
|---|---|
| **Stock firmware?** | ✅ Yes — stock Meshtastic, no custom build |
| **Extra hardware?** | Raspberry Pi Zero (~€15) per household |
| **Code to write** | ~50 lines Python |
| **Config traps** | None — USB serial just works |
| **Fails if** | Pi dies (but LoRa mesh still works between nodes) |
| **HA integration** | Script publishes to `lotse/{household}/power` |

---

## Approach B: HA Automation + MQTT Downlink

Use Home Assistant automations to publish directly to Meshtastic's MQTT downlink topic.

```
Tasmota ──MQTT──► HA (automation YAML) ──msh/{R}/2/json/mqtt/──► Heltec V3 ──LoRa──► all
                                  (mqtt channel + downlink enabled)
```

**SEND (HA automation YAML):**
```yaml
action:
  - service: mqtt.publish
    data:
      topic: "msh/EU_868/2/json/mqtt/"
      payload: >
        {"from": 2892010904, "type": "sendtext",
         "payload": "HH1 PWR:{{ states('sensor.ir_power')|int }}"}
```

**One node** must have a channel named `"mqtt"` with downlink enabled. That node's **decimal node number** goes in the `from` field. No other node should have this channel.

**RECEIVE:** Each node with uplink enabled publishes LoRa → MQTT. HA subscribes.

| | |
|---|---|
| **Stock firmware?** | ✅ Yes |
| **Extra hardware?** | None |
| **Code to write** | ~20 lines YAML in HA |
| **Config traps** | ⚠️ **Silent failures** if `from` is wrong, topic has wrong region, channel name isn't exactly `"mqtt"`, or downlink isn't enabled. Error logs only visible on the node's serial console. |
| **Fails if** | HA is down (no data enters LoRa mesh), or the single injector node is offline |
| **HA integration** | Built-in — HA is the sender and receiver |

---

## Approach C: Bridge Script (current `lotse-bridge.py`)

Same MQTT downlink mechanism as Approach B, but in a standalone Python script instead of HA YAML.

```
Tasmota ──MQTT──► lotse-bridge (ingress) ──msh/.../mqtt/──► Heltec V3 ──LoRa──► all
                                                               │
                                                    uplink MQTT │
                                                               ▼
                                              lotse-bridge (egress) ──lotse/meter/power──► HA
```

Already exists at `bridge/lotse-bridge.py`. Works, tested.

| | |
|---|---|
| **Stock firmware?** | ✅ Yes |
| **Extra hardware?** | None (or Pi, depending where the script runs) |
| **Code to write** | Already written (356 lines) |
| **Config traps** | Same as Approach B (downlink config, `from` field, channel name) |
| **Fails if** | Same failure modes as B, plus the bridge script itself (logs help but still a process to manage) |
| **HA integration** | Clean topic `lotse/meter/power` |

---

## Approach D: Full MQTT (No LoRa)

Skip the LoRa mesh entirely. All households share one MQTT broker (e.g., on a VPS or a participant's HA machine).

```
Tasmota ──MQTT──► shared broker ──MQTT──► every neighbor's HA
```

Each household's Tasmota publishes to `lotse/{household_id}/power`. All neighbors subscribe.

| | |
|---|---|
| **Hardware** | None (uses existing WiFi) |
| **Code** | None (MQTT config only) |
| **Complexity** | Zero |
| **LoRa resilience?** | ❌ If internet/WiFi is down, no data flows |
| **Single point of failure** | The shared broker |
| **Privacy** | All data goes through a central point |

---

## Approach E: Custom Firmware (Heltec V3 handles MQTT directly)

Custom firmware on the Heltec V3 that subscribes to Tasmota's MQTT topic and broadcasts over LoRa — no computer needed.

```
Tasmota ──MQTT──► Heltec V3 (custom fw) ──LoRa──► all nodes
                      │
                 has MQTT client built in
                 subscribes to tele/tasmota_ir/SENSOR
                 broadcasts power value over LoRa
```

Also handles receive: all LoRa messages → serial or display.

| | |
|---|---|
| **Stock firmware?** | ❌ Requires custom firmware from scratch |
| **Extra hardware?** | None (Heltec does everything) |
| **Code to write** | 500+ lines C++ (MQTT client + LoRa send/receive + parsing) |
| **Config traps** | WiFi credentials must be configured on each node; no UI unless you build one |
| **Fails if** | Heltec crashes (no watchdog recovery without more code) |
| **HA integration** | Separate — would need a script or MQTT from the node |

---

## Comparison

| | A: Python Serial | B: HA Downlink | C: lotse-bridge | D: MQTT only | E: Custom FW |
|---|---|---|---|---|---|
| **Extra hardware** | Pi per HH (~€15) | None | None (or Pi) | None | None |
| **Stock Meshtastic** | ✅ | ✅ | ✅ | N/A | ❌ |
| **Code to write** | ~50 lines Python | ~20 lines YAML | 0 (exists) | 0 | 500+ lines C++ |
| **Config traps** | None | High | Medium | None | Low (but lots of code) |
| **LoRa resilience** | ✅ (mesh works if Pi dies) | ⚠️ (no injector = no send) | ⚠️ (same) | ❌ | ✅ (standalone) |
| **Failure visibility** | Script logs | Silent drops | Script logs | Immediate | Serial logs |
| **Ease of adding HH** | Add Pi + USB | Configure one node's channel | Add to bridge config | Add MQTT topic | Flash custom firmware |
| **Development time** | 1 hour | 1 hour | 0 (exists) | 10 min | Weeks |

---

## Data format

Needs to fit in Meshtastic's ~220-byte text limit. Simple enough to parse on receive.

| Format | Example | Bytes | Parse |
|--------|---------|-------|-------|
| **Plain text** | `HH1 PWR:1234` | ~14 | Split on space + colon — simplest |
| Compact JSON | `{"i":"HH1","p":1234}` | ~20 | `json.loads` — extensible |
| CSV | `HH1,1234` | ~10 | `split(",")` — minimal |

For the POC, plain text (`HH1 PWR:1234`) is easiest — humans can read it on the Meshtastic channel, and HA can parse it with a template sensor.

---

## Open questions

**Q1 — One injector vs. every node sends?**  
In Approaches B/C, only ONE node has the `mqtt` channel with downlink. All Tasmota data must route through that household's node. If that household's power or internet goes out, nobody can send. **But:** if every node has the downlink channel, every node will re-inject every message, causing duplicates in the mesh.  
*Solution attempted in HA-integration.md: only one node has downlink enabled.*  
→ Is this acceptable for your neighborhood? What if that household is on vacation?

**Q2 — Does each household need a computer (Approach A)?**  
A Pi Zero W is ~€15 and draws ~1W. But it's another device to maintain. Is that acceptable, or is zero-extra-hardware (B/C/E) a hard requirement?

**Q3 — Who owns the shared MQTT broker (Approach D)?**  
If you skip LoRa and just use MQTT, whose broker do you use? One household's? A VPS with monthly cost? That creates a dependency and potentially a single point of failure.

**Q4 — How often do nodes send data?**  
Every 5 seconds? Every minute? Every 5 minutes? The LoRa 1% duty cycle at 868 MHz limits total airtime. 10 households sending every 5 seconds would saturate the channel. This affects which format and approach is viable.

**Q5 — What happens when a neighbor joins late?**  
They get no historical data. Is that OK? Do you need retain/replay of the last reading on the MQTT topic? (Approach A/C can publish with `retain=True`; B can too.)

**Q6 — How do households identify each other?**  
`HH1`, `HH2` is fine for a small group, but do you want a registry? Self-assigned IDs (risk of collision)? MAC-based? Fixed in config?

---

## Decision (5 May 2026)

After discussion, the chosen architecture is **Approach B (HA MQTT Downlink) — every node, not one.**

**Key insight:** every node CAN have the `mqtt` channel with downlink enabled. Meshtastic checks the `from` field against each node's own number — only the matched node injects into LoRa. So all households can publish to the SAME `msh/{R}/2/json/mqtt/` topic, each with their own node's `from` number. No conflicts, no single point of failure.

```
Household 1 (HA publishes with from:node1)                 
Tasmota ──MQTT──► HA automation ──MQTT──► Heltec V3 (mqtt channel + downlink)
                                            │
                                            ▼ LoRa
                                       all neighbors

Household 2 (HA publishes with from:node2)                 
Tasmota ──MQTT──► HA automation ──MQTT──► Heltec V3 (mqtt channel + downlink)
                                            │
                                            ▼ LoRa
                                       all neighbors
```

See `ha-mesh-setup.md` for the complete per-household setup guide.
