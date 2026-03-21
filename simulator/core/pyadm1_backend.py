from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from simulator.core.defaults import make_default_feed, make_default_initial_state, make_default_kinetics
from simulator.core.models import FeedDefinition, InitialState, KineticParameters, OperatingConditions, SimulationConfig

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VENDOR_PYADM1_SRC = PROJECT_ROOT / "vendor" / "PyADM1" / "src"
PYADM1_RUNTIME_ROOT = PROJECT_ROOT / "simulator" / ".pyadm1_runtime"
PYADM1_RESULTS_FILENAME = "dynamic_out.csv"
PYADM1_GASFLOW_FILENAME = "gasflow_out.csv"
RUNTIME_TRANSIENT_FILENAMES = (
    "digester_influent.csv",
    "digester_initial.csv",
    "PyADM1_runtime.py",
    PYADM1_RESULTS_FILENAME,
    PYADM1_GASFLOW_FILENAME,
)
RUNTIME_LOCK_FILENAME = ".runtime.lock"
RUNTIME_SLOT_GLOB = "slot_*"
RUNTIME_SLOT_COUNT = 8
RUNTIME_SLOT_WAIT_SECONDS = 5.0
RUNTIME_SLOT_POLL_INTERVAL_SECONDS = 0.1

INFLUENT_COLUMNS = [
    "time",
    "S_su",
    "S_aa",
    "S_fa",
    "S_va",
    "S_bu",
    "S_pro",
    "S_ac",
    "S_h2",
    "S_ch4",
    "S_IC",
    "S_IN",
    "S_I",
    "X_xc",
    "X_ch",
    "X_pr",
    "X_li",
    "X_su",
    "X_aa",
    "X_fa",
    "X_c4",
    "X_pro",
    "X_ac",
    "X_h2",
    "X_I",
    "S_cation",
    "S_anion",
    "Q",
    "T (C)",
    "S_H_ion",
    "S_va_ion",
    "S_bu_ion",
    "S_pro_ion",
    "S_ac_ion",
    "S_hco3_ion",
    "S_co2",
    "S_nh3",
    "S_nh4_ion",
    "S_gas_h2",
    "S_gas_ch4",
    "S_gas_co2",
]
INITIAL_COLUMNS = [
    "S_su",
    "S_aa",
    "S_fa",
    "S_va",
    "S_bu",
    "S_pro",
    "S_ac",
    "S_h2",
    "S_ch4",
    "S_IC",
    "S_IN",
    "S_I",
    "X_xc",
    "X_ch",
    "X_pr",
    "X_li",
    "X_su",
    "X_aa",
    "X_fa",
    "X_c4",
    "X_pro",
    "X_ac",
    "X_h2",
    "X_I",
    "S_cation",
    "S_anion",
    "S_H_ion",
    "S_va_ion",
    "S_bu_ion",
    "S_pro_ion",
    "S_ac_ion",
    "S_hco3_ion",
    "S_co2",
    "S_nh3",
    "S_nh4_ion",
    "S_gas_h2",
    "S_gas_ch4",
    "S_gas_co2",
]
RESULT_COLUMNS = [
    "S_su",
    "S_aa",
    "S_fa",
    "S_va",
    "S_bu",
    "S_pro",
    "S_ac",
    "S_h2",
    "S_ch4",
    "S_IC",
    "S_IN",
    "S_I",
    "X_xc",
    "X_ch",
    "X_pr",
    "X_li",
    "X_su",
    "X_aa",
    "X_fa",
    "X_c4",
    "X_pro",
    "X_ac",
    "X_h2",
    "X_I",
    "S_cation",
    "S_anion",
    "pH",
    "S_va_ion",
    "S_bu_ion",
    "S_pro_ion",
    "S_ac_ion",
    "S_hco3_ion",
    "S_co2",
    "S_nh3",
    "S_nh4_ion",
    "S_gas_h2",
    "S_gas_ch4",
    "S_gas_co2",
]

R_GAS = 0.083145
P_ATM_BAR = 1.013
V_GAS_RATIO = 300.0 / 3400.0

