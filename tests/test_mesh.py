#!/usr/bin/env python3
"""End-to-end template tests for LOTSE mesh sender → receiver flow."""

import json
import re
import sys
import traceback
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ─── Mock HA modules before importing custom_components ─────────────────
ha = MagicMock()
ha.util = MagicMock()
ha.util.dt = MagicMock()
ha.components = MagicMock()
ha.components.mqtt = MagicMock()
ha.components.sensor = MagicMock()
ha.config_entries = MagicMock()
ha.const = MagicMock()
ha.const.EVENT_HOMEASSISTANT_STARTED = "homeassistant_started"
ha.core = MagicMock()
ha.helpers = MagicMock()
ha.helpers.entity_registry = MagicMock()

for mod_name, obj in [
    ("homeassistant", ha),
    ("homeassistant.util", ha.util),
    ("homeassistant.util.dt", ha.util.dt),
    ("homeassistant.components", ha.components),
    ("homeassistant.components.mqtt", ha.components.mqtt),
    ("homeassistant.components.sensor", ha.components.sensor),
    ("homeassistant.config_entries", ha.config_entries),
    ("homeassistant.const", ha.const),
    ("homeassistant.core", ha.core),
    ("homeassistant.helpers", ha.helpers),
    ("homeassistant.helpers.entity_registry", ha.helpers.entity_registry),
    ("homeassistant.helpers.entity_platform", MagicMock()),
]:
    sys.modules[mod_name] = obj

# Mock dashboard submodule before __init__.py tries to import it
sys.modules["custom_components.lotse_forecast.dashboard"] = MagicMock()
sys.modules["custom_components.lotse_forecast.dashboard"].async_create_lovelace_dashboard = MagicMock()

# Now safe to import real modules
from custom_components.lotse_forecast import MeshData
from custom_components.lotse_forecast.const import COMBINED_KEY_META, NODE_KEY_META

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
    # Grid quality sensors
    "sensor.phase1_current":    {"state": 15.0,  "unit_of_measurement": "A"},
    "sensor.phase2_current":    {"state": 14.5,  "unit_of_measurement": "A"},
    "sensor.phase3_current":    {"state": 15.5,  "unit_of_measurement": "A"},
    "sensor.grid_frequency":    {"state": 50.02, "unit_of_measurement": "Hz"},
    "sensor.grid_power_factor": {"state": 96,    "unit_of_measurement": "%"},
    "sensor.reactive_power":     {"state": 200,   "unit_of_measurement": "VAr"},
    "sensor.reactive_power_l1":  {"state": 70,    "unit_of_measurement": "VAr"},
    "sensor.reactive_power_l2":  {"state": 65,    "unit_of_measurement": "VAr"},
    "sensor.reactive_power_l3":  {"state": 65,    "unit_of_measurement": "VAr"},
    "sensor.apparent_power":     {"state": 350,   "unit_of_measurement": "VA"},
    "sensor.apparent_power_l1":  {"state": 120,   "unit_of_measurement": "VA"},
    "sensor.apparent_power_l2":  {"state": 115,   "unit_of_measurement": "VA"},
    "sensor.apparent_power_l3":  {"state": 115,   "unit_of_measurement": "VA"},
}


# ─── HA mock objects ───────────────────────────────────────────────────────

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
    if isinstance(value, Undefined):
        return default if default is not None else Undefined()
    try:
        return json.loads(value)
    except (ValueError, TypeError, json.JSONDecodeError):
        return default if default is not None else Undefined()


# ─── Create HA-like Jinja environment ─────────────────────────────────────

def ha_environment():
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
    raw = blueprint["action"][2]["then"][0]["variables"]["envelope"]
    return raw


# ─── Load config template ──────────────────────────────────────────────────

def load_config_template():
    path = ROOT / "sender-config-blueprint.yaml"
    with open(path) as f:
        blueprint = yaml.load(f, Loader=yaml.FullLoader)
    # config_payload is in action[2]["then"][0]["variables"]["config_payload"]
    raw = blueprint["action"][2]["then"][0]["variables"]["config_payload"]
    return raw


