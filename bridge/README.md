# LOTSE MQTT Bridge

Connects a Tasmota IR smart-meter sensor through Meshtastic LoRa to a clean MQTT topic — no Home Assistant addon, no regex parsing, no special tools on the consumer side.

## How it works

```
                      INGRESS (sensor house)                          EGRESS (receiver house)
Tasmota IR ──MQTT──► lotse-bridge ──Meshtastic downlink──► Device A ──LoRa──► Device B
                                                                                    │
                                                                         Meshtastic uplink
                                                                                    │
                                                                           lotse-bridge ──MQTT──► lotse/meter/power
                                                                                                      │
                                                                                              Any MQTT client
```

The bridge runs in two modes (or both simultaneously if MQTT broker is shared):

- **Ingress**: subscribes to Tasmota's raw sensor topic, extracts the power value, packs it as compact JSON, and publishes to Meshtastic's MQTT downlink channel.
- **Egress**: subscribes to Meshtastic's MQTT uplink topic, extracts the compact JSON, and publishes clean structured data to `lotse/meter/power`.

Any MQTT client subscribing to `lotse/meter/power` receives:

```json
{"power_w": 1234.0, "unit": "W", "timestamp": 1712505600.123}
```

No regex, no HA automations, no custom parsing.

## Setup

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Minimal — both ingress + egress on same broker:
export MQTT_BROKER=192.168.1.100
export INGRESS_NODE_NUM=2892010904
export EGRESS_NODE_HEX='!acaad598'
python3 lotse-bridge.py

# Ingress only (at the sensor — connects Tasmota → LoRa):
python3 lotse-bridge.py --mode ingress --broker 192.168.1.100 --ingress-num 2892010904 --tasmota-topic tele/tasmota_ir/SENSOR --tasmota-field ENERGY.Power

# Egress only (at the receiver — connects LoRa → clean MQTT):
python3 lotse-bridge.py --mode egress --broker 192.168.1.100 --egress-hex '!acaad598'
```

### Options

| Flag | Env var | Default | Description |
|------|---------|---------|-------------|
| `--mode` | `MODE` | `both` | `ingress`, `egress`, or `both` |
| `--broker` | `MQTT_BROKER` | `localhost` | MQTT broker address |
| `--port` | `MQTT_PORT` | `1883` | MQTT broker port |
| `--user` | `MQTT_USER` | — | MQTT username |
| `--password` | `MQTT_PASS` | — | MQTT password |
| `--tasmota-topic` | `TASMOTA_TOPIC` | `tele/tasmota_ir/SENSOR` | Input topic from Tasmota |
| `--tasmota-field` | `TASMOTA_FIELD` | `ENERGY.Power` | Dotted JSON path to the power value |
| `--region` | `MESHTASTIC_REGION` | `EU_868` | LoRa region code |
| `--downlink-channel` | `DOWNLINK_CHANNEL` | `mqtt` | Meshtastic channel name with downlink enabled |
| `--ingress-num` | `INGRESS_NODE_NUM` | `0` | Decimal node number (from Web UI > About) |
| `--egress-hex` | `EGRESS_NODE_HEX` | `!00000000` | Hex node ID of the egress device for uplink subscription |
| `--output-topic` | `OUTPUT_TOPIC` | `lotse/meter/power` | Clean output topic |
| `--lora-key` | `LORA_PAYLOAD_KEY` | `p` | JSON key used for power value in LoRa payload |
| `--verbose` | — | — | Enable debug logging |

All flags can also be set as environment variables (uppercased).

## Finding your node number

From Meshtastic Web UI → **About** page: note both the Hex Node ID (`!acaad598`) and Decimal Node Number (`2892010904`).

The **decimal number** goes in `INGRESS_NODE_NUM`. The **hex ID** (with `!` prefix) goes in `EGRESS_NODE_HEX`.

## What changed vs the old HA-automation approach

| Before | After |
|--------|-------|
| HA template sensor averages raw data | Bridge reads raw Tasmota MQTT directly |
| HA automation formats text, publishes to Meshtastic | Bridge packs data as compact JSON |
| HA automation uses regex to extract number from text | Bridge parses JSON — unambiguous |
| HA is required in the transport path | Bridge runs independently (any machine with Python) |
| Custom parsing needed on consumer side | Consumer gets clean `{"power_w": 1234}` |

## Notes

- The compact LoRa payload uses single-char keys (`"p"` instead of `"power_w"`) to stay well under Meshtastic's ~220-byte text limit.
- The output topic publishes with `retain=True` so late-joining subscribers immediately see the last known value.
- Tasmota's raw `ENERGY.Power` is instantaneous (W). If you need 15-min averages, change `--tasmota-field` to point to a HA-average topic, or average in the bridge (future enhancement).
