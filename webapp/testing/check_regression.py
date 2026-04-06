"""Script de verificação de regressão para o webapp ADM1.

Lê os cenários de ``regression_scenarios.py``, carrega o baseline
correspondente de ``baselines/``, executa o cenário atual e compara
os resultados usando as tolerâncias definidas em ``tolerances.py``.

Uso
---
    python -m webapp.testing.check_regression
    python -m webapp.testing.check_regression --scenario caso_base_lite
    python -m webapp.testing.check_regression --verbose
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Ajuste de sys.path para encontrar o pacote simulator
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[3]  # <project-root>
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Imports do simulador (defensivos)
# ---------------------------------------------------------------------------
try:
    from simulator.service import ADM1SimulationService
    from simulator.core.models import (
        FeedDefinition,
        OperatingConditions,
        ReactorConfig,
        SimulationConfig,
    )
    from simulator.core.defaults import make_default_simulation_config
    _SIMULATOR_AVAILABLE = True
except ImportError as _exc:
    _SIMULATOR_AVAILABLE = False
    _SIMULATOR_IMPORT_ERROR = str(_exc)

from webapp.testing.regression_scenarios import REGRESSION_SCENARIOS, SCENARIOS_BY_ID
from webapp.testing.tolerances import (
    CATEGORICAL_EXACT_FIELDS,
    DEFAULT_KPI_TOLERANCES,
    WARNING_EXACT_MATCH,
)

BASELINES_DIR = Path(__file__).parent / "baselines"


# ---------------------------------------------------------------------------
# Reutiliza funções de construção do capture_baseline
# ---------------------------------------------------------------------------

def _build_feed(params: dict[str, Any]) -> "FeedDefinition":
    return FeedDefinition(
        name=str(params.get("name", "test_feed")),
        particulate_cod=float(params["particulate_cod"]),
        soluble_cod=float(params["soluble_cod"]),
        acetate=float(params["acetate"]),
        propionate=float(params["propionate"]),
        hydrogen=float(params.get("hydrogen", 0.0)),
        inorganic_nitrogen=float(params.get("inorganic_nitrogen", 0.0)),
        alkalinity=float(params["alkalinity"]),
        ph=float(params["ph"]),
    )


def _build_operating(params: dict[str, Any]) -> "OperatingConditions":
    return OperatingConditions(
        volume_m3=float(params["volume_m3"]),
        temperature_c=float(params["temperature_c"]),
        hrt_days=float(params["hrt_days"]),
    )


def _build_simulation_config(scenario: dict[str, Any]) -> "SimulationConfig":
    base = make_default_simulation_config()
    overrides: dict[str, Any] = {
        "backend": scenario["backend_requested"],
        "persist": False,
        "duration_days": 45.0,
        "evaluation_points": 181,
    }
    if scenario["extensions"]:
        overrides["full_extensions"] = list(scenario["extensions"])
    ext_ov = scenario.get("extension_overrides", {})
    if ext_ov.get("initial_state_overrides"):
        overrides["full_initial_state_overrides"] = dict(ext_ov["initial_state_overrides"])
    if ext_ov.get("influent_state_overrides"):
        overrides["full_influent_state_overrides"] = dict(ext_ov["influent_state_overrides"])
    return base.model_copy(update=overrides)


# ---------------------------------------------------------------------------
# Execução de um cenário (retorna registro no mesmo formato do baseline)
# ---------------------------------------------------------------------------

def run_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    scenario_id: str = scenario["scenario_id"]

    if not _SIMULATOR_AVAILABLE:
        return {
            "scenario_id": scenario_id,
            "status": "error",
            "error": f"Simulador indisponível: {_SIMULATOR_IMPORT_ERROR}",
            "backend_used": None,
            "has_fallback": None,
            "fallback_reason": None,
            "kpis": {},
            "warnings": [],
        }

    try:
        feed = _build_feed(scenario["feed_params"])
        operating = _build_operating(scenario["operating_params"])
        sim_config = _build_simulation_config(scenario)
        reactor_config = ReactorConfig(reactor_type=scenario["reactor_type"])  # type: ignore[arg-type]

        service = ADM1SimulationService()
        result = service.simulate(
            reactor_config,
            feed=feed,
            operating_conditions=operating,
            simulation=sim_config,
            metadata={"origin": "check_regression", "scenario_id": scenario_id},
        )

        backend_used = str(result.metadata.get("backend_used", ""))
        fallback_reason = result.metadata.get("backend_fallback_reason")
        has_fallback = fallback_reason is not None

        kpis: dict[str, float] = {
            "methane_final_m3_day": float(result.summary.methane_final_m3_day),
            "biogas_final_m3_day": float(result.summary.biogas_final_m3_day),
            "ph_final": float(result.summary.ph_final),
            "vfa_final": float(result.summary.vfa_final),
            "effluent_cod_final": float(result.summary.effluent_cod_final),
            "stability_index": float(result.summary.stability_index),
        }

        warnings: list[str] = []
        raw_warnings = result.metadata.get("warnings")
        if isinstance(raw_warnings, list):
            warnings = [str(w) for w in raw_warnings]

        return {
            "scenario_id": scenario_id,
            "status": "ok",
            "error": None,
            "backend_requested": scenario["backend_requested"],
            "backend_used": backend_used,
            "has_fallback": has_fallback,
            "fallback_reason": str(fallback_reason) if fallback_reason else None,
            "kpis": kpis,
            "warnings": warnings,
        }

    except Exception as exc:  # noqa: BLE001
        return {
            "scenario_id": scenario_id,
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
            "backend_used": None,
            "has_fallback": None,
            "fallback_reason": None,
            "kpis": {},
            "warnings": [],
        }


# ---------------------------------------------------------------------------
# Comparação entre resultado atual e baseline
# ---------------------------------------------------------------------------

def _compare(
    scenario: dict[str, Any],
    baseline: dict[str, Any],
    current: dict[str, Any],
    verbose: bool = False,
) -> tuple[bool, list[str]]:
    """Compara ``current`` com ``baseline`` e retorna (passou, lista_de_falhas)."""
    failures: list[str] = []

    # --- Status de execução ---
    if current["status"] != "ok":
        failures.append(f"Execução falhou: {(current.get('error') or '').splitlines()[0][:120]}")
        return False, failures

    if baseline.get("status") != "ok":
        failures.append("Baseline com status de erro — re-capture necessário.")
        return False, failures

    # --- Campos categóricos exatos ---
    for field in CATEGORICAL_EXACT_FIELDS:
        if field == "backend_used":
            cur_val = current.get("backend_used")
            base_val = baseline.get("backend_used")
            expected = scenario.get("backend_expected")
            if cur_val != expected:
                failures.append(
                    f"backend_used: atual={cur_val!r}, esperado={expected!r}"
                )
        elif field == "backend_requested":
            cur_val = current.get("backend_requested")
            base_val = baseline.get("backend_requested")
            if cur_val != base_val:
                failures.append(
                    f"backend_requested: atual={cur_val!r}, baseline={base_val!r}"
                )
        elif field == "has_fallback":
            cur_val = current.get("has_fallback")
            expected_fallback = scenario.get("fallback_expected")
            if cur_val != expected_fallback:
                failures.append(
                    f"has_fallback: atual={cur_val!r}, esperado={expected_fallback!r}"
                )

    # --- Razão de fallback ---
    if scenario.get("fallback_expected") and scenario.get("fallback_reason_contains"):
        substring = scenario["fallback_reason_contains"]
        fallback_reason = current.get("fallback_reason") or ""
        if substring not in fallback_reason:
            failures.append(
                f"fallback_reason não contém '{substring}': atual={fallback_reason!r}"
            )

    # --- KPIs numéricos ---
    base_kpis: dict[str, float] = baseline.get("kpis") or {}
    curr_kpis: dict[str, float] = current.get("kpis") or {}
    scenario_tols: dict[str, Any] = scenario.get("kpi_tolerances") or {}

    for kpi_name, default_tol in DEFAULT_KPI_TOLERANCES.items():
        tol = {**default_tol, **(scenario_tols.get(kpi_name) or {})}
        base_val = base_kpis.get(kpi_name)
        curr_val = curr_kpis.get(kpi_name)

        if base_val is None or curr_val is None:
            if verbose:
                failures.append(f"KPI '{kpi_name}' ausente (baseline={base_val}, atual={curr_val})")
            continue

        abs_diff = abs(curr_val - base_val)
        abs_tol = tol.get("abs")
        rel_tol_pct = tol.get("rel_pct")

        passed_abs = abs_tol is None or abs_diff <= abs_tol
        if abs_tol is not None and not passed_abs:
            failures.append(
                f"KPI '{kpi_name}': desvio absoluto {abs_diff:.6f} > tolerância {abs_tol} "
                f"(baseline={base_val:.6f}, atual={curr_val:.6f})"
            )

        if rel_tol_pct is not None and base_val != 0.0:
            rel_diff_pct = 100.0 * abs_diff / abs(base_val)
            if rel_diff_pct > rel_tol_pct:
                failures.append(
                    f"KPI '{kpi_name}': desvio relativo {rel_diff_pct:.2f}% > tolerância {rel_tol_pct}% "
                    f"(baseline={base_val:.6f}, atual={curr_val:.6f})"
                )

    # --- Warnings ---
    if WARNING_EXACT_MATCH:
        curr_warnings = current.get("warnings") or []
        curr_warnings_text = "\n".join(curr_warnings)

        for required_sub in scenario.get("required_warnings_contain") or []:
            if required_sub not in curr_warnings_text:
                failures.append(
                    f"Warning obrigatório não encontrado: '{required_sub}'"
                )

        for forbidden_sub in scenario.get("forbidden_warnings_contain") or []:
            if forbidden_sub in curr_warnings_text:
                failures.append(
                    f"Warning proibido encontrado: '{forbidden_sub}'"
                )

    return len(failures) == 0, failures


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verifica regressões nos cenários de simulação ADM1."
    )
    parser.add_argument(
        "--scenario",
        metavar="SCENARIO_ID",
        help="Verifica apenas o cenário com o ID informado.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Exibe detalhes adicionais, incluindo KPIs ausentes.",
    )
    args = parser.parse_args()

    if args.scenario:
        if args.scenario not in SCENARIOS_BY_ID:
            print(f"[ERRO] Cenário '{args.scenario}' não encontrado.", file=sys.stderr)
            return 1
        scenarios = [SCENARIOS_BY_ID[args.scenario]]
    else:
        scenarios = REGRESSION_SCENARIOS

    n_pass = n_fail = n_skip = 0

    print(f"\n{'='*60}")
    print(f"  Verificação de Regressão — {len(scenarios)} cenário(s)")
    print(f"{'='*60}\n")

    for scenario in scenarios:
        sid = scenario["scenario_id"]
        baseline_path = BASELINES_DIR / f"{sid}.json"

        if not baseline_path.exists():
            print(f"  [SKIP] {sid} — baseline não encontrado (execute capture_baseline primeiro)")
            n_skip += 1
            continue

        try:
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  [SKIP] {sid} — erro ao ler baseline: {exc}")
            n_skip += 1
            continue

        print(f"  [ RUN] {sid} ...", end="", flush=True)
        current = run_scenario(scenario)
        passed, failures = _compare(scenario, baseline, current, verbose=args.verbose)

        if passed:
            backend = current.get("backend_used", "?")
            print(f" PASS  [backend={backend}]")
            n_pass += 1
        else:
            print(f" FAIL")
            n_fail += 1
            for failure in failures:
                print(f"       ✗ {failure}")

    print(f"\n{'='*60}")
    print(f"  Resultado: {n_pass} PASS | {n_fail} FAIL | {n_skip} SKIP")
    print(f"{'='*60}\n")

    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
