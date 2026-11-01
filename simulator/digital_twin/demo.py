"""Digital shadow demo on a synthetic plant.

The "plant" is the full ADM1 CSTR running with hidden parameters
(``SyntheticScenario.hidden_parameter_overrides``). Its outputs pass through
a noisy sensor model. The twin runs open loop with nominal parameters and
the measured operating inputs only, so the tracking error it shows is the
gap closed by the optional Phase 2 augmented UKF.
Plant truth, sensors and twin all use the physical observable bases in
``contracts.py`` (dry normal gas, dry CH4, species-sum alkalinity, NH4+-N).

Usage::

    python -m simulator.digital_twin.demo --scenario overload_recovery
    python -m simulator.digital_twin.demo --all
    python -m simulator.digital_twin.demo --all --estimator ukf --identifiability
"""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd

from simulator.digital_twin.contracts import MEASUREMENT_COLUMNS, InfluentWindow, WindowResult
from simulator.digital_twin.dataset import to_daily, write_measurements
from simulator.digital_twin.engine import TwinEngine
from simulator.digital_twin.inputs import observed_windows
from simulator.digital_twin.measurement import default_sensor_suite, measure
from simulator.digital_twin.metrics import tracking_report
from simulator.digital_twin.scenarios import SyntheticScenario, base_influent_values, build_windows, default_scenarios, influent_cod

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "digital_twin_runs"
OUTPUT_COLUMNS = ("biogas_m3_d", "ch4_fraction", "ph", "vfa_kg_cod_m3", "alkalinity_kmol_m3", "nh4_kg_n_m3")


def stitch(results: Sequence[WindowResult], windows: Sequence[InfluentWindow]) -> tuple[list[float], dict[str, list[float]], dict[str, list[float]]]:
    """Join window results into one series and repeat each window's inputs on its time points.

    The first point of every window after the first duplicates the previous
    window's last point, so it is dropped.
    """
    time_days: list[float] = []
    outputs: dict[str, list[float]] = {name: [] for name in OUTPUT_COLUMNS}
    inputs: dict[str, list[float]] = {"q_in_m3_d": [], "temperature_c": [], "cod_in_kg_m3": []}
    for index, (result, window) in enumerate(zip(results, windows, strict=True)):
        start = 0 if index == 0 else 1
        points = result.time_days[start:]
        time_days.extend(points)
        for name in OUTPUT_COLUMNS:
            outputs[name].extend(result.outputs[name][start:])
        cod = influent_cod(window.influent_values)
        inputs["q_in_m3_d"].extend([window.flow_m3_day] * len(points))
        inputs["temperature_c"].extend([window.temperature_c] * len(points))
        inputs["cod_in_kg_m3"].extend([cod] * len(points))
    return time_days, outputs, inputs