def render_config(template_str, variables):
    env = ha_environment()
    tpl = env.from_string(template_str)
    result = tpl.render(**variables)
    if result.strip() == "":
        return {}
    envelope = json.loads(result)
    return json.loads(envelope["payload"])


# ─── Render helpers ────────────────────────────────────────────────────────

def render_sender(template_str, variables):
    env = ha_environment()
    tpl = env.from_string(template_str)
    result = tpl.render(**variables)
    envelope = json.loads(result)
    return json.loads(envelope["payload"])


def make_sender_vars(**overrides):
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
        # Grid quality (optional — None means not selected)
        gA1=None, gA2=None, gA3=None,
        gF=None, gPF=None,
        gQ=None, gQ1=None, gQ2=None, gQ3=None,
        gS=None, gS1=None, gS2=None, gS3=None,
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


def test_sender_grid_quality():
    """All 13 grid-quality sensors populated → correct keys and rounding."""
    tpl = load_sender_template()
    vars_ = make_sender_vars(
        gA1="sensor.phase1_current", gA2="sensor.phase2_current",
        gA3="sensor.phase3_current",
        gF="sensor.grid_frequency",
        gPF="sensor.grid_power_factor",
        gQ="sensor.reactive_power",
        gQ1="sensor.reactive_power_l1", gQ2="sensor.reactive_power_l2",
        gQ3="sensor.reactive_power_l3",
        gS="sensor.apparent_power",
        gS1="sensor.apparent_power_l1", gS2="sensor.apparent_power_l2",
        gS3="sensor.apparent_power_l3",
    )
    out = render_sender(tpl, vars_)
    keys = sorted(k for k in out if k.startswith(("gA", "gF", "gPF", "gQ", "gS")))
    assert len(keys) == 13, f"Expected 13 grid keys, got {len(keys)}: {keys}"
    assert out["gA1"] == 15.0
    assert out["gA2"] == 14.5
    assert out["gA3"] == 15.5
    assert abs(out["gF"] - 50.02) < 0.01
    assert out["gPF"] == 96.0
    assert out["gQ"] == 200.0
    assert out["gQ1"] == 70.0
    assert out["gS"] == 350.0
    assert out["gS1"] == 120.0


def test_sender_all_33_sensors():
    """All 20 measurement + 13 grid-quality sensors → 33 keys."""
    tpl = load_sender_template()
    vars_ = make_sender_vars(
        gA1="sensor.phase1_current", gA2="sensor.phase2_current",
        gA3="sensor.phase3_current",
        gF="sensor.grid_frequency",
        gPF="sensor.grid_power_factor",
        gQ="sensor.reactive_power",
        gQ1="sensor.reactive_power_l1", gQ2="sensor.reactive_power_l2",
        gQ3="sensor.reactive_power_l3",
        gS="sensor.apparent_power",
        gS1="sensor.apparent_power_l1", gS2="sensor.apparent_power_l2",
        gS3="sensor.apparent_power_l3",
    )
    out = render_sender(tpl, vars_)
    assert len(out) == 33, f"Expected 33 keys, got {len(out)}: {list(out.keys())}"
    assert "gP" in out
    assert "gA1" in out
    assert "gQ" in out
    assert "gS" in out


# ═══════════════════════════════════════════════════════════════════════════
# TESTS — CONFIG BLUEPRINT
# ═══════════════════════════════════════════════════════════════════════════

def make_config_vars(**overrides):
    defaults = dict(
        node="2896876952",
        region="eu868",
        channel_input=1,
        cap=10.0,
        pv=5.0,
        ang=30,
        az=180,
    )
    defaults.update(overrides)
    return defaults


def test_config_all_fields():
    """All config fields populated → correct config payload."""
    tpl = load_config_template()
    out = render_config(tpl, make_config_vars())
    assert len(out) == 4, f"Expected 4 keys, got {len(out)}: {out}"
    assert out["bC"] == 10.0
    assert out["sK"] == 5.0
    assert out["sA"] == 30
    assert out["sZ"] == 180


def test_config_partial():
    """Only cap and pv → 2 keys."""
    tpl = load_config_template()
    out = render_config(tpl, make_config_vars(cap=10.0, pv=5.0, ang="", az=""))
    assert len(out) == 2, f"Expected 2 keys, got {len(out)}: {out}"
    assert out["bC"] == 10.0
    assert out["sK"] == 5.0


