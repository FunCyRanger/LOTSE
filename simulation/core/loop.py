from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd

from simulation.agents.base import BaseAgent
from simulation.agents.config import build_agent_configs
from simulation.agents.types import create_agent, TimestepData
from simulation.coordinator.approaches import create_strategy, FairnessStrategy
from simulation.core.types import SimulationResult
from simulation.data.loader import generate_load_profile, generate_pv_profile
from simulation.grid.network import build_lv_network, run_load_flow
from simulation.metrics.metrics import compute_fairness_metrics, compute_grid_metrics, compute_comms_metrics


def run_simulation(config: dict) -> SimulationResult:
    np.random.seed(config.get("seed", 42))
    timestep_min = config.get("timestep_min", 15)
    dt_h = timestep_min / 60
    days = config.get("duration_days", 365)
    n_steps = int(days * 24 * 60 / timestep_min)
    year = config.get("year", 2023)

    agent_configs = build_agent_configs(config)
    agents = [create_agent(c) for c in agent_configs]
    n_agents = len(agents)

    strategy: FairnessStrategy = create_strategy(config.get("approach", "A"), config)
    net = build_lv_network(config)

    total_annual_kwh = sum(c.annual_consumption_kwh for c in agent_configs)
    load_profiles = generate_load_profile(
        annual_consumption_kwh=max(total_annual_kwh / max(1, n_agents), 1000),
        n_households=n_agents,
        year=year,
        timestep_min=timestep_min,
        seed=42,
    )

    total_pv_kwp = sum(c.pv_kwp for c in agent_configs)
    pv_profile = generate_pv_profile(
        total_kwp=max(total_pv_kwp, 1),
        year=year,
        timestep_min=timestep_min,
        seed=43,
    )

    if n_agents > 0 and n_steps > 0:
        price_profile = np.zeros(n_steps)
        base_price = np.random.lognormal(mean=2.5, sigma=0.5, size=n_steps)
        hour_cycle = np.tile(
            np.concatenate([
                np.linspace(0.8, 1.0, 6),
                np.linspace(1.0, 1.8, 4),
                np.linspace(1.8, 1.2, 4),
                np.linspace(1.2, 2.0, 4),
                np.linspace(2.0, 1.0, 6),
            ]),
            int(np.ceil(n_steps / 24))
        )[:n_steps]
        season = np.cos(2 * np.pi * np.arange(n_steps) / (365 * 96)) * 0.3 + 1.0
        price_profile = base_price * hour_cycle * season[:n_steps]
        price_profile = np.clip(price_profile, 0, 50) + np.random.lognormal(-2, 0.3, n_steps) * 5
    else:
        price_profile = np.full(n_steps, 10.0)

    par14a_events = _generate_par14a_events(config, n_steps, seed=44)

    baseline_costs = np.zeros(n_agents)
    coord_costs = np.zeros(n_agents)
    baseline_actions_list = []
    coord_actions_list = []
    grid_results = []
    agent_metrics = [{"messages_sent": 0, "flex_offers": 0, "shed_events": 0} for _ in range(n_agents)]

    for step in range(n_steps):
        hour = (step * timestep_min // 60) % 24
        dayofyear = int(step * timestep_min / (60 * 24)) + 1
        price_ct = float(price_profile[step])
        par14a = par14a_events[step] if step < len(par14a_events) else False

        load_at_step = load_profiles.iloc[step] if step < len(load_profiles) else pd.Series(0, index=range(n_agents))
        pv_at_step = pv_profile.iloc[step] if step < len(pv_profile) else 0.0

        batch_load_w = {}
        batch_pv_w = {}
        for i in range(n_agents):
            hh_scale = agent_configs[i].annual_consumption_kwh / max(1, total_annual_kwh) * n_agents
            batch_load_w[i] = max(0, float(load_at_step.get(f"hh_{i}", 0)) * hh_scale * 2)
            pv_share = agent_configs[i].pv_kwp / max(1, total_pv_kwp)
            batch_pv_w[i] = max(0, float(pv_at_step) * pv_share * 2)

        baseline_actions = []
        for i, agent in enumerate(agents):
            td = TimestepData(
                price_ct=price_ct,
                load_w=batch_load_w.get(i, 0),
                pv_w=batch_pv_w.get(i, 0),
                hour=hour,
                dayofyear=dayofyear,
                dt_h=dt_h,
                par14a_active=par14a,
            )
            action = agent.baseline_action(td)
            baseline_actions.append(action)
            baseline_costs[i] += action.cost_ct(price_ct, agent_configs[i], dt_h)

        total_import_kw = sum(max(0, a.net_grid_kw) for a in baseline_actions)
        total_limit_kw = n_agents * config["grid_limit_w"] / 1000
        grid_util = total_import_kw / max(1, total_limit_kw) * 100

        coord_signals = strategy.process_flex(agents, baseline_actions, demand_kw=0)
        shed_signals = strategy.process_load_shed(agents, baseline_actions, grid_util)
        for i in range(n_agents):
            if shed_signals[i].load_shed:
                coord_signals[i] = shed_signals[i]

        coord_actions = []
        for i, agent in enumerate(agents):
            td = TimestepData(
                price_ct=price_ct,
                load_w=batch_load_w.get(i, 0),
                pv_w=batch_pv_w.get(i, 0),
                hour=hour,
                dayofyear=dayofyear,
                dt_h=dt_h,
                par14a_active=par14a,
            )
            action = agent.coordination_action(td, coord_signals[i])
            coord_actions.append(action)
            coord_costs[i] += action.cost_ct(price_ct, agent_configs[i], dt_h)

            if coord_signals[i].flex_request_kw > 0:
                agent_metrics[i]["flex_offers"] += 1
                agent_metrics[i]["messages_sent"] += 2
            if coord_signals[i].load_shed:
                agent_metrics[i]["shed_events"] += 1
                agent_metrics[i]["messages_sent"] += 1
            agent_metrics[i]["messages_sent"] += 1

        if step % 4 == 0:
            loads_mw = {}
            for i, a in enumerate(coord_actions):
                bus = net._household_bus_map.get(i)
                if bus is not None:
                    loads_mw[i] = a.net_grid_kw / 1000
            result = run_load_flow(net, loads_mw)
            grid_results.append(result)

    for agent in agents:
        agent.reset()

    result = SimulationResult(
        agent_results=agent_metrics,
        grid_results=grid_results,
        comms_results=[],
        approach_name=strategy.name,
        config=config,
    )

    result.fairness_metrics = compute_fairness_metrics(
        [float(b) for b in baseline_costs],
        [float(c) for c in coord_costs],
        [c.household_type for c in agent_configs],
    )

    result.grid_summary = compute_grid_metrics(grid_results)
    result.comms_summary = compute_comms_metrics(agent_metrics, config)

    result.per_agent = []
    for i in range(n_agents):
        result.per_agent.append({
            "idx": i,
            "type": agent_configs[i].household_type,
            "baseline_cost_ct": float(baseline_costs[i]),
            "coord_cost_ct": float(coord_costs[i]),
            "delta_ct": float(coord_costs[i] - baseline_costs[i]),
            "messages_sent": agent_metrics[i]["messages_sent"],
            "flex_offers": agent_metrics[i]["flex_offers"],
            "shed_events": agent_metrics[i]["shed_events"],
        })

    return result


def _generate_par14a_events(config: dict, n_steps: int, seed: int = 44) -> np.ndarray:
    if not config.get("par14a", {}).get("enabled", False):
        return np.zeros(n_steps, dtype=bool)

    rng = np.random.default_rng(seed)
    events_per_year = config["par14a"]["events_per_year"]
    max_duration = config["par14a"]["max_duration_h"]
    dt_h = config.get("timestep_min", 15) / 60
    steps_per_event = int(max_duration / dt_h)

    active = np.zeros(n_steps, dtype=bool)
    for _ in range(events_per_year):
        start = rng.integers(0, n_steps - steps_per_event)
        active[start:start + steps_per_event] = True

    return active
