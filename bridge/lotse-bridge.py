#!/usr/bin/env python3
"""
LOTSE MQTT Bridge — IR sensor data through Meshtastic LoRa to clean MQTT.

Ingress (sensor side):  Tasmota MQTT topic → Meshtastic downlink → LoRa TX
Egress  (HA side):      LoRa RX → Meshtastic uplink → Clean MQTT topic

Any MQTT client subscribes to the clean output topic — no regex, no HA addon.

Usage:
  # both ingress + egress (broker shared):
  export MQTT_BROKER=192.168.1.100
  export INGRESS_NODE_NUM=2892010904
  python3 lotse-bridge.py

  # ingress only (at sensor):
  python3 lotse-bridge.py --mode ingress --broker 192.168.1.100 --ingress-num 2892010904

  # egress only (at receiver):
  python3 lotse-bridge.py --mode egress --broker 192.168.1.100
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Any

import paho.mqtt.client as mqtt

log = logging.getLogger("lotse-bridge")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULTS = {
    "broker": "localhost",
    "port": 1883,
    "user": None,
    "password": None,
    "mode": "both",
    # ingress
    "tasmota_topic": "tele/tasmota_ir/SENSOR",
    "tasmota_field": "ENERGY.Power",
    "tasmota_unit": "W",
    # meshtastic downlink
    "region": "EU_868",
    "downlink_channel": "mqtt",
    "ingress_node_num": 0,
    # meshtastic uplink
    "egress_node_hex": "!00000000",
    # clean output
    "output_topic": "lotse/meter/power",
    # loRa payload struct
    "lora_payload_key": "p",
}


def env_or_default(key: str, default: Any) -> Any:
    env_key = key.upper()
    val = os.environ.get(env_key)
    if val is not None:
        if isinstance(default, int):
            return int(val)
        if isinstance(default, float):
            return float(val)
        return val
    return default


# ---------------------------------------------------------------------------
# Deep JSON field access via dotted path
# ---------------------------------------------------------------------------


def deep_get(obj: dict, path: str) -> Any:
    parts = path.split(".")
    for p in parts:
        if isinstance(obj, dict) and p in obj:
            obj = obj[p]
        else:
            return None
    return obj


# ---------------------------------------------------------------------------
# LoRa payload encoding (compact, fits Meshtastic text limit)
# ---------------------------------------------------------------------------


def encode_lora(power_w: float, unit: str, key: str) -> str:
    return json.dumps({key: round(power_w, 1)}, separators=(",", ":"))


def decode_lora(text: str, key: str) -> dict[str, Any]:
    raw: dict[str, Any] = json.loads(text)
    if key not in raw:
        raise ValueError(f"key '{key}' not in LoRa payload")
    return raw


# ---------------------------------------------------------------------------
# Meshtastic topic helpers
# ---------------------------------------------------------------------------


def downlink_topic(region: str, channel: str) -> str:
    return f"msh/{region}/2/json/{channel}/"


def uplink_topic(region: str, node_hex: str) -> str:
    return f"msh/{region}/2/json/LongFast/{node_hex}"


# ---------------------------------------------------------------------------
# The bridge
# ---------------------------------------------------------------------------


class LotseBridge:
    def __init__(self, cfg: dict[str, Any]) -> None:
        self.cfg = cfg
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

        if cfg["user"]:
            self.client.username_pw_set(cfg["user"], cfg["password"])

        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

        self._shutdown = False

    # -- lifecycle ---------------------------------------------------------

    def run(self) -> None:
        signal.signal(signal.SIGINT, self._signal)
        signal.signal(signal.SIGTERM, self._signal)

        self.client.connect_async(self.cfg["broker"], self.cfg["port"], 60)
        self.client.loop_start()

        log.info(
            "lotse-bridge started  mode=%s  broker=%s:%s",
            self.cfg["mode"],
            self.cfg["broker"],
            self.cfg["port"],
        )

        while not self._shutdown:
            time.sleep(1)

        self._cleanup()

    # -- callbacks ---------------------------------------------------------

    def _on_connect(self, client: mqtt.Client, userdata: Any, flags: dict, rc: int, properties: Any = None) -> None:
        if rc != 0:
            log.error("MQTT connect failed  rc=%s", rc)
            return
        log.info("MQTT connected")

        mode = self.cfg["mode"]
        if mode in ("ingress", "both"):
            topic = self.cfg["tasmota_topic"]
            client.subscribe(topic, qos=1)
            log.info("Subscribed ingress: %s", topic)

        if mode in ("egress", "both"):
            topic = uplink_topic(self.cfg["region"], self.cfg["egress_node_hex"])
            client.subscribe(topic, qos=1)
            log.info("Subscribed egress:  %s", topic)

    def _on_message(self, client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
        try:
            payload_str = msg.payload.decode("utf-8")
            topic = msg.topic
        except Exception:
            return

        if topic == self.cfg["tasmota_topic"]:
            self._handle_tasmota(payload_str)
        elif topic.startswith(f"msh/{self.cfg['region']}"):
            self._handle_meshtastic_uplink(payload_str)
        else:
            log.debug("Ignored topic: %s", topic)

    def _on_disconnect(self, client: mqtt.Client, userdata: Any, rc: int, properties: Any = None) -> None:
        log.warning("MQTT disconnected  rc=%s  (will auto-reconnect)", rc)

    # -- handlers ----------------------------------------------------------

    def _handle_tasmota(self, payload_str: str) -> None:
        try:
            data: dict[str, Any] = json.loads(payload_str)
        except json.JSONDecodeError as e:
            log.warning("Tasmota JSON parse error: %s", e)
            return

        value = deep_get(data, self.cfg["tasmota_field"])
        if value is None:
            log.debug("Field '%s' not in Tasmota payload", self.cfg["tasmota_field"])
            return

        try:
            power_w = float(value)
        except (ValueError, TypeError) as e:
            log.warning("Bad Tasmota value '%s': %s", value, e)
            return

        if power_w < 0:
            power_w = 0.0

        # Build Meshtastic downlink JSON
        lora_text = encode_lora(power_w, self.cfg["tasmota_unit"], self.cfg["lora_payload_key"])
        downlink_payload = {
            "from": self.cfg["ingress_node_num"],
            "type": "sendtext",
            "payload": lora_text,
        }
        topic = downlink_topic(self.cfg["region"], self.cfg["downlink_channel"])
        self.client.publish(topic, json.dumps(downlink_payload, separators=(",", ":")), qos=1)
        log.info("Sent LoRa: %s W → %s", round(power_w, 1), topic)

    def _handle_meshtastic_uplink(self, payload_str: str) -> None:
        try:
            data: dict[str, Any] = json.loads(payload_str)
        except json.JSONDecodeError as e:
            log.warning("Uplink JSON parse error: %s", e)
            return

        if data.get("type") != "text":
            return

        text = data.get("payload", {}).get("text")
        if not text:
            log.debug("Uplink message has no text payload")
            return

        try:
            decoded = decode_lora(text, self.cfg["lora_payload_key"])
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            log.debug("Uplink text not in LoRa format (non-LOTSE message): %s", e)
            return

        raw_power = decoded[self.cfg["lora_payload_key"]]
        try:
            power_w = float(raw_power)
        except (ValueError, TypeError):
            return

        now = datetime.now(timezone.utc).timestamp()
        output = {
            "power_w": round(power_w, 1),
            "unit": self.cfg["tasmota_unit"],
            "timestamp": round(now, 3),
        }

        self.client.publish(self.cfg["output_topic"], json.dumps(output), qos=1, retain=True)
        log.info("Received LoRa: %s W → %s", round(power_w, 1), self.cfg["output_topic"])

    # -- shutdown ----------------------------------------------------------

    def _signal(self, signum: int, frame: Any) -> None:
        log.info("Signal %s received, shutting down", signum)
        self._shutdown = True

    def _cleanup(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()
        log.info("Disconnected")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_cfg() -> dict[str, Any]:
    epilog = (
        "All options also settable via env vars: MQTT_BROKER, MQTT_PORT, "
        "MQTT_USER, MQTT_PASS, TASMOTA_TOPIC, TASMOTA_FIELD, "
        "MESHTASTIC_REGION, INGRESS_NODE_NUM, EGRESS_NODE_HEX, OUTPUT_TOPIC, "
        "LORA_PAYLOAD_KEY"
    )

    parser = argparse.ArgumentParser(
        description="LOTSE MQTT Bridge — Tasmota IR → Meshtastic LoRa → Clean MQTT",
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--mode", choices=["ingress", "egress", "both"], default=env_or_default("mode", "both"))
    parser.add_argument("--broker", default=env_or_default("broker", DEFAULTS["broker"]))
    parser.add_argument("--port", type=int, default=env_or_default("port", DEFAULTS["port"]))
    parser.add_argument("--user", default=env_or_default("user", DEFAULTS["user"]))
    parser.add_argument("--password", default=env_or_default("password", DEFAULTS["password"]))
    parser.add_argument("--tasmota-topic", default=env_or_default("tasmota_topic", DEFAULTS["tasmota_topic"]))
    parser.add_argument("--tasmota-field", default=env_or_default("tasmota_field", DEFAULTS["tasmota_field"]))
    parser.add_argument("--region", default=env_or_default("region", DEFAULTS["region"]))
    parser.add_argument("--downlink-channel", default=env_or_default("downlink_channel", DEFAULTS["downlink_channel"]))
    parser.add_argument("--ingress-num", type=int, default=env_or_default("ingress_node_num", DEFAULTS["ingress_node_num"]))
    parser.add_argument("--egress-hex", default=env_or_default("egress_node_hex", DEFAULTS["egress_node_hex"]))
    parser.add_argument("--output-topic", default=env_or_default("output_topic", DEFAULTS["output_topic"]))
    parser.add_argument("--lora-key", default=env_or_default("lora_payload_key", DEFAULTS["lora_payload_key"]))
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    cfg = {
        "mode": args.mode,
        "broker": args.broker,
        "port": args.port,
        "user": args.user,
        "password": args.password,
        "tasmota_topic": args.tasmota_topic,
        "tasmota_field": args.tasmota_field,
        "tasmota_unit": DEFAULTS["tasmota_unit"],
        "region": args.region,
        "downlink_channel": args.downlink_channel,
        "ingress_node_num": args.ingress_num,
        "egress_node_hex": args.egress_hex,
        "output_topic": args.output_topic,
        "lora_payload_key": args.lora_key,
    }

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )

    if cfg["mode"] in ("ingress", "both") and cfg["ingress_node_num"] == 0:
        log.warning("INGRESS_NODE_NUM is 0 — Meshtastic will reject the downlink")

    return cfg


def main() -> None:
    cfg = build_cfg()
    bridge = LotseBridge(cfg)
    try:
        bridge.run()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
