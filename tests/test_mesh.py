#!/usr/bin/env python3
"""End-to-end template tests for LOTSE mesh sender → receiver flow."""

import json
import re
import sys
import traceback
from pathlib import Path

import yaml
from jinja2 import (
    Environment,
    Undefined,
    ChainableUndefined,
)

ROOT = Path(__file__).resolve().parent.parent

# ─── Mock HA sensor data ───────────────────────────────────────────────────

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
    "sensor.custom_power":       {"state": 42,    "unit_of_measurement": "custom_unit"},
    "sensor.unavailable_sensor": {"state": "unavailable", "unit_of_measurement": None},
    "sensor.nan_sensor":          {"state": "NaN", "unit_of_measurement": "kW"},
    "sensor.big_power":           {"state": 5000, "unit_of_measurement": "kW"},
    "sensor.negative_kwh":        {"state": -50, "unit_of_measurement": "kWh"},
    "sensor.bs_over_100":         {"state": 150, "unit_of_measurement": "%"},
    "sensor.kwh_in_power_slot":   {"state": 12345, "unit_of_measurement": "kWh"},
}


# ─── HA mock objects ───────────────────────────────────────────────────────

class MockState:
    __slots__ = ("entity_id", "state")
    def __init__(self, entity_id, state):
        self.entity_id = entity_id
        self.state = str(state)


class MockStates:
    """Mocks HA's callable+namespace `states` object."""

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


# ─── Custom Jinja filters/tests that HA provides ───────────────────────────

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
    """Parse a JSON string; return Undefined on failure.

    Supports the HA pattern ``| from_json(default)`` where ``default``
    is returned (or Undefined if omitted) when parsing fails.
    """
    if isinstance(value, Undefined):
        return default if default is not None else Undefined()
    try:
        return json.loads(value)
    except (ValueError, TypeError, json.JSONDecodeError):
        return default if default is not None else Undefined()


# ─── Create HA-like Jinja environment ─────────────────────────────────────

def ha_environment():
    """Return a Jinja2 environment mimicking HA's template engine."""
    env = Environment(
        undefined=ChainableUndefined,
        extensions=[],
    )
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


def load_sender_template():
    path = ROOT / "sender-blueprint.yaml"
    with open(path) as f:
        blueprint = yaml.load(f, Loader=yaml.FullLoader)
    # Envelope template is inside choose[1] (measurement path)
    raw = blueprint["action"][1]["choose"][1]["sequence"][0]["variables"]["envelope"]
    return raw


# ─── Render helpers ────────────────────────────────────────────────────────

def render_sender(template_str, variables):
    """Render the sender's envelope template with mocked HA globals.

    The template produces a full Meshtastic envelope JSON via
    ``{{ outer_env | to_json }}``.  Single ``json.loads`` unwraps the envelope;
    a second one extracts the inner LOTSE payload.
    """
    env = ha_environment()
    tpl = env.from_string(template_str)
    result = tpl.render(**variables)
    envelope = json.loads(result)
    return json.loads(envelope["payload"])


