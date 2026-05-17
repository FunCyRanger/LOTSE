import numpy as np
from collections import defaultdict


def compute_fairness_metrics(
    baseline_costs: list[float],
    coord_costs: list[float],
    agent_types: list[str],
) -> dict:
    cost_deltas = [c - b for b, c in zip(baseline_costs, coord_costs)]
    violations = [(i, d) for i, d in enumerate(cost_deltas) if d > 0.01]

    per_type = defaultdict(list)
    for i, delta in enumerate(cost_deltas):
        per_type[agent_types[i]].append(delta)

    type_stats = {}
    for t, deltas in per_type.items():
        type_stats[t] = {
            "count": len(deltas),
            "mean_delta_ct": np.mean(deltas),
            "max_delta_ct": max(deltas),
            "min_delta_ct": min(deltas),
            "violations": sum(1 for d in deltas if d > 0.01),
        }

    total_baseline = sum(baseline_costs)
    total_coord = sum(coord_costs)
    total_savings = total_baseline - total_coord

    positive_deltas = [d for d in cost_deltas if d > 0]
    sorted_deltas = sorted(cost_deltas)

    return {
        "max_cost_delta_ct": max(cost_deltas) if cost_deltas else 0,
        "min_cost_delta_ct": min(cost_deltas) if cost_deltas else 0,
        "mean_cost_delta_ct": np.mean(cost_deltas) if cost_deltas else 0,
        "total_baseline_cost_ct": total_baseline,
        "total_coord_cost_ct": total_coord,
        "total_savings_ct": total_savings,
        "violations_count": len(violations),
        "violations": violations,
        "gini": _gini(sorted_deltas) if len(sorted_deltas) > 1 else 0.0,
        "per_type": type_stats,
    }


def _gini(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    sorted_vals = np.sort(values)
    total = np.sum(sorted_vals)
    if total == 0:
        return 0.0
    cumsum = np.cumsum(sorted_vals)
    return float((n + 1 - 2 * np.sum(cumsum) / total) / n)


def compute_grid_metrics(grid_results: list[dict]) -> dict:
    trafo_loadings = [r.get("trafo_loading_pct", 0) for r in grid_results if r]
    converged = sum(1 for r in grid_results if r and r.get("converged", False))

    return {
        "max_trafo_loading_pct": max(trafo_loadings) if trafo_loadings else 0,
        "mean_trafo_loading_pct": np.mean(trafo_loadings) if trafo_loadings else 0,
        "p95_trafo_loading_pct": np.percentile(trafo_loadings, 95) if trafo_loadings else 0,
        "hours_above_100pct": sum(1 for l in trafo_loadings if l >= 100),
        "hours_above_90pct": sum(1 for l in trafo_loadings if l >= 90),
        "converged_steps": converged,
        "total_steps": len(grid_results),
    }


def compute_comms_metrics(agent_results: list[dict], config: dict) -> dict:
    total_messages = 0
    total_offers = 0
    total_sheds = 0

    for ar in agent_results:
        total_messages += ar.get("messages_sent", 0)
        total_offers += ar.get("flex_offers", 0)
        total_sheds += ar.get("shed_events", 0)

    n_agents = len(agent_results)
    steps = 365 * 24 * 4
    duty_cycle_limit = config.get("lora", {}).get("duty_cycle_pct", 1.0) / 100

    msg_per_agent_per_hour = total_messages / max(1, n_agents) / 24 / 365 * 96 * 4 if n_agents else 0

    time_on_air_per_msg_s = 0.1
    total_on_air_s = total_messages * time_on_air_per_msg_s
    window_s = steps * 15 * 60
    duty_cycle_used = total_on_air_s / max(1, window_s)

    return {
        "total_messages": total_messages,
        "flex_offers": total_offers,
        "shed_events": total_sheds,
        "msg_per_agent_per_hour": msg_per_agent_per_hour,
        "duty_cycle_used_pct": duty_cycle_used * 100,
        "duty_cycle_limit_pct": duty_cycle_limit * 100,
        "duty_cycle_ok": duty_cycle_used <= duty_cycle_limit,
    }