FEED_GROUPS: dict[str, tuple[list[str], dict[str, float]]] = {
    "particulate_cod": (["X_xc", "X_ch", "X_pr", "X_li", "X_I"], {}),
    "soluble_cod": (["S_su", "S_aa", "S_fa", "S_I"], {"S_su": 0.55, "S_aa": 0.2, "S_fa": 0.1, "S_I": 0.15}),
    "acetate": (["S_ac", "S_ac_ion"], {"S_ac": 1.0}),
    "propionate": (["S_pro", "S_pro_ion"], {"S_pro": 1.0}),
    "hydrogen": (["S_h2", "S_gas_h2"], {"S_h2": 1.0}),
    "inorganic_nitrogen": (["S_IN", "S_nh3", "S_nh4_ion"], {"S_IN": 0.94, "S_nh3": 0.02, "S_nh4_ion": 0.04}),
    "alkalinity": (["S_IC", "S_hco3_ion", "S_co2"], {"S_IC": 0.52, "S_hco3_ion": 0.43, "S_co2": 0.05}),
}
INITIAL_GROUPS: dict[str, tuple[list[str], dict[str, float]]] = {
    "particulate_cod": (["X_xc", "X_ch", "X_pr", "X_li", "X_I"], {}),
    "soluble_cod": (["S_su", "S_aa", "S_fa", "S_I"], {"S_su": 0.55, "S_aa": 0.2, "S_fa": 0.1, "S_I": 0.15}),
    "acetate": (["S_ac", "S_ac_ion"], {"S_ac": 0.98, "S_ac_ion": 0.02}),
    "propionate": (["S_pro", "S_pro_ion"], {"S_pro": 0.98, "S_pro_ion": 0.02}),
    "hydrogen": (["S_h2", "S_gas_h2"], {"S_h2": 0.98, "S_gas_h2": 0.02}),
    "acidogens": (["X_su", "X_aa", "X_fa", "X_c4"], {"X_su": 0.4118, "X_aa": 0.2353, "X_fa": 0.1176, "X_c4": 0.2353}),
    "propionate_biomass": (["X_pro"], {"X_pro": 1.0}),
    "acetoclastic_biomass": (["X_ac"], {"X_ac": 1.0}),
    "hydrogenotrophic_biomass": (["X_h2"], {"X_h2": 1.0}),
    "inorganic_nitrogen": (["S_IN", "S_nh3", "S_nh4_ion"], {"S_IN": 0.9, "S_nh3": 0.03, "S_nh4_ion": 0.07}),
    "alkalinity": (["S_IC", "S_hco3_ion", "S_co2"], {"S_IC": 0.52, "S_hco3_ion": 0.43, "S_co2": 0.05}),
}


@lru_cache(maxsize=1)
def _vendor_source_text() -> str:
    return (VENDOR_PYADM1_SRC / "PyADM1.py").read_text(encoding="utf-8")


@lru_cache(maxsize=4)
def _load_template_row(filename: str) -> dict[str, Any]:
    return pd.read_csv(VENDOR_PYADM1_SRC / filename).iloc[0].to_dict()


def simulate_with_pyadm1(
    *,
    operating_conditions: OperatingConditions,
    feed: FeedDefinition,
    initial_state: InitialState,
    parameters: KineticParameters,
    simulation: SimulationConfig,
) -> dict[str, Any]:
    time_grid = np.linspace(0.0, simulation.duration_days, simulation.evaluation_points)
    influent = _build_influent_frame(time_grid=time_grid, feed=feed, operating_conditions=operating_conditions)
    initial = _build_initial_frame(initial_state=initial_state, feed=feed)
    return simulate_with_pyadm1_frames(
        operating_conditions=operating_conditions,
        feed=feed,
        parameters=parameters,
        simulation=simulation,
        influent_frame=influent,
        initial_frame=initial,
    )


def simulate_with_pyadm1_frames(
    *,
    operating_conditions: OperatingConditions,
    feed: FeedDefinition,
    parameters: KineticParameters,
    simulation: SimulationConfig,
    influent_frame: pd.DataFrame,
    initial_frame: pd.DataFrame,
) -> dict[str, Any]:
    if not VENDOR_PYADM1_SRC.exists():
        raise FileNotFoundError(f"PyADM1 vendor source was not found in {VENDOR_PYADM1_SRC}")

    influent = _coerce_frame(frame=influent_frame, columns=INFLUENT_COLUMNS, frame_name="influent_frame")
    initial = _coerce_frame(frame=initial_frame, columns=INITIAL_COLUMNS, frame_name="initial_frame")
    return _execute_pyadm1_case(
        operating_conditions=operating_conditions,
        feed=feed,
        parameters=parameters,
        simulation=simulation,
        influent=influent,
        initial=initial,
    )


