# Prototype Build Plan

**Purpose:** Prove the LoRa-to-WiFi data bridge: IR sensor → SoftAP HTTP → Heltec V3 (ingress) → LoRa mesh → Heltec V3 (egress) → Home Assistant.
**Based on:** Phase 1 architecture in Brainstorming.md §1.

---

## P1. Hardware & Software

### P1.1 Bill of Materials

| Item | Part | Est. cost |
|------|------|-----------|
| Ingress node | Heltec V3 (ESP32-S3 + SX1262 868 MHz) | €22-28 |
| Egress node | Heltec V3 (ESP32-S3 + SX1262 868 MHz) | €22-28 |
| IR sensor | Tasmota-compatible IR reader (e.g., WattWächter TTL) | €15-25 |
| Power supply | USB-C 5V (existing phone charger) | €0 |
| **Total** | | **€59-81** |

### P1.2 Software Stack

| Layer | Component |
|-------|-----------|
| Framework | PlatformIO + Arduino ESP32 core (`espressif32` platform) |
| LoRa mesh | Meshtastic v2.7.9 (clean fork at `meshtastic-fork-clean/`) |
| Ingress | SoftAP HTTP `POST /api/v1/meter` → LoRa forwarder |
| Egress | LoRa RX → WiFi station → MQTT or REST to Home Assistant |
| Sensor IF | Tasmota IR sensor → HTTP POST over WiFi (SoftAP) |

**Approach:** Add an HTTP endpoint to Meshtastic firmware (~50 lines) that accepts IR sensor JSON payloads and re-broadcasts them over the LoRa mesh. The egress node listens for specific LoRa packets and publishes to Home Assistant.

---

## P2. Build & Flash

```bash
cd /home/felix/LOTSE/meshtastic-fork-clean
pio run -e heltec-v3
pio run -e heltec-v3 -t upload --upload-port /dev/ttyUSB0
pio device monitor -p /dev/ttyUSB0 -b 115200
```

---

## P3. Test Procedure

1. **Power on** the ingress Heltec V3 — SoftAP appears (SSID begins with `LEM-`).
2. **Connect** to SoftAP from a laptop or Tasmota sensor (DHCP assigns 192.168.4.x).
3. **Send test data:**
   ```bash
   curl -X POST http://192.168.4.1/api/v1/meter \
     -H "Content-Type: application/json" \
     -d '{"power_w": 1234, "import_kwh": 50000, "export_kwh": 1000}'
   ```
4. **Verify** the egress node receives the LoRa packet and logs it.
5. **Two-node test**: position both nodes at least 10m apart, verify bidirectional LoRa.
6. **Home Assistant test**: configure egress WiFi station mode, verify MQTT/REST delivery.

---

## P4. Success Criteria

1. ✅ Ingress serves HTTP POST endpoint on SoftAP (192.168.4.1).
2. ✅ Payload forwarded over LoRa mesh to egress node.
3. ✅ Egress publishes to Home Assistant via MQTT or REST.
4. ✅ End-to-end latency < 5s.
5. ✅ 24h continuous operation without crash.

---

## P5. Meshtastic Fork Status

The prototype is based on Meshtastic v2.7.9 (clean fork at `meshtastic-fork-clean/`). Build blockers (BLE, Ethernet, nRF52 platform code) are documented in `AGENTS.md`. Once resolved, the HTTP endpoint handler is a small addition to `src/mesh/http/ContentHandler.cpp`.

**Historical note:** An earlier Phase 1 attempt used a LilyGO T3-S3 with a custom Meshtastic fork in `meshtastic-fork/` (branch `develop`). That fork is deprecated but kept for reference.
