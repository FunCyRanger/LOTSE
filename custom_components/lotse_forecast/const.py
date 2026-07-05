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
    "gq":  {"unit": "VAr", "device_class": "reactive_power", "state_class": "measurement", "name": "gQ"},
    "gq1": {"unit": "VAr", "device_class": "reactive_power", "state_class": "measurement", "name": "gQ1"},
    "gq2": {"unit": "VAr", "device_class": "reactive_power", "state_class": "measurement", "name": "gQ2"},
    "gq3": {"unit": "VAr", "device_class": "reactive_power", "state_class": "measurement", "name": "gQ3"},
    "gs":  {"unit": "VA",  "device_class": "apparent_power", "state_class": "measurement", "name": "gS"},
    "gs1": {"unit": "VA",  "device_class": "apparent_power", "state_class": "measurement", "name": "gS1"},
    "gs2": {"unit": "VA",  "device_class": "apparent_power", "state_class": "measurement", "name": "gS2"},
    "gs3": {"unit": "VA",  "device_class": "apparent_power", "state_class": "measurement", "name": "gS3"},
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
    # Cumulative energy (valid — monotonically increasing)
    "combined_mesh_gei": {"unit": "kWh", "device_class": "energy",    "state_class": "total_increasing",  "name": "Combined Mesh Grid Import"},
    "combined_mesh_geo": {"unit": "kWh", "device_class": "energy",    "state_class": "total_increasing",  "name": "Combined Mesh Grid Export"},
    "combined_mesh_se":  {"unit": "kWh", "device_class": "energy",    "state_class": "total_increasing",  "name": "Combined Mesh Solar Energy"},
    "combined_mesh_se_clean": {"unit": "kWh", "device_class": "energy", "state_class": "total_increasing", "name": "Combined Mesh Solar Energy Clean"},
    "combined_mesh_bei": {"unit": "kWh", "device_class": "energy", "state_class": "total_increasing", "name": "Combined Mesh Battery Energy In"},
    "combined_mesh_beo": {"unit": "kWh", "device_class": "energy", "state_class": "total_increasing", "name": "Combined Mesh Battery Energy Out"},
    # Static config (valid — doesn't change between reports)
    "combined_mesh_battery_capacity": {"unit": "kWh", "device_class": "energy", "state_class": "total", "name": "Combined Mesh Battery Capacity"},
    "combined_mesh_solar_capacity":   {"unit": "kW",  "device_class": "power",  "state_class": "measurement", "name": "Combined Mesh Solar Capacity"},
    # Slow-changing averages (valid — SOC/charge changes slowly)
    "combined_mesh_bs":  {"unit": "%",   "device_class": "battery",   "state_class": "measurement",       "name": "Average Neighbor SOC"},
    "combined_mesh_soc_weighted": {"unit": "%",   "device_class": "battery", "state_class": "measurement", "name": "Weighted Average SOC"},
    # Counters (timeless)
    "combined_mesh_participants": {"unit": "nodes", "name": "Participating Neighbors"},
    "combined_mesh_config_ready": {"unit": "nodes", "name": "Config-Ready Nodes"},
    # Grid-coherent stats (valid — same physical grid, min/max/avg across nodes)
    "combined_mesh_gv1_max": {"unit": "V",   "device_class": "voltage", "state_class": "measurement", "name": "Combined Mesh Max Voltage L1"},
    "combined_mesh_gv1_min": {"unit": "V",   "device_class": "voltage", "state_class": "measurement", "name": "Combined Mesh Min Voltage L1"},
    "combined_mesh_gv2_max": {"unit": "V",   "device_class": "voltage", "state_class": "measurement", "name": "Combined Mesh Max Voltage L2"},
    "combined_mesh_gv2_min": {"unit": "V",   "device_class": "voltage", "state_class": "measurement", "name": "Combined Mesh Min Voltage L2"},
    "combined_mesh_gv3_max": {"unit": "V",   "device_class": "voltage", "state_class": "measurement", "name": "Combined Mesh Max Voltage L3"},
    "combined_mesh_gv3_min": {"unit": "V",   "device_class": "voltage", "state_class": "measurement", "name": "Combined Mesh Min Voltage L3"},
    "combined_mesh_gf_avg":  {"unit": "Hz",  "device_class": "frequency", "state_class": "measurement", "name": "Combined Mesh Avg Frequency"},
    "combined_mesh_gf_min":  {"unit": "Hz",  "device_class": "frequency", "state_class": "measurement", "name": "Combined Mesh Min Frequency"},
    "combined_mesh_gf_max":  {"unit": "Hz",  "device_class": "frequency", "state_class": "measurement", "name": "Combined Mesh Max Frequency"},
    "combined_mesh_gpf_avg": {"unit": "%",   "device_class": "power_factor", "state_class": "measurement", "name": "Combined Mesh Avg Power Factor"},
    # Phase current sums (approximate snapshot — useful for phase balance)
    "combined_mesh_ga1_sum": {"unit": "A",   "device_class": "current", "state_class": "measurement", "name": "Combined Mesh Total Current L1"},
    "combined_mesh_ga2_sum": {"unit": "A",   "device_class": "current", "state_class": "measurement", "name": "Combined Mesh Total Current L2"},
    "combined_mesh_ga3_sum": {"unit": "A",   "device_class": "current", "state_class": "measurement", "name": "Combined Mesh Total Current L3"},
    # Reactive and apparent power (new protocol keys)
    "combined_mesh_gq_sum": {"unit": "VAr",  "device_class": "reactive_power", "state_class": "measurement", "name": "Combined Mesh Reactive Power"},
    "combined_mesh_gs_sum": {"unit": "VA",   "device_class": "apparent_power", "state_class": "measurement", "name": "Combined Mesh Apparent Power"},
    # Forecast
    "solar_production_forecast": {"unit": "kWh", "device_class": "energy", "state_class": "total", "name": "Solar Production with Forecast"},
}