def test_config_all_empty():
    """No config fields filled → empty payload dict."""
    tpl = load_config_template()
    out = render_config(tpl, make_config_vars(cap="", pv="", ang="", az=""))
    assert out == {}, f"Expected empty dict, got {out}"


def test_config_float_angle():
    """Float angle → int coercion."""
    tpl = load_config_template()
    out = render_config(tpl, make_config_vars(ang=30.7, az=180.3))
    assert out["sA"] == 30
    assert out["sZ"] == 180


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
    """Universal template: dict payload → value extracted."""
    p = {"from": 2712679380, "payload": {"gP": -1.2, "bS": 85}}
    r = render_receiver_universal(p, 2712679380, "gP", "float(0)")
    assert float(r) == -1.2, f"Expected -1.2, got {r}"


def test_universal_receiver_string_payload():
    """Universal template: string payload → parsed and value extracted."""
    p = {"from": 2712679380, "payload": '{"gP": -1.2, "bS": 85}'}
    r = render_receiver_universal(p, 2712679380, "gP", "float(0)")
    assert float(r) == -1.2, f"Expected -1.2, got {r}"


def test_universal_receiver_dict_mismatch():
    """Universal template: dict payload, from mismatch → fallback."""
    p = {"from": 999, "payload": {"gP": -1.2}}
    r = render_receiver_universal(p, 2712679380, "gP", "float(0)", this_state="-5.0")
    assert r == "-5.0", f"Expected '-5.0', got {r}"


def test_universal_receiver_string_mismatch():
    """Universal template: string payload, from mismatch → fallback."""
    p = {"from": 999, "payload": '{"gP": -1.2}'}
    r = render_receiver_universal(p, 2712679380, "gP", "float(0)", this_state="-5.0")
    assert r == "-5.0", f"Expected '-5.0', got {r}"


def test_universal_receiver_missing_key():
    """Universal template: payload missing the key → default 0."""
    p = {"from": 2712679380, "payload": {"gP": -1.2}}
    r = render_receiver_universal(p, 2712679380, "nonexistent", "float(0)")
    assert float(r) == 0.0, f"Expected 0.0, got {r}"


def test_universal_receiver_int_filter_dict():
    """Universal template: bS via |int(0) with dict payload."""
    p = {"from": 2712679380, "payload": {"bS": 85}}
    r = render_receiver_universal(p, 2712679380, "bS", "int(0)")
    assert int(r) == 85, f"Expected 85, got {r}"


def test_universal_receiver_int_filter_string():
    """Universal template: bS via |int(0) with string payload."""
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
# TESTS — COMBINED SENSORS  (Python sensor.py logic)
# ═══════════════════════════════════════════════════════════════════════════

class _MockMeshData:
    """Minimal mock for MeshData used by combined sensors."""
    def __init__(self):
        self._node_data: dict[str, dict[str, float]] = {}

    def set_values(self, key: str, vals: list[float]) -> None:
        for i, v in enumerate(vals):
            self._node_data.setdefault(str(i), {})[key] = v

    def get_all_values(self, key: str) -> list[float]:
        return [nd[key] for nd in self._node_data.values() if key in nd]

    def known_nodes(self) -> list[str]:
        return list(self._node_data.keys())

    def get_value(self, node_id: str, key: str) -> float | None:
        return self._node_data.get(node_id, {}).get(key)


def test_combined_sum():
    """_sum helper: 3 values → correct total."""
    from custom_components.lotse_forecast.sensor import _sum
    m = _MockMeshData()
    m.set_values("gp", [-1.2, -0.8, 2.5])
    assert abs(_sum(m, "gp") - 0.5) < 0.01


def test_combined_sum_empty():
    """_sum helper: empty → 0."""
    from custom_components.lotse_forecast.sensor import _sum
    assert _sum(_MockMeshData(), "gp") == 0.0


def test_combined_avg():
    """_avg helper: 3 values → correct average."""
    from custom_components.lotse_forecast.sensor import _avg
    m = _MockMeshData()
    m.set_values("bs", [80, 90, 85])
    assert _avg(m, "bs") == 85.0


