"""End-to-end MQTT roundtrip test for LOTSE message format.

Requires Docker (spawns eclipse-mosquitto).  Auto-skipped if Docker is
unavailable or paho-mqtt is not installed.
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import time
import traceback

MESHTASTIC_PAYLOAD_MAX_BYTES = 220

# ─── Detect availability ───────────────────────────────────────────────────

SKIP_REASON = None

if shutil.which("docker") is None:
    SKIP_REASON = "docker not found in PATH"
else:
    try:
        subprocess.run(["docker", "info"],
                       capture_output=True, timeout=10, check=True)
    except Exception:
        SKIP_REASON = "docker daemon not reachable"

try:
    import paho.mqtt.client as mqtt
except ImportError:
    SKIP_REASON = "paho-mqtt not installed"

MQTT_PORT = 1883
REGION = "EU_868"
NODE_DECIMAL = 2892010904
NODE_HEX = "!acaad598"


class MosquittoManager:
    """Context manager for a local Mosquitto container."""

    def __init__(self):
        self.container_id = None

    def __enter__(self):
        result = subprocess.run(
            ["docker", "run", "-d", "--rm",
             "-p", f"{MQTT_PORT}:1883",
             "eclipse-mosquitto"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to start Mosquitto: {result.stderr}")
        self.container_id = result.stdout.strip()
        # Wait for Mosquitto to accept connections
        for _ in range(10):
            try:
                import paho.mqtt.client as mqtt
                c = mqtt.Client()
                c.connect("localhost", MQTT_PORT, timeout=2)
                c.disconnect()
                return self
            except Exception:
                time.sleep(1)
        raise RuntimeError("Mosquitto did not become ready in time")

    def __exit__(self, *args):
        if self.container_id:
            subprocess.run(["docker", "stop", self.container_id],
                           capture_output=True, timeout=15)


def test_mqtt_publish_roundtrip():
    """Publish LOTSE message → subscribe → verify topic + payload."""
    container = None
    try:
        container = MosquittoManager()
        container.__enter__()
    except (RuntimeError, Exception) as e:
        print(f"  SKIP  test_mqtt_publish_roundtrip — {e}")
        return

    try:
        received = []

        def on_message(client, userdata, msg):
            received.append(msg)

        client = mqtt.Client()
        client.on_message = on_message
        client.connect("localhost", MQTT_PORT, timeout=5)
        client.subscribe(f"msh/{REGION}/2/json/mqtt/#", qos=0)
        client.loop_start()

        # Build the payload
        inner = json.dumps({"gP": -1.2, "gIP": 2.5, "gEP": 0.8,
                            "gP1": -0.4, "gP2": -0.5, "gP3": -0.3,
                            "bS": 85, "sP": 3.5}, separators=(",", ":"))
        assert len(inner.encode("utf-8")) <= MESHTASTIC_PAYLOAD_MAX_BYTES, (
            f"Inner payload too large: {len(inner.encode('utf-8'))} B"
        )

        envelope = json.dumps({
            "from": NODE_DECIMAL,
            "type": "sendtext",
            "payload": inner,
            "channel": 1,
        }, separators=(",", ":"))

        # Publish to the sender topic
        client.publish(f"msh/{REGION}/2/json/mqtt/", envelope, qos=0)
        time.sleep(2)

        assert len(received) > 0, "No messages received on msh/# wildcard"
        msg = received[0]
        assert msg.topic.startswith(f"msh/{REGION}/2/json/mqtt/")

        decoded = json.loads(msg.payload.decode("utf-8"))
        assert decoded["from"] == NODE_DECIMAL
        assert decoded["type"] == "sendtext"
        assert decoded["channel"] == 1
        # Inner payload survived JSON-in-JSON encoding
        parsed_inner = json.loads(decoded["payload"])
        assert parsed_inner["gP"] == -1.2
        assert parsed_inner["bS"] == 85
        print("  PASS  test_mqtt_publish_roundtrip")

    except Exception as e:
        print(f"  FAIL  test_mqtt_publish_roundtrip")
        traceback.print_exc()
        raise
    finally:
        client.loop_stop()
        client.disconnect()
        if container:
            container.__exit__()


def test_mqtt_topic_convention():
    """Sender and receiver topic formats follow documented convention."""
    sender_topic = f"msh/{REGION}/2/json/mqtt/"
    assert sender_topic.endswith("/"), "Sender topic must end with /"
    receiver_topic = f"msh/{REGION}/2/json/mqtt/{NODE_HEX}"
    assert receiver_topic.startswith(sender_topic)
    assert NODE_HEX in receiver_topic


# ─── Runner ─────────────────────────────────────────────────────────────────

TEST_FUNCTIONS = [
    name for name, val in globals().items()
    if name.startswith("test_") and callable(val)
]


def run_all():
    if SKIP_REASON:
        print(f"  SKIP  (all e2e tests) — {SKIP_REASON}")
        sys.exit(0)

    passed = 0
    failed = 0
    for name in sorted(TEST_FUNCTIONS):
        func = globals()[name]
        try:
            func()
            if name != "test_mqtt_publish_roundtrip":
                print(f"  PASS  {name}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {name}")
            traceback.print_exc()
            failed += 1
    total = passed + failed
    print(f"\n{'='*50}")
    print(f"  {passed}/{total} passed", end="")
    if failed:
        print(f", {failed} FAILED")
        sys.exit(1)
    else:
        print()
        sys.exit(0)


if __name__ == "__main__":
    run_all()
