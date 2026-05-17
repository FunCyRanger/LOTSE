import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path


def generate_plots(result, output_dir: Path):
    per_agent = result.per_agent
    if not per_agent:
        return

    types = [a["type"] for a in per_agent]
    deltas = [a["delta_ct"] / 100 for a in per_agent]

    colors = plt.cm.Set2(np.linspace(0, 1, len(set(types))))
    type_color = {t: colors[i] for i, t in enumerate(sorted(set(types)))}

    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    fig.suptitle(f"Fairness Analysis: {result.approach_name}", fontsize=14)

    ax = axes[0, 0]
    bars = ax.bar(range(len(deltas)), deltas, color=[type_color[t] for t in types])
    ax.axhline(0, color="red", linestyle="--", linewidth=0.5)
    ax.set_xlabel("Household")
    ax.set_ylabel("Cost delta (€)")
    ax.set_title("Per-Household Cost Difference (Coord - Baseline)")
    neg = sum(1 for d in deltas if d < 0)
    pos = sum(1 for d in deltas if d > 0)
    ax.text(0.98, 0.95, f"Better: {neg} | Worse: {pos}",
            transform=ax.transAxes, ha="right", va="top",
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5))

    ax = axes[0, 1]
    fm = result.fairness_metrics
    per_type = fm.get("per_type", {})
    if per_type:
        t_labels = []
        t_means = []
        t_maxs = []
        for t in sorted(per_type.keys()):
            stats = per_type[t]
            t_labels.append(t)
            t_means.append(stats["mean_delta_ct"] / 100)
            t_maxs.append(stats["max_delta_ct"] / 100)
        x = range(len(t_labels))
        width = 0.35
        ax.bar([i - width/2 for i in x], t_means, width, label="Mean", color="steelblue")
        ax.bar([i + width/2 for i in x], t_maxs, width, label="Max", color="coral")
        ax.axhline(0, color="red", linestyle="--", linewidth=0.5)
        ax.set_xticks(x)
        ax.set_xticklabels(t_labels, rotation=45)
        ax.set_ylabel("Cost delta (€)")
        ax.set_title("Per-Type Cost Impact")
        ax.legend()

    ax = axes[1, 0]
    gs = result.grid_summary
    metrics_labels = ["Max trafo\nloading %", "P95 trafo\nloading %", "Hours\n>100%"]
    metrics_values = [gs["max_trafo_loading_pct"], gs["p95_trafo_loading_pct"],
                      gs["hours_above_100pct"]]
    ax.bar(metrics_labels, metrics_values, color="seagreen")
    ax.set_title("Grid Impact")
    for i, v in enumerate(metrics_values):
        ax.text(i, v + 0.5, f"{v:.1f}", ha="center", fontsize=9)

    ax = axes[1, 1]
    cs = result.comms_summary
    comms_labels = ["Msg/agent/hour", "Duty cycle %"]
    comms_values = [cs["msg_per_agent_per_hour"], cs["duty_cycle_used_pct"]]
    ax.bar(comms_labels, comms_values, color="mediumpurple")
    ax.set_title("Communication")
    for i, v in enumerate(comms_values):
        ax.text(i, v + 0.1, f"{v:.2f}", ha="center", fontsize=9)

    plt.tight_layout()
    plt.savefig(output_dir / f"fairness_{result.config['approach']}.png", dpi=150)
    plt.close()
