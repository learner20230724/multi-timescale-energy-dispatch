from __future__ import annotations

import argparse
import json
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .config import RunConfig, build_default_model
from .intraday import run_intraday
from .optimization import run_day_ahead


def _to_serializable(value: Any) -> Any:
    if is_dataclass(value):
        return {field.name: _to_serializable(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, dict):
        return {key: _to_serializable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_serializable(item) for item in value]
    return value


def _print_summary(results: dict[str, Any]) -> None:
    dayahead = results["dayahead"]
    intraday = results["intraday"]
    print("\nDay-ahead summary / 日前调度总结")
    print(f"  Total cost / 总成本: {dayahead.total_cost:.2f} CNY")
    print(f"  Total carbon / 总碳排放: {dayahead.total_carbon:.2f} tCO2")
    print(f"  Curtailment / 弃电率: {100 * dayahead.curtailment_ratio:.4f}%")
    print(f"  Max balance error / 最大功率平衡误差: {np.max(np.abs(dayahead.power_balance)):.4f} MW")
    print(f"  Final SOC / 最终SOC: {dayahead.SOC[-1]:.2f} MWh")

    print("\nIntraday summary / 日内调度总结")
    print(f"  Switch count / 储能切换次数: {intraday['switch_count']}")
    print(f"  Charge RMS deviation / 充电RMS偏差: {intraday['charge_rms_dev']:.4f} MW")
    print(f"  Discharge RMS deviation / 放电RMS偏差: {intraday['discharge_rms_dev']:.4f} MW")
    print(f"  SOC RMS deviation / SOC RMS偏差: {intraday['soc_rms_dev']:.4f} MWh")
    print(f"  Net RMS intraday / 日内净不平衡RMS: {intraday['net_rms_intraday']:.4f} MW")
    print(f"  Net RMS day-ahead / 若直接执行日前调度: {intraday['net_rms_if_day_ahead']:.4f} MW")
    if intraday["fallback_used"]:
        print("  Fallback used / 已应用后备方案: keep day-ahead storage trajectory")


def _plot_results(results: dict[str, Any]) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError("matplotlib is required for plotting. Install with `pip install .[plot]`.") from exc

    final_obj = results["final_population_objectives"]
    pareto_obj = results["pareto_objectives"]
    dayahead = results["dayahead"]
    intraday = results["intraday"]

    fig = plt.figure(figsize=(10, 6))
    ax = fig.add_subplot(111, projection="3d")
    ax.scatter(final_obj[:, 0], final_obj[:, 1], final_obj[:, 2] * 100, s=18, c="tab:blue", label="Population")
    ax.scatter(pareto_obj[:, 0], pareto_obj[:, 1], pareto_obj[:, 2] * 100, s=40, c="tab:red", label="Pareto")
    ax.scatter(
        [dayahead.total_cost],
        [dayahead.total_carbon],
        [dayahead.curtailment_ratio * 100],
        s=80,
        c="tab:green",
        marker="s",
        label="Selected",
    )
    ax.set_xlabel("Total cost")
    ax.set_ylabel("Total carbon")
    ax.set_zlabel("Curtailment (%)")
    ax.set_title("Pareto front / 帕累托前沿")
    ax.legend()

    fig2, axes = plt.subplots(2, 2, figsize=(12, 8))
    axes[0, 0].plot(dayahead.P_wind_actual, label="Wind")
    axes[0, 0].plot(dayahead.P_solar_actual, label="Solar")
    axes[0, 0].plot(dayahead.P_thermal_total, label="Thermal")
    axes[0, 0].set_title("Day-ahead dispatch / 日前出力")
    axes[0, 0].legend()

    axes[0, 1].plot(dayahead.P_charge, label="Charge")
    axes[0, 1].plot(dayahead.P_discharge, label="Discharge")
    axes[0, 1].plot(dayahead.P_P2G, label="P2G")
    axes[0, 1].plot(dayahead.P_P2A, label="P2A")
    axes[0, 1].set_title("Flexible assets / 灵活资源")
    axes[0, 1].legend()

    axes[1, 0].plot(intraday["SOC_day_ahead"], label="Day-ahead SOC")
    axes[1, 0].plot(intraday["SOC_intraday"], label="Intraday SOC")
    axes[1, 0].set_title("SOC tracking / SOC跟踪")
    axes[1, 0].legend()

    axes[1, 1].plot(intraday["P_net_day_ahead"], label="Day-ahead")
    axes[1, 1].plot(intraday["P_net_intraday"], label="Intraday")
    axes[1, 1].set_title("Net imbalance / 净不平衡")
    axes[1, 1].legend()

    plt.tight_layout()
    plt.show()


def run_pipeline(config: RunConfig | None = None) -> dict[str, Any]:
    config = config or RunConfig()
    model = build_default_model(config.seed)
    day_ahead = run_day_ahead(model, config)
    intraday = run_intraday(model, day_ahead["best_metrics"], sigma=config.intraday_error_sigma, seed=config.seed)

    results = {
        "config": config,
        "model": model,
        "best_individual": day_ahead["best_individual"],
        "final_population_objectives": day_ahead["final_population_objectives"],
        "pareto_objectives": day_ahead["pareto_objectives"],
        "pareto_history": day_ahead["pareto_history"],
        "selection_details": day_ahead["selection_details"],
        "dayahead": day_ahead["best_metrics"],
        "intraday": intraday,
    }

    if config.verbose:
        _print_summary(results)
    if config.enable_plots:
        _plot_results(results)
    return results


def main(argv: list[str] | None = None) -> int:
    import sys, io
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Run the multi-timescale energy dispatch workflow.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--pop-size", type=int, default=80)
    parser.add_argument("--max-gen", type=int, default=100)
    parser.add_argument("--crossover-prob", type=float, default=0.85)
    parser.add_argument("--mutation-prob", type=float, default=0.06)
    parser.add_argument("--intraday-error-sigma", type=float, default=0.02)
    parser.add_argument("--plots", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--output", type=Path, help="Optional JSON output path.")
    args = parser.parse_args(argv)

    config = RunConfig(
        seed=args.seed,
        pop_size=args.pop_size,
        max_gen=args.max_gen,
        crossover_prob=args.crossover_prob,
        mutation_prob=args.mutation_prob,
        intraday_error_sigma=args.intraday_error_sigma,
        enable_plots=args.plots,
        verbose=not args.quiet,
    )
    results = run_pipeline(config)

    if args.output is not None:
        args.output.write_text(json.dumps(_to_serializable(results), indent=2, ensure_ascii=False), encoding="utf-8")
        if not args.quiet:
            print(f"\nSaved results to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