def test_combined_avg_empty():
    """_avg helper: empty → 0."""
    from custom_components.lotse_forecast.sensor import _avg
    assert _avg(_MockMeshData(), "bs") == 0.0


def test_combined_max():
    """_max helper: 3 values → correct max."""
    from custom_components.lotse_forecast.sensor import _max
    m = _MockMeshData()
    m.set_values("gv1", [230.0, 245.0, 238.5])
    assert abs(_max(m, "gv1") - 245.0) < 0.1


def test_combined_max_empty():
    """_max helper: empty → 0."""
    from custom_components.lotse_forecast.sensor import _max
    assert _max(_MockMeshData(), "gv1") == 0.0


def test_combined_weighted_soc():
    """_weighted_soc: (80*10 + 90*5) / (10+5) = 83.3%."""
    from custom_components.lotse_forecast.sensor import _weighted_soc
    m = _MockMeshData()
    m.set_values("bs", [80, 90])
    m.set_values("bc", [10, 5])
    assert abs(_weighted_soc(m) - 83.3) < 0.1


def test_combined_weighted_soc_empty():
    """_weighted_soc: no data → 0."""
    from custom_components.lotse_forecast.sensor import _weighted_soc
    assert _weighted_soc(_MockMeshData()) == 0.0


def test_combined_weighted_soc_bs_negative():
    """_weighted_soc: negative bs skipped, valid bs still weighted correctly."""
    from custom_components.lotse_forecast.sensor import _weighted_soc
    m = _MockMeshData()
    m.set_values("bs", [-10, 80])
    m.set_values("bc", [10, 10])
    assert abs(_weighted_soc(m) - 80.0) < 0.1


def test_combined_weighted_soc_bs_over_100():
    """_weighted_soc: bs > 100 skipped."""
    from custom_components.lotse_forecast.sensor import _weighted_soc
    m = _MockMeshData()
    m.set_values("bs", [150, 80])
    m.set_values("bc", [10, 10])
    assert abs(_weighted_soc(m) - 80.0) < 0.1


def test_combined_weighted_soc_partial():
    """_weighted_soc: nodes with bs but no bc skipped; valid ones weighted."""
    from custom_components.lotse_forecast.sensor import _weighted_soc
    m = _MockMeshData()
    m._node_data = {
        "a": {"bs": 80, "bc": 10},
        "b": {"bs": 70},
        "c": {"bs": 90, "bc": 5},
    }
    assert abs(_weighted_soc(m) - 83.3) < 0.1


def test_combined_weighted_soc_bc_zero():
    """_weighted_soc: bc=0 excluded from weighting, other nodes still work."""
    from custom_components.lotse_forecast.sensor import _weighted_soc
    m = _MockMeshData()
    m._node_data = {
        "a": {"bs": 80, "bc": 10},
        "b": {"bs": 90, "bc": 0},
    }
    assert abs(_weighted_soc(m) - 80.0) < 0.1


def test_combined_weighted_soc_all_bc_zero_fallback():
    """_weighted_soc: all bc=0 falls back to simple bs average."""
    from custom_components.lotse_forecast.sensor import _weighted_soc
    m = _MockMeshData()
    m.set_values("bs", [80, 90])
    m.set_values("bc", [0, 0])
    assert abs(_weighted_soc(m) - 85.0) < 0.1


def test_combined_weighted_soc_bs_only_fallback():
    """_weighted_soc: no bc at all falls back to simple bs average."""
    from custom_components.lotse_forecast.sensor import _weighted_soc
    m = _MockMeshData()
    m.set_values("bs", [80, 90])
    assert abs(_weighted_soc(m) - 85.0) < 0.1


def test_combined_min():
    """_min helper: 3 values → correct min."""
    from custom_components.lotse_forecast.sensor import _min
    m = _MockMeshData()
    m.set_values("gv1", [230.0, 245.0, 238.5])
    assert abs(_min(m, "gv1") - 230.0) < 0.1


def test_combined_min_empty():
    """_min helper: empty → 0."""
    from custom_components.lotse_forecast.sensor import _min
    assert _min(_MockMeshData(), "gv1") == 0.0