def run_scenario(
    name: str,
    scenario: SyntheticScenario,
    *,
    seed: int = 0,
    warmup_days: float = 200.0,
    twin_influent: str = "observed",
    estimator: str = "open_loop",
    assess_identifiability: bool = False,
) -> dict[str, object]:
    """Run plant and nominal shadow, optionally assimilating observations.

    ``twin_influent="observed"`` (default) feeds the twin only measured flow,
    temperature and weekly COD. ``"oracle"`` feeds it the true influent, which
    isolates the effect of the hidden parameters.
    """
    started = time.perf_counter()
    if estimator not in ("open_loop", "ukf"):
        raise ValueError("estimator must be 'open_loop' or 'ukf'")
    windows = build_windows(scenario)

    plant = TwinEngine(volume_m3=scenario.volume_m3, parameter_overrides=scenario.hidden_parameter_overrides)
    plant_state = plant.initial_state(windows[0], warmup_days=warmup_days)
    plant_results = plant.run(plant_state, windows)
    time_days, true_outputs, inputs = stitch(plant_results, windows)
    measured = measure(time_days, true_outputs, inputs, default_sensor_suite(), seed=seed)

    # The twin knows neither the hidden parameters nor the plant's true state.
    if twin_influent == "observed":
        twin_windows = observed_windows(
            windows,
            measured,
            base_influent_values(),
            nominal_flow_m3_day=scenario.base_flow_m3_day,
            nominal_temperature_c=scenario.base_temperature_c,
        )
    elif twin_influent == "oracle":
        twin_windows = list(windows)
    else:
        raise ValueError("twin_influent must be 'observed' or 'oracle'")
    twin = TwinEngine(volume_m3=scenario.volume_m3)
    twin_state = twin.initial_state(twin_windows[0], warmup_days=warmup_days)
    twin_results = twin.run(twin_state, twin_windows)
    twin_time, twin_outputs, twin_inputs = stitch(twin_results, twin_windows)
    simulated = to_daily(_frame(twin_time, twin_outputs, twin_inputs))
    truth = to_daily(_frame(time_days, true_outputs, inputs))

    extra = {}
    if assess_identifiability:
        from simulator.digital_twin.identifiability import local_information

        extra["identifiability"] = local_information(twin, twin_state, twin_windows, measured)
    if estimator == "ukf":
        from simulator.digital_twin.estimator import TwinUKF

        filter_started = time.perf_counter()
        ukf = TwinUKF(twin, twin_state)
        estimated = ukf.run(twin_windows, measured)
        extra.update({
            "open_loop": simulated,
            "open_loop_report": tracking_report(measured, simulated[simulated.time_days < scenario.duration_days], columns=list(OUTPUT_COLUMNS)),
            "open_loop_truth_report": tracking_report(truth, simulated[simulated.time_days < scenario.duration_days], columns=list(OUTPUT_COLUMNS)),
            "parameter_history": pd.DataFrame(ukf.history),
            "assimilations": ukf.assimilations,
            "filter_runtime_seconds": time.perf_counter() - filter_started,
        })
        simulated = estimated
        final_state = ukf.state
    else:
        final_state = twin_results[-1].state
    return {
        **extra,
        "name": name,
        "estimator": estimator,
        "runtime_seconds": time.perf_counter() - started,
        "twin_influent": twin_influent,
        "measured": measured,
        "simulated": simulated,
        "truth": truth,
        "report": tracking_report(measured, simulated, columns=list(OUTPUT_COLUMNS)),
        "truth_report": tracking_report(truth, simulated, columns=list(OUTPUT_COLUMNS)),
        "final_twin_state": final_state,
    }


def _frame(time_days: list[float], outputs: dict[str, list[float]], inputs: dict[str, list[float]]) -> pd.DataFrame:
    frame = pd.DataFrame({"time_days": time_days, **outputs, **inputs})
    for column in MEASUREMENT_COLUMNS:
        if column not in frame:
            frame[column] = np.nan
    return frame[list(MEASUREMENT_COLUMNS)]


def save_outputs(run: dict[str, object], output_dir: Path) -> Path:
    target = output_dir / f"{run['name']}_{run['twin_influent']}"
    if run.get("estimator") == "ukf":
        target = target.with_name(target.name + "_ukf")
    target.mkdir(parents=True, exist_ok=True)
    write_measurements(run["measured"], target / "measured.csv")
    if run.get("estimator") == "ukf":
        write_measurements(run["open_loop"], target / "twin_open_loop.csv")
        write_measurements(run["simulated"], target / "twin_ukf_forecast.csv")
        run["parameter_history"].to_csv(target / "estimated_parameters.csv", index=False)
        comparison = {key: run[key] for key in ("open_loop_report", "open_loop_truth_report", "truth_report", "runtime_seconds", "filter_runtime_seconds", "assimilations")}
        (target / "comparison.json").write_text(json.dumps(comparison, indent=2), encoding="utf-8")
    else:
        write_measurements(run["simulated"], target / "twin_open_loop.csv")
    write_measurements(run["truth"], target / "plant_truth.csv")
    (target / "tracking_report.json").write_text(json.dumps(run["report"], indent=2), encoding="utf-8")
    if "identifiability" in run:
        (target / "identifiability.json").write_text(json.dumps(run["identifiability"], indent=2, allow_nan=False), encoding="utf-8")
    TwinEngine.save_state(run["final_twin_state"], target / "twin_state_final.json")
    _plot(run, target / "shadow.png")
    return target


