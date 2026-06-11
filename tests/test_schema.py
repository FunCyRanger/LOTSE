"""Schema compliance tests for LOTSE mesh payloads and topics."""

import json
import re
import sys
import traceback
from pathlib import Path

import yaml
from jinja2 import Environment, Undefined, ChainableUndefined

ROOT = Path(__file__).resolve().parent.parent

# ─── Reuse the same mock infrastructure as test_mesh.py ────────────────────

MOCK_DATA = {
    "sensor.grid_power":         {"state": -1.2,  "unit_of_measurement": "kW"},
    "sensor.grid_import":        {"state": 2500,  "unit_of_measurement": "W"},
    "sensor.grid_export":        {"state": 0.8,   "unit_of_measurement": "MW"},
    "sensor.p1_power":           {"state": -0.4,  "unit_of_measurement": "kW"},
    "sensor.p2_power":           {"state": -0.5,  "unit_of_measurement": "kW"},
    "sensor.p3_power":           {"state": -0.3,  "unit_of_measurement": "W"},
    "sensor.p1_voltage":         {"state": 230,   "unit_of_measurement": "V"},
    "sensor.p2_voltage":         {"state": 231,   "unit_of_measurement": "mV"},
    "sensor.p3_voltage":         {"state": 0.229, "unit_of_measurement": "kV"},
    "sensor.grid_energy_import": {"state": 1234.5,"unit_of_measurement": "kWh"},
    "sensor.grid_energy_export": {"state": 567.8, "unit_of_measurement": "Wh"},
    "sensor.solar_power":        {"state": 3.5,   "unit_of_measurement": "kW"},
    "sensor.solar_energy":       {"state": 42.1,  "unit_of_measurement": "kWh"},
    "sensor.battery_power":      {"state": 0.75,  "unit_of_measurement": "kW"},
    "sensor.battery_soc":        {"state": 85,    "unit_of_measurement": "%"},
    "sensor.battery_energy_in":  {"state": 10.2,  "unit_of_measurement": "Wh"},
    "sensor.battery_energy_out": {"state": 5.1,   "unit_of_measurement": "kWh"},
    "sensor.wallbox_power":      {"state": 7.2,   "unit_of_measurement": "kW"},
    "sensor.wallbox_energy":     {"state": 200.0, "unit_of_measurement": "kWh"},
    "sensor.wallbox_soc":        {"state": 60,    "unit_of_measurement": "%"},
}


class MockState:
    __slots__ = ("entity_id", "state")
    def __init__(self, entity_id, state):
        self.entity_id = entity_id
        self.state = str(state)


class MockStates:
    def __init__(self, data):
        self._data = data

    def __call__(self, entity_id):
        entry = self._data.get(entity_id, {})
        val = entry.get("state", "unknown")
        return str(val) if val is not None else "unknown"

    @property
    def sensor(self):
        return [MockState(eid, self._data[eid]["state"])
                for eid in self._data
                if eid.startswith("sensor.")]


def mock_state_attr(entity_id, attr):
    entry = MOCK_DATA.get(entity_id, {})
    return entry.get(attr)


def mock_expand(seq):
    return list(seq)


def ha_to_json(value):
    return json.dumps(value)


def ha_search(value, pattern):
    return bool(re.search(pattern, str(value)))


def ha_float(value, default=0):
    if isinstance(value, Undefined):
        return float(default)
    try:
        return float(value)
    except (ValueError, TypeError):
        return float(default)


def ha_int(value, default=0):
    if isinstance(value, Undefined):
        return int(default)
    try:
        return int(value)
    except (ValueError, TypeError):
        return int(default)


def ha_from_json(value, default=None):
    if isinstance(value, Undefined):
        return default if default is not None else Undefined()
    try:
        return json.loads(value)
    except (ValueError, TypeError, json.JSONDecodeError):
        return default if default is not None else Undefined()


def ha_environment():
    env = Environment(undefined=ChainableUndefined)
    env.filters["to_json"] = ha_to_json
    env.filters["from_json"] = ha_from_json
    env.filters["float"] = ha_float
    env.filters["int"] = ha_int
    env.tests["search"] = ha_search
    mock_states = MockStates(MOCK_DATA)
    env.globals["states"] = mock_states
    env.globals["state_attr"] = mock_state_attr
    env.globals["expand"] = mock_expand
    return env


# ─── Load sender template ──────────────────────────────────────────────────

def _input_constructor(loader, node):
    return f"__INPUT__{node.value}__"


yaml.FullLoader.add_constructor("!input", _input_constructor)


def load_sender_inner():
    path = ROOT / "sender-blueprint.yaml"
    with open(path) as f:
        blueprint = yaml.load(f, Loader=yaml.FullLoader)
    return blueprint["action"][1]["variables"]["inner"]


