# Prototype Build Plan

**Purpose:** Prove the physical and communication layer before investing in the full protocol stack.
**Based on:** Brainstorming.md §10 Recommendations for Next Step.

---

## P1. Step 1 — Build Agent Prototype (ESP32 + IR Reader)

Goal: A working ESP32 that reads a German smart meter via its optical IR interface and outputs parsed OBIS values.

**Validates:** UC-02 (Record consumption & generation data) from LEM-Requirements.md §6.

### P1.1 Bill of Materials

| Item | Part | Est. cost | German source |
|------|------|-----------|---------------|
| Agent MCU + LoRa + display | LilyGO T3 S3 SX1262 868MHz (H595) or SX1276 868MHz (H596) | €22-28 | [tinytronics.nl](https://www.tinytronics.nl) (NL, ships DE), [openelab.de](https://www.openelab.de) (Munich, ships DE), [Amazon.de](https://www.amazon.de/LILYGO-T3S3-V1-3-ESP32-S3-Entwicklungsboard/dp/B0GQSKYYN1) (DE warehouse) |
| IR head | WattWächter TTL (WS-IR-UART/TTL) | €24 | [SmartCircuits / WattWächter](https://www.xn--wattwchter-u5a.de/products/wattwaechter-ttl) |
| USB-C cable | USB-C data cable | €2-3 | Conrad, Reichelt |
| USB power supply | 5V 1A (phone charger) | €0 (likely owned) | — |
| **Total** | | **€48-55** | |

**Why this hardware?** See Brainstorming §3.2 and §5.5 for full hardware evaluation.

**LilyGO T3 S3** (€22-28, SX1262 or SX1276 variant): ESP32-S3 dual-core 240MHz, onboard LoRa 868MHz (ETSI RED compliant), 0.96" OLED (SSD1306) for local status display, SD card slot for data retention (Q7), USB-C, LiPo charger. Both SX1262 and SX1276 variants work for LEM — SX1276 is older but equally capable for this use case. The Amazon.de listing (SX1276 868MHz) ships from a German warehouse for fast delivery.

**WattWächter TTL** (~€24, smartcircuits.de): professional IR head with screw terminals — no soldering required. Pre-wired 1m cable with 4 color-coded wires (braun=VCC, grün=RX, gelb=TX, weiß=GND). TTL UART output (9600 baud, 3.3V), magnetic mount (8.5kg holding force), built-in reverse polarity protection, CE certified, made in Germany. Connects to T3 S3 GPIO in seconds with Dupont jumper wires.

**What we rejected** (and why):
| Device | Price | Problem |
|--------|-------|---------|
| bitShake Air | ~€35 | ESP32-C3, no SPI bus exposed — cannot add LoRa. Locked Tasmota firmware cannot run agent state machine. |
| bitShake SmartMeterReader-UART | ~€25-27 | Requires soldering to pads — violates "layperson-installable" (NFR C3). WattWächter TTL is cheaper and truly no-solder. |
| IMST iOKE868 | ~€126 | LoRaWAN-only bridge with closed firmware. Cannot run agent logic. No WiFi/MQTT for local EMS. Budget exhaustion. |
| WiFi IR SMI V32 | ~€45 | ESP32-C3, no LoRa SPI. Limited to meter reading only, no agent. |
| Breadboard + BPW40 + SX1276 | ~€22 | Valid proof-of-concept but not production-close. Soldering required, fragile, no display, no SD card. T3 S3 costs barely more and is production-ready. |

**Budget note:** €48-55 per household leaves €45-152 headroom within the €100-200 target (AGENTS.md cost breakdown) for enclosure, antenna upgrade, and installation. Savings possible: use the eBay WattWächter listing (~€14 from dtb-systeme, Bösel) instead of the official store.

### P1.2 Circuit: WattWächter TTL → T3 S3 UART

No breadboard, no soldering. The WattWächter TTL comes with a pre-wired 1m cable (4 color-coded wires) and connects to the T3 S3 via the built-in screw terminals:

| WattWächter wire | Color | → T3 S3 pin | Function |
|------------------|-------|-------------|----------|
| VCC | Braun (brown) | 3.3V | Power (3.3V, built-in reverse polarity protection) |
| GND | Weiß (white) | GND | Ground |
| RX | Grün (green) | GPIO4 | UART RX: data from meter → ESP32 |
| TX | Gelb (yellow) | *(not connected)* | UART TX: optional — for PIN entry to meter in later iteration |

**Connection steps:**
1. Strip the pre-wired cable ends ~5mm
2. Insert each wire into the T3 S3 pin headers (use Dupont-to-Dupont jumper wires or bare wires directly)
3. Tip: crimp Dupont female connectors onto the WattWächter cable ends for a plug-and-play connection to the T3 S3

**ESP32-S3 GPIO matrix note:** ESP32-S3 has a flexible GPIO matrix — any GPIO can serve as UART RX. We use GPIO4 (free on T3 S3, not used by PSRAM/FLASH/LoRa/display). The WattWächter outputs 9600 baud 8N1 TTL which feeds directly into the ESP32-S3 UART.

**For PIN entry (future):** To unlock 16.7.0 (current power), connect the yellow (TX) wire to T3 S3 GPIO5 (UART TX). The agent can send IR pulse sequences through the head to the meter. This is optional — many meters display 16.7.0 via a physical button.

### P1.3 Software Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Framework | Arduino core for ESP32 (ESP32-S3 variant) | Largest ecosystem, most SML parsing examples, ESP32-S3 support via `esp32` platform |
| Build system | PlatformIO | Cross-platform, library manager, simple CLI, `board = esp32-s3-devkitc-1` |
| SML parser | `sml` library by m-, or `SmartMeter` library | Mature, handles German smart meter SML output |
| OBIS extraction | Manual OBIS code filter on parsed SML | Targeted parsing is simpler than full SML stack |
| Serial (meter) | HardwareSerial on UART (GPIO4 RX) using ESP32-S3 GPIO matrix | UART1 or UART2 mapped to GPIO4 |
| LoRa driver | RadioLib (SX1262) | Mature OSS, supports SX1262, RadioLib handles SPI + IRQ + DIO + CAD |
| Display | Adafruit SSD1306 + Adafruit GFX | 0.96" OLED for local status (grid limit, current power, agent state) |
| SD card | SD_MMC or SD library (ESP32) | Data logging for validation and potential retention (Q7) |
| WiFi (optional) | WiFi.h (ESP32 Arduino core) | Only needed if forwarding to MQTT |

**Why Arduino over ESPHome:** ESPHome (listed in Brainstorming §3.2) is simpler (YAML-based) but limited for custom load-shed logic, flexible MQTT topic control, and the agent state machine to come. Arduino + PlatformIO gives full control over the agent behavior with minimal overhead.

**EMS integration deferred:** This prototype outputs parsed meter data over serial only. Integration with OpenEMS/evcc/Home Assistant via MQTT topics (Brainstorming §3.3) will be added in the next build iteration, after the physical layer is proven.

### P1.4 Flashing & First Test

```bash
# Prerequisites
pip install platformio

# Create project (ESP32-S3 — T3 S3 uses S3 variant)
pio init --board esp32-s3-devkitc-1

# PlatformIO project configuration
# Set the following in platformio.ini for T3 S3 SX1262:
#   board_build.mcu = esp32s3
#   board_build.f_cpu = 240000000L
#   board_build.flash_mode = qio
#   board_build.flash_size = 16MB
#   board_build.psram = enable
#   board_build.psram_mode = octal

# Install libraries
pio pkg install --library "m-/SML"
pio pkg install --library "jgromes/RadioLib"       # SX1262 LoRa
pio pkg install --library "adafruit/Adafruit SSD1306"  # OLED display
pio pkg install --library "adafruit/Adafruit GFX Library"

# Build and flash
pio run --target upload

# Monitor serial output (T3 S3 uses USB CDC on UART0)
pio device monitor --baud 115200 --rtscts 0 --dtr 0
```

> **Note:** LilyGO T3 S3 does not have a dedicated PlatformIO board definition yet. Use `esp32-s3-devkitc-1` as the base board and override the flash/PSRAM settings. See [LilyGO T3 S3 docs](https://github.com/Xinyuan-LilyGO/T3_S3) for pinout and configuration.

Expected output when held against a live smart meter:
```
[READ] 1.8.0: 12345.678 kWh  (total consumption)
[READ] 2.8.0:   234.567 kWh  (total feed-in)
[READ] 16.7.0:   1.234 kW     (current power)
```

### P1.5 First Test: Smart Meter Simulator (No Meter Needed)

Before touching a real meter, verify the circuit and software with a serial simulator:

```python
# meter_simulator.py — sends fake SML frames over USB serial
# Run on PC, connect ESP32 USB to PC
# ESP32 reads from USB-serial (UART0) instead of IR sensor UART2
```

1. Wire ESP32 USB to PC
2. Upload agent firmware configured for Serial.read() on UART0 (debug mode)
3. Run `python meter_simulator.py` — sends SML frames at configurable intervals
4. Verify ESP32 console shows correct OBIS values

### P1.6 Second Test: Real Smart Meter

1. Attach the WattWächter TTL magnetically over the meter's IR interface (round/rectangular window, usually bottom-left) — the 8.5kg neodym magnet holds it securely
2. The magnetic mount holds it in place — no tape or alignment needed
3. The meter LED inside the IR window should flash as data is transmitted
4. On first reading without PIN: expect only total consumption (1.8.0) — no current power (16.7.0)
5. To get current power: request PIN from Messstellenbetreiber, enter via flashlight pulses on the meter's optical input (or use the meter's button sequence)
6. Verify: 1.8.0 value matches the physical meter display

### P1.7 Pin Entry Procedure (for Current Power)

Many German meters lock 16.7.0 behind a 4-digit PIN:

1. Request PIN from Messstellenbetreiber (may take 2-4 weeks)
2. On the meter, enter PIN via the optical interface:
   - With the WattWächter TTL: connect the yellow (TX) wire to a T3 S3 GPIO (e.g., GPIO5 as UART TX). The agent can send IR pulse sequences through the head's IR LED to the meter's IR receiver.
   - Manually: use a flashlight to pulse the meter's IR receiver. Sequence: meter menu → PIN entry → confirm.
   - Or: use the meter's physical button if available
3. Alternative: many meters have a "display mode" button that cycles through screens including current power — read the value visually

> **Note:** The WattWächter yellow (TX) wire enables programmatic PIN entry. This is a future enhancement — for the initial prototype, manual PIN entry (option 2 or 3) is sufficient.

---

## P2. Step 2 — Validate SML Parsing

**Validates:** UC-02 (record consumption & generation data) across multiple meter brands. This ensures the agent can read any German smart meter, not just one model.

### P2.1 OBIS Code Catalog (Common German Meters)

| Code | Meaning | Unit | Typical present? |
|------|---------|------|-----------------|
| 1.8.0 | Total consumption (Wirkarbeit Bezug) | kWh | ✅ Always |
| 2.8.0 | Total feed-in (Wirkarbeit Lieferung) | kWh | ✅ Always (if PV) |
| 16.7.0 | Current power (Wirkleistung Bezug) | W | ⚠️ Needs PIN |
| 36.7.0 | Current power (Wirkleistung Lieferung) | W | ⚠️ Needs PIN |
| 1.8.1 | Consumption HT (Hochtarif) | kWh | ✅ If TOU tariff |
| 1.8.2 | Consumption NT (Niedertarif) | kWh | ✅ If TOU tariff |
| 32.7.0 | Current voltage L1 | V | Sometimes |
| 52.7.0 | Current voltage L2 | V | Sometimes |
| 72.7.0 | Current voltage L3 | V | Sometimes |

### P2.2 Test Matrix

| Brand | Known OBIS quirks | Status |
|-------|-------------------|--------|
| ISKRA MT174 / MT175 | Standard SML, 9600 baud | 🔄 To test |
| Landis+Gyr E450 / E650 | Standard SML, 9600 baud | 🔄 To test |
| Holley DTZ541 | Standard SML, 115200 baud | 🔄 To test |
| EMH eBZ | Custom OBIS extensions | 🔄 To test |
| Generic (any mME/iMSys) | DIN EN 62056-21 compliant | 🔄 To test |

### P2.3 Common SML Parsing Issues

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| No data from IR sensor | IR head alignment off | Adjust magnetic mount position/rotation |
| Garbled output | Wrong baud rate | Try 9600 vs 115200 vs 38400 |
| Only zeros | PIN not entered | Request PIN from Messstellenbetreiber |
| Intermittent readout | Ambient light interference | Shroud the sensor with black tape |
| No 2.8.0 value | No PV or meter doesn't measure feed-in | Check if meter is a two-way meter |
| CRC errors | Weak IR signal | Better alignment, clean meter window |

---

## P3. Step 3 — Build Test Receiver

**⚠️ This is test-only infrastructure.** Phase 1 has no production coordinator (Brainstorming §5.1, Q2). This receiver is only needed to validate range and latency in steps 4 and 5. In production, each agent operates independently with no inter-household communication.

The receiver can be as simple as a second ESP32+LoRa or an RPi.

### P3.1 Option A: T3 S3 Test Receiver (Cheapest)

A second LilyGO T3 S3 SX1262 (identical to the agent) running minimal receiver firmware. Acts as message sink for range testing.

```bash
# Flash minimal receiver firmware
pio run -e receiver --target upload
```

Messages appear on serial console:
```
[RX] 2026-05-16 14:30:01  RSSI: -72 dBm  SNR: 8 dB  MSG: GridLimit import=5000W
[RX] 2026-05-16 14:30:06  RSSI: -75 dBm  SNR: 7 dB  MSG: GridLimit import=5000W
```

### P3.2 Option B: RPi Test Receiver (Full-Featured)

| Component | Part | Cost |
|-----------|------|------|
| Raspberry Pi 3B+ or 4 | Any model | €35-55 |
| SD card (16GB+) | | €8-10 |
| Power supply + case | | €10-15 |
| LoRa hat (optional, for LoRa path) | Waveshare SX1262 HAT or Dragino | €20-30 |
| **Total (RPi only)** | | **€53-80** |
| **Total (RPi + LoRa)** | | **€73-110** |

Setup:

```bash
# Install Raspberry Pi OS Lite
# Install Mosquitto MQTT broker (needed if testing MQTT path)
sudo apt update && sudo apt install -y mosquitto mosquitto-clients

# Install LoRa hat SPI libraries (if using LoRa)
sudo raspi-config  # enable SPI
pip install spidev

# Create test log directory
mkdir -p ~/lem-test/logs

# Run minimal receiver script
python3 test_receiver.py  # prints received messages to terminal + log
```

### P3.3 Minimal Test Receiver Script

```python
# test_receiver.py — receives LoRa or MQTT messages, logs + displays
# For initial prototype testing, just print everything received.

import sys
import time
from datetime import datetime

def on_message(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[RX] {ts}  {msg}")
    with open("logs/test_receiver.log", "a") as f:
        f.write(f"{ts}  {msg}\n")

# Phase 1: just read from stdin (simulated messages)
# Phase 2: read from LoRa module over SPI
# Phase 3: read from MQTT broker

if __name__ == "__main__":
    print("Test receiver — waiting for messages...")
    for line in sys.stdin:
        on_message(line.strip())
```

---

## P4. Step 4 — Range Testing in Real Neighborhood

### P4.1 Procedure

| Step | Action |
|------|--------|
| 1 | Place test receiver at a fixed location (e.g., ground floor apartment, cellar) |
| 2 | Start the agent (ESP32 + LoRa) continuously broadcasting a test message (e.g., GridLimit) every 10s |
| 3 | Walk the agent through the neighborhood in a backpack/pocket |
| 4 | At each measurement point: stop for 30s, note location, RSSI, packet loss |
| 5 | Mark locations on a map (Google Maps / OpenStreetMap printout) |
| 6 | Repeat at night (less interference) and in rain (attenuation test) |
| 7 | Test the critical path: from receiver location to the farthest household's cellar |

**Note:** The GridLimit message in this test is a payload-only construct. In Phase 1 production, the grid limit is a locally configured value per household (Brainstorming §5.1, Q4) — no messages are broadcast between households. The limit is set during onboarding and stays on the local agent.

### P4.2 Measurement Points

| # | Location | Distance from receiver | Obstacles | RSSI (dBm) | SNR (dB) | Pkts sent | Pkts recv | Loss % | Notes |
|---|----------|---------------------|-----------|------------|----------|-----------|-----------|--------|-------|
| 1 | Same room (baseline) | 2m | — | | | 20 | | | |
| 2 | Next room, 1 wall | 5m | 1 brick wall | | | 20 | | | |
| 3 | Opposite side of house | 20m | 3 walls, floor | | | 20 | | | |
| 4 | Cellar of same building | 30m | 2 floors, concrete | | | 20 | | | |
| 5 | Neighbor house, cellar | 50m | 2 houses, walls | | | 20 | | | |
| 6 | Neighbor house, cellar | 75m | 3 houses, walls | | | 20 | | | |
| 7 | Neighbor house, cellar | 100m | 4 houses, walls | | | 20 | | | |
| 8 | Maximum distance reached | ___m | | | | 20 | | | |

### P4.3 Pass/Fail Criteria

- **PASS**: ≥90% packet delivery at 100m through walls/cellars (any orientation)
- **PASS**: ≥80% packet delivery at 150m
- **FAIL**: <50% packet delivery at 100m — try different antenna, higher power, or lower SF
- **FAIL**: Complete dropout before 100m — communication medium unsuitable for this neighborhood

### P4.4 Tuning Knobs (if range is insufficient)

| Parameter | Effect | Tradeoff |
|-----------|--------|----------|
| Spreading Factor (SF) | Higher SF = longer range, slower | SF12 = ~3× range but 4× airtime |
| Output power | +14 dBm → +20 dBm adds ~50% range | Higher power draw |
| Antenna | Quarter-wave whip vs PCB trace | External antenna = 3-6 dB gain |
| Antenna placement | Elevation, away from metal | Critical in cellars |

---

## P5. Step 5 — Latency & Reliability Measurement

### P5.1 Test Scenarios

| Scenario | Description | Metric | Target |
|----------|-------------|--------|--------|
| Baseline (same room) | Test receiver and agent 2m apart | Round-trip time | <500ms |
| Through walls | 50m, through 2-3 walls | RTT, packet loss | <2s, <10% loss |
| Through cellars | 100m, through multiple buildings | RTT, packet loss | <5s, <20% loss |
| Burst test | Agent sends 10 messages in 10s | Delivery ratio | >90% |
| Duty cycle compliance | Continuous operation 1h | Message count vs 1% limit | ≤36 messages/h |

### P5.2 Measurement Method

1. Agent sends timestamped message with sequence number
2. Test receiver records arrival time, sequence number, RSSI, SNR
3. Latency = arrival_time - send_time (assumes clocks roughly synced)
4. Packet loss = gaps in seq numbers over each 100-message window

### P5.3 Log Format

```
agent -> coord | seq=0042 | t_send=1715000000 | t_recv=1715000005 | latency=5000ms | RSSI=-78dBm | SNR=6dB
```

### P5.4 End-to-End Latency Budget

| Step | Time (LoRa SF7) | Time (LoRa SF12) |
|------|-----------------|------------------|
| Meter reading interval | 5000ms | 5000ms |
| SML parsing | 50ms | 50ms |
| Internal processing | 10ms | 10ms |
| LoRa TX (GridLimit, ~25 bytes) | ~100ms | ~1200ms |
| Air propagation | <1ms | <1ms |
| LoRa RX + decode | ~100ms | ~1200ms |
| Coordinator processing | 10ms | 10ms |
| **Total per reading cycle** | **~5270ms** | **~7470ms** |

At SF7, the neighborhood receives a fresh limit update every ~5s. At SF12, every ~7.5s. Either timescale is acceptable for grid limit enforcement (load changes on the order of minutes, not seconds).

> **Note:** Again, this GridLimit transmission is test-only. In Phase 1 production, no messages cross households — the limit lives locally on each agent.

---

## P6. Success Criteria

The prototype is a success when:

1. ✅ ESP32 reads a real German smart meter and outputs correct 1.8.0, 2.8.0, and 16.7.0 values
2. ✅ SML parsing validated against at least 2 brands (ISKRA + one other)
3. ✅ LoRa (or MQTT) reliably transmits the GridLimit message from agent to coordinator at ≥100m through buildings
4. ✅ Latency from meter reading to coordinator receipt is <10s at worst case
5. ✅ The prototype runs continuously for 24h without crash or data corruption

**Not yet validated by this prototype (next iteration):**
- Priority invariant and load shed order: wallbox → battery → heat pump (§2a, UC-04)
- Agent→EMS signaling: MQTT topics for OpenEMS/evcc/Home Assistant (Brainstorming §3.3)
- Grid limit enforcement state machine: MONITOR → WARN → SHED → RECOVERY
- Simple onboarding (FR-05): web UI or captive portal for limit configuration

**After success of both iterations:** Full protocol stack with the 7 message types (Brainstorming §4.1) and inter-household coordination (Phase 2).
