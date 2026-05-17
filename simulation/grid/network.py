import pandapower as pp
import pandapower.networks as nw
import numpy as np


def build_lv_network(config: dict) -> pp.pandapowerNet:
    net = pp.create_empty_network()
    trafo_kva = config.get("transformer_kva", 630)
    feeder_cfg = config.get("feeder_config", {"n_feeder": 1, "households_per_feeder": [10], "feeder_length_km": [0.3]})
    vn_kv = 0.4

    pp.create_bus(net, vn_kv=20, name="hv_bus")
    pp.create_bus(net, vn_kv=vn_kv, name="lv_bus")
    pp.create_ext_grid(net, bus=0, vm_pu=1.02)

    pp.create_transformer_from_parameters(
        net, hv_bus=0, lv_bus=1,
        sn_mva=trafo_kva / 1000,
        vn_hv_kv=20, vn_lv_kv=vn_kv,
        vkr_percent=1.0, vk_percent=4.0,
        pfe_kw=0.3, i0_percent=0.1,
        name="trafo",
    )

    n_households = sum(feeder_cfg.get("households_per_feeder", []))
    household_buses = []
    bus_counter = 1

    for feeder_idx, (n_hh, length_km) in enumerate(
        zip(
            feeder_cfg.get("households_per_feeder", []),
            feeder_cfg.get("feeder_length_km", [0.3] * len(feeder_cfg.get("households_per_feeder", [10]))),
        )
    ):
        prev_bus = 1
        n_segments = max(1, n_hh)
        segment_km = length_km / n_segments

        for seg in range(n_segments):
            bus_counter += 1
            pp.create_bus(net, vn_kv=vn_kv, name=f"f{feeder_idx}_s{seg}")
            pp.create_line_from_parameters(
                net,
                from_bus=prev_bus,
                to_bus=bus_counter,
                length_km=segment_km,
                r_ohm_per_km=0.208,
                x_ohm_per_km=0.080,
                c_nf_per_km=600,
                max_i_ka=0.355,
                name=f"line_f{feeder_idx}_s{seg}",
            )
            prev_bus = bus_counter

        for hh in range(n_hh):
            bus_counter += 1
            pp.create_bus(net, vn_kv=vn_kv, name=f"f{feeder_idx}_hh_{hh}")
            seg_bus = 2 + feeder_idx * n_segments + min(hh, n_segments - 1)
            pp.create_line_from_parameters(
                net,
                from_bus=seg_bus,
                to_bus=bus_counter,
                length_km=0.015,
                r_ohm_per_km=0.841,
                x_ohm_per_km=0.076,
                c_nf_per_km=300,
                max_i_ka=0.182,
                name=f"service_f{feeder_idx}_hh_{hh}",
            )
            household_buses.append(bus_counter)

    if len(household_buses) < n_households:
        while len(household_buses) < n_households:
            household_buses.append(household_buses[-1])

    for bus in household_buses:
        pp.create_load(net, bus=bus, p_mw=0.0, q_mvar=0.0, name=f"load_{bus}")

    net._household_bus_map = {i: bus for i, bus in enumerate(household_buses)}
    return net


def run_load_flow(net: pp.pandapowerNet, loads_mw: dict[int, float]) -> dict:
    for hh_idx, p_mw in loads_mw.items():
        bus = net._household_bus_map.get(hh_idx)
        if bus is not None:
            load_idx = net.load.loc[net.load.bus == bus].index
            if len(load_idx) > 0:
                net.load.loc[load_idx, "p_mw"] = p_mw
            else:
                pp.create_load(net, bus=bus, p_mw=p_mw, q_mvar=0, name=f"load_{hh_idx}")

    try:
        pp.runpp(net, algorithm="nr", max_iteration=10, tolerance_mva=1e-8, numba=False)
    except pp.LoadflowNotConverged:
        try:
            pp.runpp(net, algorithm="iwamoto_nr", numba=False)
        except pp.LoadflowNotConverged:
            return {"converged": False, "vm_pu": {}, "loading_pct": {}, "trafo_loading_pct": 0}

    vm = net.res_bus["vm_pu"].to_dict()
    loading = {}
    if not net.res_line.empty:
        line_names = net.line.index if "name" not in net.line.columns else net.line.index
        loading = dict(zip(line_names, net.res_line["loading_percent"].values))
    trafo_loading = (net.res_trafo["loading_percent"].iloc[0]) if not net.res_trafo.empty else 0

    return {
        "converged": True,
        "vm_pu": vm,
        "loading_pct": loading,
        "trafo_loading_pct": float(trafo_loading),
    }
