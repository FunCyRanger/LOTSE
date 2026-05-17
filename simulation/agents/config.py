from simulation.core.types import AgentConfig


def build_agent_configs(config: dict) -> list[AgentConfig]:
    mix = config["household_mix"]
    defaults = config.get("type_defaults", {})
    n = config["n_households"]
    limit_w = config["grid_limit_w"]
    tariff_ct = config.get("tariff_rate_ct_per_kwh", 30.0)
    eeg_ct = config.get("eeg_rate_ct_per_kwh", 8.2)

    type_list = []
    for t, frac in mix.items():
        count = max(1, round(frac * n))
        type_list.extend([t] * count)

    type_list = type_list[:n]
    while len(type_list) < n:
        type_list.append("T1")

    configs = []
    for idx, t in enumerate(type_list):
        td = defaults.get(t, {}).copy()
        c = AgentConfig(
            household_type=t,
            idx=idx,
            annual_consumption_kwh=td.get("annual_consumption_kwh", 4000),
            pv_kwp=td.get("pv_kwp", 0),
            battery_kwh=td.get("battery_kwh", 0),
            battery_kw=td.get("battery_kw", 0),
            ev_kwh=td.get("ev_kwh", 0),
            ev_kw=td.get("ev_kw", 0),
            ev_arrival_hour=td.get("ev_arrival_hour", 17),
            ev_departure_hour=td.get("ev_departure_hour", 8),
            hp_kw=td.get("hp_kw", 0),
            hp_buffer_kwh=td.get("hp_buffer_kwh", 0),
            grid_limit_w=limit_w,
            tariff_rate_ct=tariff_ct,
            eeg_rate_ct=eeg_ct,
        )
        configs.append(c)
    return configs