def _execute_pyadm1_case(
    *,
    operating_conditions: OperatingConditions,
    feed: FeedDefinition,
    parameters: KineticParameters,
    simulation: SimulationConfig,
    influent: pd.DataFrame,
    initial: pd.DataFrame,
) -> dict[str, Any]:
    runtime_dir = _prepare_runtime_dir()
    script_path = runtime_dir / "PyADM1_runtime.py"
    success = False

    try:
        influent.to_csv(runtime_dir / "digester_influent.csv", index=False)
        initial.to_csv(runtime_dir / "digester_initial.csv", index=False)
        script_path.write_text(
            _patched_pyadm1_source(
                operating_conditions=operating_conditions,
                feed=feed,
                parameters=parameters,
                simulation=simulation,
            ),
            encoding="utf-8",
        )
        _run_pyadm1(script_path=script_path, runtime_dir=runtime_dir)
        results, gasflow = _read_runtime_outputs(runtime_dir)
        profiles = _translate_profiles(
            results=results,
            gasflow=gasflow,
            operating_conditions=operating_conditions,
        )
        final_internal_state = [float(results.iloc[-1][column]) for column in RESULT_COLUMNS]
        metadata = {
            "segment_count": 1,
            "solver_status": f"PyADM1 completed with {simulation.solver}",
            "final_internal_state": final_internal_state,
            "pyadm1_runtime": "subprocess",
            "pyadm1_source": str(VENDOR_PYADM1_SRC / "PyADM1.py"),
            "pyadm1_state_columns": RESULT_COLUMNS,
        }
        success = True
        return {
            "time_days": [float(value) for value in influent["time"].tolist()],
            "profiles": profiles,
            "metadata": metadata,
        }
    except Exception as exc:
        raise RuntimeError(f"PyADM1 execution failed; runtime preserved in {runtime_dir}") from exc
    finally:
        if success:
            _cleanup_runtime_dir(runtime_dir)
        _release_runtime_dir(runtime_dir)


def _coerce_frame(*, frame: pd.DataFrame, columns: list[str], frame_name: str) -> pd.DataFrame:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        missing_text = ", ".join(missing)
        raise ValueError(f"{frame_name} is missing required columns: {missing_text}")
    coerced = frame.loc[:, columns].copy()
    for column in columns:
        coerced[column] = coerced[column].astype(float)
    return coerced


def _prepare_runtime_dir() -> Path:
    PYADM1_RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    _ensure_runtime_slots()
    _clear_runtime_files(PYADM1_RUNTIME_ROOT)
    slot_dirs = _runtime_slot_dirs()

    deadline = time.monotonic() + RUNTIME_SLOT_WAIT_SECONDS
    while True:
        for slot_dir in slot_dirs:
            if _try_acquire_runtime_slot(slot_dir):
                _clear_runtime_files(slot_dir)
                return slot_dir
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"No PyADM1 runtime slots are available in {PYADM1_RUNTIME_ROOT}; all {len(slot_dirs)} slots are currently in use."
            )
        time.sleep(RUNTIME_SLOT_POLL_INTERVAL_SECONDS)


def _ensure_runtime_slots() -> None:
    for index in range(1, RUNTIME_SLOT_COUNT + 1):
        (PYADM1_RUNTIME_ROOT / f"slot_{index:02d}").mkdir(parents=True, exist_ok=True)


def _runtime_slot_dirs() -> list[Path]:
    return sorted(path for path in PYADM1_RUNTIME_ROOT.glob(RUNTIME_SLOT_GLOB) if path.is_dir())


def _try_acquire_runtime_slot(runtime_dir: Path) -> bool:
    lock_path = runtime_dir / RUNTIME_LOCK_FILENAME
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(str(os.getpid()))
    return True


def _clear_runtime_files(runtime_dir: Path) -> None:
    for filename in RUNTIME_TRANSIENT_FILENAMES:
        (runtime_dir / filename).unlink(missing_ok=True)
    shutil.rmtree(runtime_dir / "__pycache__", ignore_errors=True)


def _cleanup_runtime_dir(runtime_dir: Path) -> None:
    _clear_runtime_files(runtime_dir)


def _release_runtime_dir(runtime_dir: Path) -> None:
    (runtime_dir / RUNTIME_LOCK_FILENAME).unlink(missing_ok=True)