def make_sender_vars(**overrides):
    """Build entity-id variables dict (all sensors populated by default)."""
    defaults = dict(
        node="2896876952",
        region="eu868",
        channel_input=1,
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


# ─── Receiver value template helpers ──────────────────────────────────────

RECEIVER_TEMPLATE = """\
{% if value_json.from == NEIGHBOR_DECIMAL %}\
{{ value_json.payload.KEY | FILTER }}\
{% else %}\
{{ this.state }}\
{% endif %}"""


def render_receiver(mqtt_payload, neighbor_decimal, key, filter_="float(0)",
                    this_state="0"):
    """Render a receiver value_template for a single sensor.

    ``mqtt_payload`` should be a dict with ``payload`` as an inline JSON
    object (matching what Meshtastic publishes on the receive side).
    """
    env = ha_environment()
    tpl_str = RECEIVER_TEMPLATE.replace("KEY", key).replace("FILTER", filter_)
    tpl = env.from_string(tpl_str)

    class ThisProxy:
        def __init__(self):
            self.state = this_state

    result = tpl.render(
        value_json=mqtt_payload,
        NEIGHBOR_DECIMAL=neighbor_decimal,
        this=ThisProxy(),
    )
    return result.strip()


UNIVERSAL_TEMPLATE = """\
{% if value_json.from == NEIGHBOR_DECIMAL %}\
{% set p = value_json.payload if value_json.payload is mapping\
           else value_json.payload | from_json({}) %}\
{{ p.KEY | FILTER }}\
{% else %}\
{{ this.state }}\
{% endif %}"""


def render_receiver_universal(mqtt_payload, neighbor_decimal, key,
                              filter_="float(0)", this_state="0"):
    """Render the universal receiver template that handles both dict and string
    payloads (matching the updated auto-discovery value_template)."""
    env = ha_environment()
    tpl_str = UNIVERSAL_TEMPLATE.replace("KEY", key).replace("FILTER", filter_)
    tpl = env.from_string(tpl_str)

    class ThisProxy:
        def __init__(self):
            self.state = this_state

    result = tpl.render(
        value_json=mqtt_payload,
        NEIGHBOR_DECIMAL=neighbor_decimal,
        this=ThisProxy(),
    )
    return result.strip()


# ─── Combined sensor helper ────────────────────────────────────────────────

def render_combined(template_str, mock_entity_ids):
    """Render a combined sensor template (sum/average)."""
    env = ha_environment()
    env.globals["expand"] = mock_expand

    class MockNamespace:
        @property
        def sensor(self):
            return [MockState(eid, MOCK_DATA.get(eid, {}).get("state", "unknown"))
                    for eid in mock_entity_ids]

    env.globals["states"] = MockNamespace()
    tpl = env.from_string(template_str)
    result = tpl.render()
    return result.strip()


# ═══════════════════════════════════════════════════════════════════════════
# TESTS — SENDER
# ═══════════════════════════════════════════════════════════════════════════

def test_sender_all_sensors():
    """All 20 sensors populated → correct payload keys and types."""
    tpl = load_sender_template()
    out = render_sender(tpl, make_sender_vars())
    assert len(out) == 20, f"Expected 20 keys, got {len(out)}: {list(out.keys())}"
    assert out["gP"] == -1.2
    assert out["bS"] == 85
    assert isinstance(out["bS"], int), f"bS should be int, got {type(out['bS'])}"


def test_sender_partial():
    """Only gP + bS provided → only those two keys in payload."""
    tpl = load_sender_template()
    vars_ = make_sender_vars(gIP=None, gEP=None, gP1=None, gP2=None, gP3=None,
                             gV1=None, gV2=None, gV3=None, gEI=None, gEO=None,
                             sP=None, sE=None, bP=None, bEI=None, bEO=None,
                             wP=None, wE=None, wS=None)
    out = render_sender(tpl, vars_)
    assert set(out.keys()) == {"gP", "bS"}, f"Got {set(out.keys())}"


def test_sender_all_none():
    """No sensors provided → empty payload dict."""
    tpl = load_sender_template()
    vars_ = make_sender_vars(**{k: None for k in make_sender_vars()})
    out = render_sender(tpl, vars_)
    assert out == {}, f"Expected empty dict, got {out}"


def test_sender_unit_w_to_kw():
    """2500 W → 2.5 kW."""
    tpl = load_sender_template()
    out = render_sender(tpl, make_sender_vars(gIP="sensor.grid_import"))
    assert out["gIP"] == 2.5, f"Expected 2.5, got {out['gIP']}"


def test_sender_unit_mw_to_kw():
    """0.8 MW → 800 kW, clamped to 500 kW max."""
    tpl = load_sender_template()
    out = render_sender(tpl, make_sender_vars(gEP="sensor.grid_export"))
    assert out["gEP"] == 500.0, f"Expected 500.0, got {out['gEP']}"


def test_sender_unit_wh_to_kwh():
    """567.8 Wh → 0.5678 → round(2) → 0.57 kWh."""
    tpl = load_sender_template()
    out = render_sender(tpl, make_sender_vars(gEO="sensor.grid_energy_export"))
    assert out["gEO"] == 0.57, f"Expected 0.57, got {out['gEO']}"


def test_sender_unit_mv_to_v():
    """231 mV → 0.231 V → round(1) → 0.2 V."""
    tpl = load_sender_template()
    out = render_sender(tpl, make_sender_vars(gV2="sensor.p2_voltage"))
    assert out["gV2"] == 0.2, f"Expected 0.2, got {out['gV2']}"


def test_sender_unit_kv_to_v():
    """0.229 kV → 229 V."""
    tpl = load_sender_template()
    out = render_sender(tpl, make_sender_vars(gV3="sensor.p3_voltage"))
    assert abs(out["gV3"] - 229.0) < 1.0, f"Expected ~229.0, got {out['gV3']}"


def test_sender_unit_unknown_passthrough():
    """Unknown unit → factor 1 (pass through)."""
    tpl = load_sender_template()
    vars_ = make_sender_vars(gP="sensor.custom_power",
                             **{k: None for k in make_sender_vars() if k != "gP"})
    out = render_sender(tpl, vars_)
    assert out["gP"] == 42.0, f"Expected 42.0, got {out['gP']}"





def test_sender_negative_preserved():
    """Negative gP preserved."""
    tpl = load_sender_template()
    out = render_sender(tpl, make_sender_vars())
    assert out["gP"] < 0


def test_sender_mixed_units():
    """3 phases with kW/W → all converted to kW then rounded."""
    tpl = load_sender_template()
    out = render_sender(tpl, make_sender_vars(
        gP1="sensor.p1_power", gP2="sensor.p2_power", gP3="sensor.p3_power"))
    assert out["gP1"] == -0.4
    assert out["gP2"] == -0.5
    # -0.3 W → -0.0003 kW → round(2) → -0.0
    assert out["gP3"] == -0.0 or out["gP3"] == 0.0


def test_sender_unavailable_omits_key():
    """Unavailable sensor → key omitted from payload."""
    tpl = load_sender_template()
    vars_ = make_sender_vars(gP="sensor.unavailable_sensor",
                             **{k: None for k in make_sender_vars() if k != "gP"})
    out = render_sender(tpl, vars_)
    assert "gP" not in out


def test_sender_nan_omits_key():
    """NaN state → key omitted."""
    tpl = load_sender_template()
    vars_ = make_sender_vars(gP="sensor.nan_sensor",
                             **{k: None for k in make_sender_vars() if k != "gP"})
    out = render_sender(tpl, vars_)
    assert "gP" not in out


def test_sender_power_clamped():
    """5000 kW clamped to 500 kW."""
    tpl = load_sender_template()
    vars_ = make_sender_vars(gP="sensor.big_power",
                             **{k: None for k in make_sender_vars() if k != "gP"})
    out = render_sender(tpl, vars_)
    assert out["gP"] == 500.0, f"Expected 500.0, got {out['gP']}"


def test_sender_bs_clamped():
    """bS = 150 clamped to 100."""
    tpl = load_sender_template()
    vars_ = make_sender_vars(bS="sensor.bs_over_100",
                             **{k: None for k in make_sender_vars() if k != "bS"})
    out = render_sender(tpl, vars_)
    assert out["bS"] == 100, f"Expected 100, got {out['bS']}"


def test_sender_energy_negative_clamped():
    """Negative energy clamped to 0."""
    tpl = load_sender_template()
    vars_ = make_sender_vars(gEI="sensor.negative_kwh",
                             **{k: None for k in make_sender_vars() if k != "gEI"})
    out = render_sender(tpl, vars_)
    assert out["gEI"] == 0.0, f"Expected 0.0, got {out['gEI']}"


def test_sender_unit_mismatch_omitted():
    """kWh sensor in kW slot → key omitted."""
    tpl = load_sender_template()
    vars_ = make_sender_vars(gP="sensor.kwh_in_power_slot",
                             **{k: None for k in make_sender_vars() if k != "gP"})
    out = render_sender(tpl, vars_)
    assert "gP" not in out, f"gP should be omitted, got {out.get('gP')}"


def test_sender_all_unavailable():
    """All sensors offline → empty payload dict."""
    tpl = load_sender_template()
    vars_ = make_sender_vars(**{k: "sensor.unavailable_sensor" for k in make_sender_vars()})
    out = render_sender(tpl, vars_)
    assert out == {}, f"Expected empty dict, got {out}"


# ═══════════════════════════════════════════════════════════════════════════
# TESTS — RECEIVER
# ═══════════════════════════════════════════════════════════════════════════

def test_receiver_match():
    """from matches → sensor value extracted."""
    p = {"from": 2712679380, "payload": {"gP": -1.2, "bS": 85}}
    r = render_receiver(p, 2712679380, "gP", "float(0)")
    assert float(r) == -1.2, f"Expected -1.2, got {r}"


def test_receiver_mismatch():
    """from doesn't match → fallback state."""
    p = {"from": 999, "payload": {"gP": -1.2}}
    r = render_receiver(p, 2712679380, "gP", "float(0)", this_state="-5.0")
    assert r == "-5.0", f"Expected '-5.0', got {r}"


def test_receiver_int_filter():
    """bS via |int(0) → integer."""
    p = {"from": 2712679380, "payload": {"bS": 85}}
    r = render_receiver(p, 2712679380, "bS", "int(0)")
    assert int(r) == 85, f"Expected 85, got {r}"


def test_receiver_missing_key():
    """Payload missing the key → float(0) returns 0."""
    p = {"from": 2712679380, "payload": {"gP": -1.2}}
    r = render_receiver(p, 2712679380, "nonexistent", "float(0)")
    assert float(r) == 0.0, f"Expected 0.0, got {r}"


def test_receiver_voltage_rounding():
    """gV1 with 1 decimal preserved."""
    p = {"from": 2712679380, "payload": {"gV1": 230.456}}
    r = render_receiver(p, 2712679380, "gV1", "float(0)")
    assert float(r) == 230.456


# ═══════════════════════════════════════════════════════════════════════════
# TESTS — UNIVERSAL RECEIVER (handles both dict and string payloads)
# ═══════════════════════════════════════════════════════════════════════════

def test_universal_receiver_dict_payload():
    """"Universal template: dict payload → value extracted."""
    p = {"from": 2712679380, "payload": {"gP": -1.2, "bS": 85}}
    r = render_receiver_universal(p, 2712679380, "gP", "float(0)")
    assert float(r) == -1.2, f"Expected -1.2, got {r}"


def test_universal_receiver_string_payload():
    """"Universal template: string payload → parsed and value extracted."""
    p = {"from": 2712679380, "payload": '{"gP": -1.2, "bS": 85}'}
    r = render_receiver_universal(p, 2712679380, "gP", "float(0)")
    assert float(r) == -1.2, f"Expected -1.2, got {r}"


def test_universal_receiver_dict_mismatch():
    """"Universal template: dict payload, from mismatch → fallback."""
    p = {"from": 999, "payload": {"gP": -1.2}}
    r = render_receiver_universal(p, 2712679380, "gP", "float(0)", this_state="-5.0")
    assert r == "-5.0", f"Expected '-5.0', got {r}"


def test_universal_receiver_string_mismatch():
    """"Universal template: string payload, from mismatch → fallback."""
    p = {"from": 999, "payload": '{"gP": -1.2}'}
    r = render_receiver_universal(p, 2712679380, "gP", "float(0)", this_state="-5.0")
    assert r == "-5.0", f"Expected '-5.0', got {r}"


def test_universal_receiver_missing_key():
    """"Universal template: payload missing the key → default 0."""
    p = {"from": 2712679380, "payload": {"gP": -1.2}}
    r = render_receiver_universal(p, 2712679380, "nonexistent", "float(0)")
    assert float(r) == 0.0, f"Expected 0.0, got {r}"


def test_universal_receiver_int_filter_dict():
    """"Universal template: bS via |int(0) with dict payload."""
    p = {"from": 2712679380, "payload": {"bS": 85}}
    r = render_receiver_universal(p, 2712679380, "bS", "int(0)")
    assert int(r) == 85, f"Expected 85, got {r}"


def test_universal_receiver_int_filter_string():
    """"Universal template: bS via |int(0) with string payload."""
    p = {"from": 2712679380, "payload": '{"bS": 85}'}
    r = render_receiver_universal(p, 2712679380, "bS", "int(0)")
    assert int(r) == 85, f"Expected 85, got {r}"


# ═══════════════════════════════════════════════════════════════════════════
# TESTS — ROUNDTRIP
# ═══════════════════════════════════════════════════════════════════════════

def test_roundtrip():
    """Send payload → receive-parsed → correct values."""
    tpl = load_sender_template()
    out = render_sender(tpl, make_sender_vars())
    msg = {"from": 12345, "payload": out}
    for key in ("gP", "gIP", "gEP", "bS"):
        flt = "int(0)" if key == "bS" else "float(0)"
        r = render_receiver(msg, 12345, key, flt)
        expected = out[key]
        if key == "bS":
            assert int(r) == expected, f"Roundtrip {key}: {r} != {expected}"
        else:
            assert abs(float(r) - float(expected)) < 0.01, f"Roundtrip {key}: {r} != {expected}"


# ═══════════════════════════════════════════════════════════════════════════
# TESTS — COMBINED SENSORS  (mesh_combined.yaml)
# ═══════════════════════════════════════════════════════════════════════════

COMBINED_GP = """\
{% set entities = expand(states.sensor)\
 | selectattr('entity_id', 'search', 'node_\\\\d+_gp$') | list %}\
{{ entities | map(attribute='state') | map('float', 0) | sum | round(2) }}"""

COMBINED_SOC = """\
{% set entities = expand(states.sensor)\
 | selectattr('entity_id', 'search', 'node_\\\\d+_bs$') | list %}\
{% set vals = entities | map(attribute='state') | map('int', 0) | list %}\
{{ (vals | sum / vals | length) | round(0) if vals | length > 0 else 0 }}"""


def test_combined_gp_sum():
    """gp sum: 3 neighbors → -0.5 kW."""
    ids = ["sensor.node_1_gp", "sensor.node_2_gp", "sensor.node_3_gp"]
    for eid, v in zip(ids, [-1.2, -0.8, 2.5]):
        MOCK_DATA[eid] = {"state": v, "unit_of_measurement": "kW"}
    r = render_combined(COMBINED_GP, ids)
    for eid in ids:
        del MOCK_DATA[eid]
    assert abs(float(r) - 0.5) < 0.01, f"Expected 0.5, got {r}"


def test_combined_gp_empty():
    """gp sum: no matching entities → 0."""
    r = render_combined(COMBINED_GP, [])
    assert float(r) == 0.0, f"Expected 0.0, got {r}"


def test_combined_soc_avg():
    """bs avg: 3 neighbors → 85%."""
    ids = ["sensor.node_1_bs", "sensor.node_2_bs", "sensor.node_3_bs"]
    for eid, v in zip(ids, [80, 90, 85]):
        MOCK_DATA[eid] = {"state": v, "unit_of_measurement": "%"}
    r = render_combined(COMBINED_SOC, ids)
    for eid in ids:
        del MOCK_DATA[eid]
    assert float(r) == 85.0, f"Expected 85.0, got {r}"


def test_combined_soc_empty():
    """bs avg: no matching entities → 0."""
    r = render_combined(COMBINED_SOC, [])
    assert float(r) == 0.0, f"Expected 0.0, got {r}"


# ═══════════════════════════════════════════════════════════════════════════
# TESTS — AUTO‑DISCOVERY CONFIG JSON
# ═══════════════════════════════════════════════════════════════════════════

def load_discovery_template():
    """Load the first gP sensor's MQTT discovery config template from
    auto-discovery-automation.yaml and return it as a Jinja template string."""
    path = ROOT / "auto-discovery-automation.yaml"
    with open(path) as f:
        data = yaml.load(f, Loader=yaml.FullLoader)
    return data["action"][0]["then"][0]["data"]["payload"]


def test_discovery_valid_json():
    """Auto-discovery config renders to valid JSON."""
    env = ha_environment()
    tpl = env.from_string(load_discovery_template())
    raw = tpl.render(**{"from": 2712679380, "region": "EU_868", "sender": "!a1b2c3d4"})
    cfg = json.loads(raw)
    assert cfg["name"] == "Node 2712679380 gP"
    assert cfg["unit_of_measurement"] == "kW"
    assert cfg["unique_id"] == "mesh_2712679380_gp"
    assert isinstance(cfg["value_template"], str)
    assert "value_json.from" in cfg["value_template"]
    assert "gP" in cfg["value_template"]


def test_discovery_nested_template():
    """The value_template field in discovery config is itself valid Jinja."""
    env = ha_environment()
    tpl = env.from_string(load_discovery_template())
    raw = tpl.render(**{"from": 2712679380, "region": "EU_868", "sender": "!a1b2c3d4"})
    cfg = json.loads(raw)

    nested = env.from_string(cfg["value_template"])
    result = nested.render(value_json={
        "from": 2712679380,
        "payload": {"gP": -1.2},
    })
    assert float(result.strip()) == -1.2, f"Expected -1.2, got '{result.strip()}'"


# ═══════════════════════════════════════════════════════════════════════════
# TESTS — MESH ENVELOPE
# ═══════════════════════════════════════════════════════════════════════════

ENVELOPE_TPL = """\
{"from": {{ node }}, "type": "sendtext",
 "payload": "{{ inner_payload }}",
 "channel": 1}"""


def test_envelope_valid():
    """Envelope renders to valid JSON with correct fields."""
    env = ha_environment()
    inner = json.dumps({"gP": -1.2, "bS": 85})
    escaped = inner.replace('"', '\\"')
    raw = env.from_string(ENVELOPE_TPL).render(node=2892010904, inner_payload=escaped)
    envp = json.loads(raw)
    assert envp["from"] == 2892010904
    assert envp["type"] == "sendtext"
    assert envp["channel"] == 1
    assert json.loads(envp["payload"]) == {"gP": -1.2, "bS": 85}


def test_envelope_payload_roundtrip():
    """Envelope payload survives JSON-in-JSON escaping."""
    env = ha_environment()
    inner = json.dumps({"gP": -1.2, "gP1": -0.4, "bS": 85})
    escaped = inner.replace('"', '\\"')
    raw = env.from_string(ENVELOPE_TPL).render(node=2892010904, inner_payload=escaped)
    envp = json.loads(raw)
    assert isinstance(envp["payload"], str)
    assert json.loads(envp["payload"]) == {"gP": -1.2, "gP1": -0.4, "bS": 85}


# ═══════════════════════════════════════════════════════════════════════════
# RUNNER
# ═══════════════════════════════════════════════════════════════════════════

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
