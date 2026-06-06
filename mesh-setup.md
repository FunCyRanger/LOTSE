# Mesh Setup — Heltec V3 Configuration

After completing [ha-setup.md](ha-setup.md) on the Home Assistant side, configure your Heltec V3 node.

## What you need

| Item | Notes |
|------|-------|
| Heltec V3 (ESP32-S3 + SX1262 868 MHz) | One per household |
| Tasmota-compatible IR reader | Reads smart meter via optical interface |
| USB-C cable + power supply | Existing phone charger works |

> **Flashing:** Use the [Meshtastic Web Flasher](https://flasher.meshtastic.org/) (no local tools needed). Select **Heltec V3**, flash the latest stable release. No custom firmware fork required.

## Node Configuration (Web UI)

After flashing, connect to the node's WiFi hotspot and open the Web UI (typically `http://192.168.42.1`).

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
| Primary (LongFast) | Default LoRa | ✅ Leave checked (mesh discovery) | ☐ Unchecked |
| `mqtt` (index 1) | All meter data | ✅ **Check this** | ✅ **Check this** |

Create a **new** channel with these settings:

| Setting | Value |
|---------|-------|
| Name | **`mqtt`** (exactly this, lowercase) |
| PSK | Default/random |
| Uplink Enabled | ✅ Check |
| Downlink Enabled | ✅ Check |

**Reboot the node** — channel changes don't take effect until reboot.

### Find Your Node Number

From Web UI → **About** page, note both:

| Identifier | Example | Used for |
|------------|---------|----------|
| Decimal Node Number | `2892010904` | `from` field in the sender automation |
| Hex Node ID | `!acaad598` | MQTT topic path for received messages |
| Region string | `EU_868` | Part of the MQTT topic |