def _build_influent_frame(
    *,
    time_grid: np.ndarray,
    feed: FeedDefinition,
    operating_conditions: OperatingConditions,
) -> pd.DataFrame:
    template_row = _load_template_row("digester_influent.csv")
    baseline_feed = make_default_feed()
    row = _scaled_row(
        template_row=template_row,
        value_map={
            "particulate_cod": feed.particulate_cod,
            "soluble_cod": feed.soluble_cod,
            "acetate": feed.acetate,
            "propionate": feed.propionate,
            "hydrogen": feed.hydrogen,
            "inorganic_nitrogen": _kg_n_to_kmol_n(feed.inorganic_nitrogen),
            "alkalinity": feed.alkalinity,
        },
        baseline_map={
            "particulate_cod": baseline_feed.particulate_cod,
            "soluble_cod": baseline_feed.soluble_cod,
            "acetate": baseline_feed.acetate,
            "propionate": baseline_feed.propionate,
            "hydrogen": baseline_feed.hydrogen,
            "inorganic_nitrogen": _kg_n_to_kmol_n(baseline_feed.inorganic_nitrogen),
            "alkalinity": baseline_feed.alkalinity,
        },
        groups=FEED_GROUPS,
    )
    row["Q"] = float(feed.flow_rate_m3_day or (operating_conditions.volume_m3 / operating_conditions.hrt_days))
    row["T (C)"] = float(operating_conditions.temperature_c)
    row["S_H_ion"] = 10 ** (-feed.ph)
    return pd.DataFrame(
        [{**row, "time": float(time_value)} for time_value in time_grid],
        columns=INFLUENT_COLUMNS,
    )


def _build_initial_frame(*, initial_state: InitialState, feed: FeedDefinition) -> pd.DataFrame:
    template_row = _load_template_row("digester_initial.csv")
    baseline_feed = make_default_feed()
    baseline_initial = make_default_initial_state(baseline_feed)
    row = _scaled_row(
        template_row=template_row,
        value_map={
            "particulate_cod": initial_state.particulate_cod,
            "soluble_cod": initial_state.soluble_cod,
            "acetate": initial_state.acetate,
            "propionate": initial_state.propionate,
            "hydrogen": initial_state.hydrogen,
            "acidogens": initial_state.acidogens,
            "propionate_biomass": initial_state.propionate_biomass,
            "acetoclastic_biomass": initial_state.acetoclastic_biomass,
            "hydrogenotrophic_biomass": initial_state.hydrogenotrophic_biomass,
            "inorganic_nitrogen": _kg_n_to_kmol_n(initial_state.inorganic_nitrogen),
            "alkalinity": initial_state.alkalinity,
        },
        baseline_map={
            "particulate_cod": baseline_initial.particulate_cod,
            "soluble_cod": baseline_initial.soluble_cod,
            "acetate": baseline_initial.acetate,
            "propionate": baseline_initial.propionate,
            "hydrogen": baseline_initial.hydrogen,
            "acidogens": baseline_initial.acidogens,
            "propionate_biomass": baseline_initial.propionate_biomass,
            "acetoclastic_biomass": baseline_initial.acetoclastic_biomass,
            "hydrogenotrophic_biomass": baseline_initial.hydrogenotrophic_biomass,
            "inorganic_nitrogen": _kg_n_to_kmol_n(baseline_initial.inorganic_nitrogen),
            "alkalinity": baseline_initial.alkalinity,
        },
        groups=INITIAL_GROUPS,
    )
    row["S_H_ion"] = 10 ** (-feed.ph)
    row["S_nh4_ion"] = max(row["S_IN"] - row["S_nh3"], 1e-9)
    row["S_co2"] = max(row["S_IC"] - row["S_hco3_ion"], 1e-9)
    return pd.DataFrame([row], columns=INITIAL_COLUMNS)


def _scaled_row(
    *,
    template_row: dict[str, Any],
    value_map: dict[str, float],
    baseline_map: dict[str, float],
    groups: dict[str, tuple[list[str], dict[str, float]]],
) -> dict[str, float]:
    row = {key: float(template_row.get(key, 0.0) or 0.0) for key in template_row}
    for group_name, (columns, fallback_weights) in groups.items():
        target_value = float(value_map[group_name])
        baseline_value = float(baseline_map[group_name])
        template_total = float(sum(max(row.get(column, 0.0), 0.0) for column in columns))
        if template_total > 0.0 and baseline_value > 0.0:
            scale = target_value / baseline_value
            for column in columns:
                row[column] = max(row.get(column, 0.0), 0.0) * scale
            continue
        weights = fallback_weights or {column: 1.0 / len(columns) for column in columns}
        weight_total = sum(weights.values())
        for column in columns:
            row[column] = target_value * (weights.get(column, 0.0) / weight_total)
    return row