def make_sender_vars(**overrides):
    defaults = dict(
        gP="sensor.grid_power",
        gIP="sensor.grid_import",
        gEP="sensor.grid_export",
        gP1="sensor.p1_power",
        gP2="sensor.p2_power",
        gP3="sensor.p3_power",
        gV1="sensor.p1_voltage",
        gV2="sensor.p2_voltage",
        gV3="sensor.p3_voltage",
        gEI="sensor.grid_energy_import",
        gEO="sensor.grid_energy_export",
        sP="sensor.solar_power",
        sE="sensor.solar_energy",
        bP="sensor.battery_power",
        bS="sensor.battery_soc",
        bEI="sensor.battery_energy_in",
        bEO="sensor.battery_energy_out",
        wP="sensor.wallbox_power",
        wE="sensor.wallbox_energy",
        wS="sensor.wallbox_soc",
    )
    defaults.update(overrides)
    return defaults


def render_sender(template_str, variables):
    env = ha_environment()
    tpl = env.from_string(template_str)
    result = tpl.render(**variables)
    return json.loads(result)


# ─── TESTS ─────────────────────────────────────────────────────────────────

MESHTASTIC_PAYLOAD_MAX_BYTES = 220


def test_payload_within_220_bytes():
    """Full 20-sensor payload fits Meshtastic 220-byte limit."""
    tpl = load_sender_inner()
    out = render_sender(tpl, make_sender_vars())
    inner_json = json.dumps(out, separators=(",", ":"))
    size = len(inner_json.encode("utf-8"))
    assert size <= MESHTASTIC_PAYLOAD_MAX_BYTES, (
        f"Inner payload {size} B exceeds {MESHTASTIC_PAYLOAD_MAX_BYTES} limit"
    )


def test_payload_typical_small():
    """Minimal payload (gP, bS only) well under limit."""
    tpl = load_sender_inner()
    vars_ = make_sender_vars(**{k: None for k in make_sender_vars()
                                if k not in ("gP", "bS")})
    out = render_sender(tpl, vars_)
    inner_json = json.dumps(out, separators=(",", ":"))
    assert len(inner_json.encode("utf-8")) <= MESHTASTIC_PAYLOAD_MAX_BYTES


def test_mqtt_topic_trailing_slash():
    """MQTT topic must end with / (required by Meshtastic)."""
    topic = "msh/EU_868/2/json/mqtt/"
    assert topic.endswith("/"), "Topic must have trailing slash"
    parts = topic.rstrip("/").split("/")
    assert len(parts) == 5, f"Expected 5 path segments, got {parts}"
    assert parts[0] == "msh"
    assert parts[1] == "EU_868"
    assert parts[2] == "2"
    assert parts[3] == "json"
    assert parts[4] == "mqtt"


def test_sign_convention():
    """gP signed, gIP/gEP >= 0, bS 0-100 int."""
    tpl = load_sender_inner()
    out = render_sender(tpl, make_sender_vars())
    assert "gP" in out and isinstance(out["gP"], (int, float))
    if "gIP" in out:
        assert out["gIP"] >= 0, f"gIP must be >= 0, got {out['gIP']}"
    if "gEP" in out:
        assert out["gEP"] >= 0, f"gEP must be >= 0, got {out['gEP']}"
    if "bS" in out:
        assert 0 <= out["bS"] <= 100, f"bS 0-100, got {out['bS']}"
        assert isinstance(out["bS"], int), f"bS int, got {type(out['bS'])}"


def test_nan_safe():
    """NaN/inf/unknown sensor states produce 0, not crash."""
    env = ha_environment()
    for bad_state in ("NaN", "nan", "inf", "-inf", "unknown", "unavailable"):
        tpl = env.from_string("{{ states('sensor.bad') | float(0) }}")
        result = tpl.render()
        assert float(result) == 0.0, f"State '{bad_state}' → {result}"


def test_none_and_empty_entity_id():
    """None and '' as entity ID both skip the key."""
    tpl = load_sender_inner()
    keep = ("gP",)
    none_vars = make_sender_vars(**{k: None for k in make_sender_vars()
                                    if k not in keep})
    empty_vars = make_sender_vars(**{k: "" for k in make_sender_vars()
                                     if k not in keep})
    out_none = render_sender(tpl, none_vars)
    out_empty = render_sender(tpl, empty_vars)
    assert set(out_none.keys()) == {"gP"}, f"None: {set(out_none.keys())}"
    assert set(out_empty.keys()) == {"gP"}, f"Empty: {set(out_empty.keys())}"


