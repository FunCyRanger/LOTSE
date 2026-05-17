#!/usr/bin/env python3
import argparse
import yaml
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from simulation.core.loop import run_simulation
from simulation.output.plots import generate_plots


def main():
    parser = argparse.ArgumentParser(description="LOTSE Fairness Simulation")
    parser.add_argument("--config", "-c", default="configs/default.yaml",
                        help="Configuration file (YAML)")
    parser.add_argument("--approach", "-a", default=None,
                        help="Fairness approach to test (A-I). Overrides config.")
    parser.add_argument("--days", "-d", type=int, default=None,
                        help="Duration in days. Overrides config.")
    parser.add_argument("--output", "-o", default="output",
                        help="Output directory")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print progress")
    args = parser.parse_args()

    config_path = Path(__file__).parent / args.config if not os.path.isabs(args.config) else Path(args.config)
    with open(config_path) as f:
        config = yaml.safe_load(f)

    if args.approach:
        config["approach"] = args.approach.upper()
    if args.days:
        config["duration_days"] = args.days

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.verbose:
        print(f"Running approach {config['approach']} "
              f"({config.get('n_households', 10)} households, "
              f"{config.get('duration_days', 365)} days)")

    result = run_simulation(config)

    fm = result.fairness_metrics
    gs = result.grid_summary
    cs = result.comms_summary

    print(f"\n{'='*60}")
    print(f"  Approach: {result.approach_name}")
    print(f"{'='*60}")
    print(f"\n  FR-06 (Economic Fairness):")
    print(f"    Max cost delta:     {fm['max_cost_delta_ct']:.2f} ct")
    print(f"    Mean cost delta:    {fm['mean_cost_delta_ct']:.2f} ct")
    print(f"    FR-06 violations:   {fm['violations_count']}")
    print(f"    Gini coefficient:   {fm['gini']:.3f}")
    print(f"    Total savings:      {fm['total_savings_ct']:.0f} ct")

    print(f"\n  Grid:")
    print(f"    Max transformer:    {gs['max_trafo_loading_pct']:.1f}%")
    print(f"    P95 transformer:    {gs['p95_trafo_loading_pct']:.1f}%")
    print(f"    Hours >100%:        {gs['hours_above_100pct']}")

    print(f"\n  Communication:")
    print(f"    Msg/agent/hour:     {cs['msg_per_agent_per_hour']:.2f}")
    print(f"    Duty cycle used:    {cs['duty_cycle_used_pct']:.3f}%")
    print(f"    Duty cycle OK:      {cs['duty_cycle_ok']}")
    print()

    per_type = fm.get("per_type", {})
    if per_type:
        print(f"  Per-type cost deltas:")
        for t, stats in sorted(per_type.items()):
            print(f"    {t}: mean={stats['mean_delta_ct']:.1f}ct, "
                  f"max={stats['max_delta_ct']:.1f}ct, "
                  f"violations={stats['violations']}")

    result_path = output_dir / f"result_{config['approach']}.yaml"
    with open(result_path, "w") as f:
        yaml.dump({
            "approach": config["approach"],
            "approach_name": result.approach_name,
            "n_households": config["n_households"],
            "duration_days": config["duration_days"],
            "fairness": {k: v for k, v in fm.items() if k != "per_type"},
            "per_type": {k: v for k, v in per_type.items()},
            "grid": gs,
            "comms": cs,
            "per_agent": result.per_agent,
        }, f, default_flow_style=False)

    print(f"\n  Results saved to {result_path}")

    try:
        generate_plots(result, output_dir)
        print(f"  Plots saved to {output_dir}/")
    except Exception as e:
        print(f"  Plot generation skipped: {e}")

    return 0 if fm["violations_count"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