def _patched_pyadm1_source(
    *,
    operating_conditions: OperatingConditions,
    feed: FeedDefinition,
    parameters: KineticParameters,
    simulation: SimulationConfig,
) -> str:
    source = _vendor_source_text()
    source = _replace_literal(
        source,
        old="import pandas as pd",
        new=(
            "import pandas as pd\n"
            "if not hasattr(pd.DataFrame, 'append'):\n"
            "    def _compat_append(self, other, ignore_index=False, **kwargs):\n"
            "        if isinstance(other, dict):\n"
            "            other = pd.DataFrame([other])\n"
            "        elif not isinstance(other, pd.DataFrame):\n"
            "            other = pd.DataFrame(other)\n"
            "        return pd.concat([self, other], ignore_index=ignore_index)\n"
            "    pd.DataFrame.append = _compat_append\n"
        ),
        label="pandas append shim",
    )
    source = _replace_literal(
        source,
        old="import matplotlib.pyplot as plt",
        new="import matplotlib\nmatplotlib.use('Agg')\nimport matplotlib.pyplot as plt",
        label="matplotlib backend",
    )
    source = _replace_literal(
        source,
        old="  r = scipy.integrate.solve_ivp(ADM1_ODE, t_step, state_zero, method= solvermethod)",
        new=(
            "  r = scipy.integrate.solve_ivp("
            f"ADM1_ODE, t_step, state_zero, method=solvermethod, rtol={simulation.rtol!r}, atol={simulation.atol!r})"
        ),
        label="solve_ivp tolerances",
    )

    flow_rate = float(feed.flow_rate_m3_day or (operating_conditions.volume_m3 / operating_conditions.hrt_days))
    temperature_k = operating_conditions.temperature_c + 273.15
    liquid_volume = operating_conditions.volume_m3
    gas_volume = max(liquid_volume * V_GAS_RATIO, 1.0)
    default_kinetics = make_default_kinetics()

    replacements = {
        "T_op": temperature_k,
        "T_ad": temperature_k,
        "V_liq": liquid_volume,
        "V_gas": gas_volume,
        "q_ad": flow_rate,
        "solvermethod": repr(simulation.solver),
        "initq": "{'q_ad' : [%s]}" % flow_rate,
        "k_hyd_ch": 10.0 * _ratio(parameters.k_hyd, default_kinetics.k_hyd),
        "k_hyd_pr": 10.0 * _ratio(parameters.k_hyd, default_kinetics.k_hyd),
        "k_hyd_li": 10.0 * _ratio(parameters.k_hyd, default_kinetics.k_hyd),
        "k_m_su": 30.0 * _ratio(parameters.k_m_su, default_kinetics.k_m_su),
        "k_m_pro": 13.0 * _ratio(parameters.k_m_pro, default_kinetics.k_m_pro),
        "k_m_ac": 8.0 * _ratio(parameters.k_m_ac, default_kinetics.k_m_ac),
        "k_m_h2": 35.0 * _ratio(parameters.k_m_h2, default_kinetics.k_m_h2),
        "K_S_su": 0.5 * _ratio(parameters.k_s_su, default_kinetics.k_s_su),
        "K_S_pro": 0.1 * _ratio(parameters.k_s_pro, default_kinetics.k_s_pro),
        "K_S_ac": 0.15 * _ratio(parameters.k_s_ac, default_kinetics.k_s_ac),
        "K_S_h2": 7e-6 * _ratio(parameters.k_s_h2, default_kinetics.k_s_h2),
        "Y_su": 0.1 * _ratio(parameters.acidogen_yield, default_kinetics.acidogen_yield),
        "Y_aa": 0.08 * _ratio(parameters.acidogen_yield, default_kinetics.acidogen_yield),
        "Y_fa": 0.06 * _ratio(parameters.acidogen_yield, default_kinetics.acidogen_yield),
        "Y_c4": 0.06 * _ratio(parameters.acidogen_yield, default_kinetics.acidogen_yield),
        "Y_pro": 0.04 * _ratio(parameters.propionate_yield, default_kinetics.propionate_yield),
        "Y_ac": 0.05 * _ratio(parameters.acetoclastic_yield, default_kinetics.acetoclastic_yield),
        "Y_h2": 0.06 * _ratio(parameters.hydrogenotrophic_yield, default_kinetics.hydrogenotrophic_yield),
        "k_dec_X_su": 0.02 * _ratio(parameters.decay_acidogens, default_kinetics.decay_acidogens),
        "k_dec_X_aa": 0.02 * _ratio(parameters.decay_acidogens, default_kinetics.decay_acidogens),
        "k_dec_X_fa": 0.02 * _ratio(parameters.decay_acidogens, default_kinetics.decay_acidogens),
        "k_dec_X_c4": 0.02 * _ratio(parameters.decay_acidogens, default_kinetics.decay_acidogens),
        "k_dec_X_pro": 0.02 * _ratio(parameters.decay_propionate_biomass, default_kinetics.decay_propionate_biomass),
        "k_dec_X_ac": 0.02 * _ratio(parameters.decay_acetoclastic, default_kinetics.decay_acetoclastic),
        "k_dec_X_h2": 0.02 * _ratio(parameters.decay_hydrogenotrophic, default_kinetics.decay_hydrogenotrophic),
        "k_L_a": 200.0 * _ratio(parameters.gas_stripping_h2, default_kinetics.gas_stripping_h2),
    }
    for name, value in replacements.items():
        source = _replace_assignment(source, name=name, value=value)
    return source + f"\n\ngasflow.to_csv('{PYADM1_GASFLOW_FILENAME}', index=False)\n"