def _plot(run: dict[str, object], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    measured, simulated, truth = run["measured"], run["simulated"], run["truth"]
    labels = {
        "biogas_m3_d": "Biogás seco [Nm³/d; 0 °C, 1 atm]",
        "ch4_fraction": "CH4 [fração seca]",
        "ph": "pH",
        "vfa_kg_cod_m3": "AGV [kgDQO/m³]",
        "alkalinity_kmol_m3": "Alcalinidade total [kmol carga/m³]",
        "nh4_kg_n_m3": "NH4+-N [kgN/m³]",
    }
    is_ukf = run.get("estimator") == "ukf"
    fig, axes = plt.subplots(4 if is_ukf else 3, 2, figsize=(12, 12 if is_ukf else 9), sharex=True)
    for ax, column in zip(axes.flat, OUTPUT_COLUMNS):
        ax.plot(truth["time_days"], truth[column], color="0.6", lw=1.2, label="planta (verdade)")
        ax.plot(simulated["time_days"], simulated[column], color="tab:blue", lw=1.5, label="UKF (previsão)" if is_ukf else "gêmeo (malha aberta)")
        ax.plot(measured["time_days"], measured[column], ".", color="tab:red", ms=4, label="medido")
        if is_ukf:
            ax.plot(run["open_loop"]["time_days"], run["open_loop"][column], color="tab:orange", lw=1, label="malha aberta")
        ax.set_ylabel(labels[column])
        ax.grid(alpha=0.3)
    if is_ukf:
        history = run["parameter_history"]
        for ax, name, label in zip(axes[-1], ("k_m_ac", "nitrogen_factor"), ("k_m_ac [d⁻¹]", "Fator N afluente (NH4Cl)"), strict=True):
            ax.plot(history.time_days, history[name], color="tab:blue")
            ax.fill_between(history.time_days, history[name + "_lower_2sigma"], history[name + "_upper_2sigma"], alpha=0.2, label="±2σ em log")
            ax.set_ylabel(label)
            ax.grid(alpha=0.3)
            ax.legend(fontsize=8)
    axes[0, 0].legend(fontsize=8)
    for ax in axes[-1]:
        ax.set_xlabel("tempo [d]")
    fig.suptitle(f"Sombra digital — {run['name']} (afluente do gêmeo: {run['twin_influent']})")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def main(argv: Sequence[str] | None = None) -> int:
    scenarios = default_scenarios()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--scenario", choices=sorted(scenarios), default="overload_recovery")
    group.add_argument("--all", action="store_true")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--twin-influent", choices=("observed", "oracle"), default="observed")
    parser.add_argument("--estimator", choices=("open_loop", "ukf"), default="open_loop")
    parser.add_argument("--identifiability", action="store_true", help="Assess conditional local information before filtering")
    args = parser.parse_args(argv)

    names = sorted(scenarios) if args.all else [args.scenario]
    for name in names:
        run = run_scenario(name, scenarios[name], seed=args.seed, twin_influent=args.twin_influent, estimator=args.estimator, assess_identifiability=args.identifiability)
        target = save_outputs(run, args.out)
        print(f"\n== {name} -> {target.name}/")
        if args.estimator == "ukf":
            last = run["parameter_history"].iloc[-1]
            print(f"  k_m_ac={last.k_m_ac:.3f} ± {last.k_m_ac_sigma:.3f}; fator N={last.nitrogen_factor:.3f} ± {last.nitrogen_factor_sigma:.3f}; UKF={run['filter_runtime_seconds']:.1f}s")
        for column, stats in run["report"].items():
            print(f"  {column:<20} n={stats['n']:<4.0f} rmse={stats['rmse']:.4g}  mape={stats['mape']:.2f}%  bias={stats['bias']:+.4g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
