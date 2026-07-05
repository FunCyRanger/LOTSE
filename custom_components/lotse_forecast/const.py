from __future__ import annotations

DOMAIN = "lotse_forecast"

PLATFORMS = ["sensor"]

MSH_TOPIC = "msh/+/2/json/mqtt/+"

CONF_WEATHER_ENTITY = "weather_entity"

BAD_STATES = {"unknown", "unavailable", "none", "nan", "inf", "-inf"}

NODE_KEY_META: dict[str, dict] = {
    "gp":  {"unit": "kW",  "device_class": "power",     "state_class": "measurement",     "name": "gP"},
    "gip": {"unit": "kW",  "device_class": "power",     "state_class": "measurement",     "name": "gIP"},
    "gep": {"unit": "kW",  "device_class": "power",     "state_class": "measurement",     "name": "gEP"},
    "gp1": {"unit": "kW",  "device_class": "power",     "state_class": "measurement",     "name": "gP1"},
    "gp2": {"unit": "kW",  "device_class": "power",     "state_class": "measurement",     "name": "gP2"},
    "gp3": {"unit": "kW",  "device_class": "power",     "state_class": "measurement",     "name": "gP3"},
    "gv1": {"unit": "V",   "device_class": "voltage",   "state_class": "measurement",     "name": "gV1"},
    "gv2": {"unit": "V",   "device_class": "voltage",   "state_class": "measurement",     "name": "gV2"},
    "gv3": {"unit": "V",   "device_class": "voltage",   "state_class": "measurement",     "name": "gV3"},
    "ga1": {"unit": "A",   "device_class": "current",   "state_class": "measurement",     "name": "gA1"},
    "ga2": {"unit": "A",   "device_class": "current",   "state_class": "measurement",     "name": "gA2"},
    "ga3": {"unit": "A",   "device_class": "current",   "state_class": "measurement",     "name": "gA3"},
    "gf":  {"unit": "Hz",  "device_class": "frequency", "state_class": "measurement",     "name": "gF"},
    "gpf": {"unit": "%",   "device_class": "power_factor", "state_class": "measurement",  "name": "gPF"},
    "gei": {"unit": "kWh", "device_class": "energy",    "state_class": "total_increasing", "name": "gEI"},
    "geo": {"unit": "kWh", "device_class": "energy",    "state_class": "total_increasing", "name": "gEO"},
    "sp":  {"unit": "kW",  "device_class": "power",     "state_class": "measurement",     "name": "sP"},
    "se":  {"unit": "kWh", "device_class": "energy",    "state_class": "total_increasing", "name": "sE"},
    "bp":  {"unit": "kW",  "device_class": "power",     "state_class": "measurement",     "name": "bP"},
    "bs":  {"unit": "%",   "device_class": "battery",   "state_class": "measurement",     "name": "bS"},
    "bei": {"unit": "kWh", "device_class": "energy",    "state_class": "total_increasing", "name": "bEI"},
    "beo": {"unit": "kWh", "device_class": "energy",    "state_class": "total_increasing", "name": "bEO"},
    "wp":  {"unit": "kW",  "device_class": "power",     "state_class": "measurement",     "name": "wP"},
    "we":  {"unit": "kWh", "device_class": "energy",    "state_class": "total_increasing", "name": "wE"},
    "ws":  {"unit": "%",   "device_class": "battery",   "state_class": "measurement",     "name": "wS"},
    "bc":  {"unit": "kWh", "device_class": "energy",    "state_class": "total",           "name": "bC"},
    "sk":  {"unit": "kW",  "device_class": "power",     "state_class": "measurement",     "name": "sK"},
    "sa":  {"unit": "°",   "state_class": "measurement",                                 "name": "sA"},
    "sz":  {"unit": "°",   "state_class": "measurement",                                 "name": "sZ"},
}