def _replace_assignment(source: str, *, name: str, value: Any) -> str:
    pattern = re.compile(rf"^(?P<indent>\s*){re.escape(name)}\s*=.*$", flags=re.MULTILINE)
    match = pattern.search(source)
    if match is None:
        raise ValueError(f"Could not patch PyADM1 assignment for '{name}'")
    return pattern.sub(f"{match.group('indent')}{name} = {value}", source, count=1)


def _replace_literal(source: str, *, old: str, new: str, label: str) -> str:
    if old not in source:
        raise ValueError(f"Could not patch PyADM1 source for {label}")
    return source.replace(old, new, 1)


def _replace_regex(source: str, *, pattern: str, replacement: str, label: str) -> str:
    updated, count = re.subn(pattern, replacement, source)
    if count != 1:
        raise ValueError(f"Could not patch PyADM1 source for {label}")
    return updated


def _run_pyadm1(*, script_path: Path, runtime_dir: Path) -> None:
    env = os.environ.copy()
    env["MPLBACKEND"] = "Agg"
    completed = subprocess.run(
        [sys.executable, str(script_path.name)],
        cwd=str(runtime_dir),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        stdout = completed.stdout.strip()
        details = "\n".join(part for part in (stdout, stderr) if part)
        raise RuntimeError(f"PyADM1 subprocess failed with exit code {completed.returncode}. {details}")


def _read_runtime_outputs(runtime_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    results_path = runtime_dir / PYADM1_RESULTS_FILENAME
    gasflow_path = runtime_dir / PYADM1_GASFLOW_FILENAME
    if not results_path.exists():
        raise FileNotFoundError(f"PyADM1 did not produce {PYADM1_RESULTS_FILENAME}")
    if not gasflow_path.exists():
        raise FileNotFoundError(f"PyADM1 did not produce {PYADM1_GASFLOW_FILENAME}")
    return pd.read_csv(results_path), pd.read_csv(gasflow_path)


def _translate_profiles(
    *,
    results: pd.DataFrame,
    gasflow: pd.DataFrame,
    operating_conditions: OperatingConditions,
) -> dict[str, list[float]]:
    aligned_gasflow = gasflow.reset_index(drop=True)
    if len(aligned_gasflow) < len(results):
        aligned_gasflow = aligned_gasflow.reindex(range(len(results))).ffill().fillna(0.0)
    else:
        aligned_gasflow = aligned_gasflow.iloc[: len(results)].copy()

    temperature_k = operating_conditions.temperature_c + 273.15
    p_h2o = 0.0313 * np.exp(5290.0 * (1.0 / 298.15 - 1.0 / temperature_k))
    p_h2 = results["S_gas_h2"].to_numpy(dtype=float) * R_GAS * temperature_k / 16.0
    p_ch4 = results["S_gas_ch4"].to_numpy(dtype=float) * R_GAS * temperature_k / 64.0
    p_co2 = results["S_gas_co2"].to_numpy(dtype=float) * R_GAS * temperature_k
    p_total = np.maximum(p_h2 + p_ch4 + p_co2 + p_h2o, 1e-9)
    gas_normalization = p_total / P_ATM_BAR
    # The BSM2 reference publishes gas flow at atmospheric pressure, not at headspace pressure.
    biogas = np.maximum(aligned_gasflow["q_gas"].to_numpy(dtype=float) * gas_normalization, 0.0)
    methane = np.maximum(aligned_gasflow["q_ch4"].to_numpy(dtype=float) * gas_normalization, 0.0)
    co2 = np.maximum(biogas * (p_co2 / p_total), 0.0)
    hydrogen = np.maximum(biogas * (p_h2 / p_total), 0.0)
    particulate_cod = (
        results["X_xc"].to_numpy(dtype=float)
        + results["X_ch"].to_numpy(dtype=float)
        + results["X_pr"].to_numpy(dtype=float)
        + results["X_li"].to_numpy(dtype=float)
        + results["X_I"].to_numpy(dtype=float)
    )
    soluble_cod = (
        results["S_su"].to_numpy(dtype=float)
        + results["S_aa"].to_numpy(dtype=float)
        + results["S_fa"].to_numpy(dtype=float)
        + results["S_I"].to_numpy(dtype=float)
    )
    acidogens = (
        results["X_su"].to_numpy(dtype=float)
        + results["X_aa"].to_numpy(dtype=float)
        + results["X_fa"].to_numpy(dtype=float)
        + results["X_c4"].to_numpy(dtype=float)
    )
    propionate_biomass = results["X_pro"].to_numpy(dtype=float)
    acetate = results["S_ac"].to_numpy(dtype=float)
    propionate = results["S_pro"].to_numpy(dtype=float)
    vfa_total = acetate + propionate + results["S_va"].to_numpy(dtype=float) + results["S_bu"].to_numpy(dtype=float)
    profiles = {
        "particulate_cod": particulate_cod.tolist(),
        "soluble_cod": soluble_cod.tolist(),
        "acetate": acetate.tolist(),
        "propionate": propionate.tolist(),
        "hydrogen": results["S_h2"].to_numpy(dtype=float).tolist(),
        "acidogens": acidogens.tolist(),
        "propionate_biomass": propionate_biomass.tolist(),
        "acetoclastic_biomass": results["X_ac"].to_numpy(dtype=float).tolist(),
        "hydrogenotrophic_biomass": results["X_h2"].to_numpy(dtype=float).tolist(),
        "inorganic_nitrogen": (results["S_IN"].to_numpy(dtype=float) * 14.0).tolist(),
        "alkalinity": results["S_IC"].to_numpy(dtype=float).tolist(),
        "ph": results["pH"].to_numpy(dtype=float).tolist(),
        "vfa_total": vfa_total.tolist(),
        "methane_m3_day": methane.tolist(),
        "co2_m3_day": co2.tolist(),
        "h2_m3_day": hydrogen.tolist(),
        "biogas_m3_day": biogas.tolist(),
        "ch4_fraction": np.clip(methane / np.maximum(biogas, 1e-9), 0.0, 1.0).tolist(),
        "effluent_cod": (
            particulate_cod
            + soluble_cod
            + vfa_total
            + acidogens
            + propionate_biomass
            + results["X_ac"].to_numpy(dtype=float)
            + results["X_h2"].to_numpy(dtype=float)
            + results["S_h2"].to_numpy(dtype=float)
            + results["S_ch4"].to_numpy(dtype=float)
        ).tolist(),
        "volatile_solids_proxy": (
            particulate_cod
            + acidogens
            + propionate_biomass
            + results["X_ac"].to_numpy(dtype=float)
            + results["X_h2"].to_numpy(dtype=float)
        ).tolist(),
    }
    return {name: [float(value) for value in values] for name, values in profiles.items()}


def _ratio(value: float, baseline: float) -> float:
    if abs(baseline) <= 1e-12:
        return 1.0
    return max(float(value) / float(baseline), 1e-6)


def _kg_n_to_kmol_n(value: float) -> float:
    return float(value) / 14.0