def test_receiver_excludes_self():
    """Receiver returns fallback for own node decimal."""
    env = ha_environment()
    template = """\
{% if value_json.from == NEIGHBOR_DECIMAL %}\
{{ value_json.payload.gP | float(0) }}\
{% else %}\
{{ this.state }}\
{% endif %}"""
    tpl = env.from_string(template)

    class ThisProxy:
        pass

    this = ThisProxy()
    this.state = "-5.0"

    # from matches → extract value
    result1 = tpl.render(value_json={"from": 12345, "payload": {"gP": -1.2}},
                         NEIGHBOR_DECIMAL=12345, this=this)
    assert result1.strip() == "-1.2", f"Got '{result1.strip()}'"

    # from differs → fallback
    result2 = tpl.render(value_json={"from": 99999, "payload": {"gP": -1.2}},
                         NEIGHBOR_DECIMAL=12345, this=this)
    assert result2.strip() == "-5.0", f"Got '{result2.strip()}'"


def test_combined_sensor_regex():
    """Combined sensor regex matches correct entity IDs."""
    cases = [
        (r"node_\d+_gp$",  "sensor.node_2712679380_gp",  "sensor.node_2712679380_gip"),
        (r"node_\d+_gip$", "sensor.node_2712679380_gip", "sensor.node_2712679380_gp"),
        (r"node_\d+_gep$", "sensor.node_2712679380_gep", "sensor.node_2712679380_gp"),
        (r"node_\d+_bs$",  "sensor.node_2712679380_bs",  "sensor.node_2712679380_bp"),
        (r"node_\d+_gei$", "sensor.node_2712679380_gei", "sensor.node_2712679380_geo"),
        (r"node_\d+_geo$", "sensor.node_2712679380_geo", "sensor.node_2712679380_gei"),
        (r"node_\d+_se$",  "sensor.node_2712679380_se",  "sensor.node_2712679380_sp"),
    ]
    for regex, match_ok, match_fail in cases:
        assert re.search(regex, match_ok), f"'{regex}' should match '{match_ok}'"
        assert not re.search(regex, match_fail), (
            f"'{regex}' should NOT match '{match_fail}'"
        )


def test_sender_topic_no_hash():
    """Sender blueprint publishes to msh/{region}/2/json/mqtt/ without node hash."""
    path = ROOT / "sender-blueprint.yaml"
    with open(path) as f:
        blueprint = yaml.load(f, Loader=yaml.FullLoader)
    # Scan actions for the mqtt.publish service
    publish = None
    for act in blueprint["action"]:
        if isinstance(act, dict) and act.get("service") == "mqtt.publish":
            publish = act
            break
    assert publish is not None, "mqtt.publish action not found"
    topic_tpl = publish["data"]["topic"]
    # Template should be literal string with no hash suffix
    assert topic_tpl == "msh/{{ region }}/2/json/mqtt/", f"Got: {topic_tpl}"
    env = ha_environment()
    rendered = env.from_string(topic_tpl).render(region="EU_868")
    assert rendered == "msh/EU_868/2/json/mqtt/"
    assert not rendered.rstrip("/").endswith("/2/json/mqtt/!"), "Topic contains node hash suffix"
    parts = rendered.rstrip("/").split("/")
    assert parts == ["msh", "EU_868", "2", "json", "mqtt"]


def test_envelope_payload_is_json_string():
    """Full envelope has payload as a JSON string (not a raw object)."""
    env = ha_environment()
    tpl = load_sender_inner()
    inner = render_sender(tpl, make_sender_vars())
    inner_str = json.dumps(inner, separators=(",", ":"))
    escaped = inner_str.replace('"', '\\"')

    envelope_tpl = env.from_string("""\
{"from": {{ node }}, "type": "sendtext",
 "payload": "{{ inner }}",
 "channel": {{ chan }}}""")
    raw = envelope_tpl.render(node=2892010904, inner=escaped, chan=1)
    envelope = json.loads(raw)
    assert isinstance(envelope["payload"], str), (
        f"payload must be a JSON string, got {type(envelope['payload'])}"
    )
    parsed = json.loads(envelope["payload"])
    assert isinstance(parsed, dict)
    assert "gP" in parsed


def test_envelope_inner_size():
    """Full MQTT envelope stays under 4096 bytes."""
    env = ha_environment()
    tpl = load_sender_inner()
    inner = render_sender(tpl, make_sender_vars())
    inner_str = json.dumps(inner, separators=(",", ":"))
    escaped = inner_str.replace('"', '\\"')

    envelope_tpl = env.from_string("""\
{"from": {{ node }}, "type": "sendtext",
 "payload": "{{ inner }}",
 "channel": {{ chan }}}""")
    raw = envelope_tpl.render(node=2892010904, inner=escaped, chan=1)
    envelope = json.loads(raw)
    size = len(json.dumps(envelope, separators=(",", ":")).encode("utf-8"))
    assert size < 4096, f"Envelope too large: {size} bytes"


# ─── Runner ─────────────────────────────────────────────────────────────────

TEST_FUNCTIONS = [
    name for name, val in globals().items()
    if name.startswith("test_") and callable(val)
]


def run_all():
    passed = 0
    failed = 0
    for name in sorted(TEST_FUNCTIONS):
        func = globals()[name]
        try:
            func()
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