COMBINED_KEY_META: dict[str, dict] = {
    "combined_mesh_gp":  {"unit": "kW",  "device_class": "power",     "state_class": "measurement",       "name": "Combined Mesh Grid Power"},
    "combined_mesh_gip": {"unit": "kW",  "device_class": "power",     "state_class": "measurement",       "name": "Combined Mesh Grid Import Power"},
    "combined_mesh_gep": {"unit": "kW",  "device_class": "power",     "state_class": "measurement",       "name": "Combined Mesh Grid Export Power"},
    "combined_mesh_gp1": {"unit": "kW",  "device_class": "power",     "state_class": "measurement",       "name": "Combined Mesh Grid Phase 1 Power"},
    "combined_mesh_gp2": {"unit": "kW",  "device_class": "power",     "state_class": "measurement",       "name": "Combined Mesh Grid Phase 2 Power"},
    "combined_mesh_gp3": {"unit": "kW",  "device_class": "power",     "state_class": "measurement",       "name": "Combined Mesh Grid Phase 3 Power"},
    "combined_mesh_gv1": {"unit": "V",   "device_class": "voltage",   "state_class": "measurement",       "name": "Combined Mesh Voltage L1"},
    "combined_mesh_gei": {"unit": "kWh", "device_class": "energy",    "state_class": "total_increasing",  "name": "Combined Mesh Grid Import"},
    "combined_mesh_geo": {"unit": "kWh", "device_class": "energy",    "state_class": "total_increasing",  "name": "Combined Mesh Grid Export"},
    "combined_mesh_sp":  {"unit": "kW",  "device_class": "power",     "state_class": "measurement",       "name": "Combined Mesh Solar Power"},
    "combined_mesh_se":  {"unit": "kWh", "device_class": "energy",    "state_class": "total_increasing",  "name": "Combined Mesh Solar Energy"},
    "combined_mesh_bp":  {"unit": "kW",  "device_class": "power",     "state_class": "measurement",       "name": "Combined Mesh Battery Power"},
    "combined_mesh_bs":  {"unit": "%",   "device_class": "battery",   "state_class": "measurement",       "name": "Average Neighbor SOC"},
    "combined_mesh_battery_capacity": {"unit": "kWh", "device_class": "energy", "state_class": "total", "name": "Combined Mesh Battery Capacity"},
    "combined_mesh_bei": {"unit": "kWh", "device_class": "energy", "state_class": "total_increasing", "name": "Combined Mesh Battery Energy In"},
    "combined_mesh_beo": {"unit": "kWh", "device_class": "energy", "state_class": "total_increasing", "name": "Combined Mesh Battery Energy Out"},
    "combined_mesh_solar_capacity":   {"unit": "kW",  "device_class": "power",  "state_class": "measurement", "name": "Combined Mesh Solar Capacity"},
    "combined_mesh_participants":     {"unit": "nodes",                               "name": "Participating Neighbors"},
    "combined_mesh_config_ready":     {"unit": "nodes",                               "name": "Config-Ready Nodes"},
    "combined_mesh_total_solar_generation": {"unit": "kW", "device_class": "power", "state_class": "measurement", "name": "Combined Mesh Total Solar Generation"},
    "combined_solar_utilization":     {"unit": "%",                                   "name": "Combined Solar Utilization"},
    "combined_mesh_self_consumption_rate": {"unit": "%",                              "name": "Combined Self-Consumption Rate"},
    "combined_mesh_soc_weighted":     {"unit": "%",   "device_class": "battery",     "state_class": "measurement", "name": "Weighted Average SOC"},
    "combined_mesh_gv1_max":          {"unit": "V",   "device_class": "voltage",     "state_class": "measurement", "name": "Combined Mesh Max Voltage"},
    "combined_mesh_export_ratio":     {"unit": "%",                                   "name": "Combined Mesh Export Ratio"},
    "combined_mesh_se_clean":         {"unit": "kWh", "device_class": "energy",      "state_class": "total_increasing", "name": "Combined Mesh Solar Energy Clean"},
    "solar_production_forecast":      {"unit": "kWh", "device_class": "energy",      "state_class": "total", "name": "Solar Production with Forecast"},
}