def test_combined_gf_avg():
    """gf_avg: 3 values → correct average."""
    from custom_components.lotse_forecast.sensor import COMBINED_FNS
    m = _MockMeshData()
    m.set_values("gf", [50.0, 50.02, 49.98])
    fn = COMBINED_FNS["combined_mesh_gf_avg"]
    assert abs(fn(m) - 50.0) < 0.1


def test_combined_gf_min_max():
    """gf_min/gf_max: correct bounds."""
    from custom_components.lotse_forecast.sensor import COMBINED_FNS
    m = _MockMeshData()
    m.set_values("gf", [50.0, 50.1, 49.9])
    assert abs(COMBINED_FNS["combined_mesh_gf_min"](m) - 49.9) < 0.1
    assert abs(COMBINED_FNS["combined_mesh_gf_max"](m) - 50.1) < 0.1


def test_combined_gpf_avg():
    """gpf_avg: 3 values → correct average."""
    from custom_components.lotse_forecast.sensor import COMBINED_FNS
    m = _MockMeshData()
    m.set_values("gpf", [95.0, 97.0, 96.0])
    assert abs(COMBINED_FNS["combined_mesh_gpf_avg"](m) - 96.0) < 0.1


def test_combined_voltage_min_max():
    """gv1/gv2/gv3 min and max: correct bounds."""
    from custom_components.lotse_forecast.sensor import COMBINED_FNS
    m = _MockMeshData()
    m.set_values("gv1", [230.0, 245.0, 238.5])
    m.set_values("gv2", [229.0, 231.0])
    m.set_values("gv3", [228.0, 232.0, 230.0])
    assert abs(COMBINED_FNS["combined_mesh_gv1_min"](m) - 230.0) < 0.1
    assert abs(COMBINED_FNS["combined_mesh_gv1_max"](m) - 245.0) < 0.1
    assert abs(COMBINED_FNS["combined_mesh_gv2_min"](m) - 229.0) < 0.1
    assert abs(COMBINED_FNS["combined_mesh_gv2_max"](m) - 231.0) < 0.1
    assert abs(COMBINED_FNS["combined_mesh_gv3_min"](m) - 228.0) < 0.1
    assert abs(COMBINED_FNS["combined_mesh_gv3_max"](m) - 232.0) < 0.1


def test_combined_phase_currents():
    """ga1/ga2/ga3 sum: correct totals."""
    from custom_components.lotse_forecast.sensor import COMBINED_FNS
    m = _MockMeshData()
    m.set_values("ga1", [10.0, 12.0])
    m.set_values("ga2", [9.5, 11.5])
    m.set_values("ga3", [10.5, 11.0])
    assert abs(COMBINED_FNS["combined_mesh_ga1_sum"](m) - 22.0) < 0.1
    assert abs(COMBINED_FNS["combined_mesh_ga2_sum"](m) - 21.0) < 0.1
    assert abs(COMBINED_FNS["combined_mesh_ga3_sum"](m) - 21.5) < 0.1


def test_combined_reactive_apparent():
    """gq_sum / gs_sum: correct totals."""
    from custom_components.lotse_forecast.sensor import COMBINED_FNS
    m = _MockMeshData()
    m.set_values("gq", [100.0, 150.0])
    m.set_values("gs", [300.0, 400.0])
    assert abs(COMBINED_FNS["combined_mesh_gq_sum"](m) - 250.0) < 0.1
    assert abs(COMBINED_FNS["combined_mesh_gs_sum"](m) - 700.0) < 0.1


def test_combined_participants():
    """participants: 2 nodes with gip > 0."""
    from custom_components.lotse_forecast.sensor import COMBINED_FNS
    m = _MockMeshData()
    m.set_values("gip", [1.2, 0.0, 3.0])
    fn = COMBINED_FNS["combined_mesh_participants"]
    assert fn(m) == 2.0


def test_combined_config_ready():
    """config_ready: 2 nodes with bc."""
    from custom_components.lotse_forecast.sensor import COMBINED_FNS
    m = _MockMeshData()
    m.set_values("bc", [10, 5])
    fn = COMBINED_FNS["combined_mesh_config_ready"]
    assert fn(m) == 2.0


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
