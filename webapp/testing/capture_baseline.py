"""Script de captura de baseline para testes de regressão.

Executa cada cenário de regressão contra o simulador real e salva as saídas
em ``webapp/testing/baselines/<scenario_id>.json``.

Uso
---
    python -m webapp.testing.capture_baseline
    python -m webapp.testing.capture_baseline --scenario caso_base_lite
    python -m webapp.testing.capture_baseline --force  # sobrescreve baselines existentes
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import UTC, datetime
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
        KineticParameters,
    )
    from simulator.core.defaults import make_default_simulation_config
    _SIMULATOR_AVAILABLE = True
except ImportError as _exc:
    _SIMULATOR_AVAILABLE = False
    _SIMULATOR_IMPORT_ERROR = str(_exc)

from webapp.testing.regression_scenarios import REGRESSION_SCENARIOS, SCENARIOS_BY_ID

BASELINES_DIR = Path(__file__).parent / "baselines"


# ---------------------------------------------------------------------------
# Construção de objetos do simulador a partir dos cenários
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
# Execução de um cenário
# ---------------------------------------------------------------------------

def run_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    """Executa um cenário e retorna o registro de baseline."""
    scenario_id: str = scenario["scenario_id"]

    if not _SIMULATOR_AVAILABLE:
        return {
            "scenario_id": scenario_id,
            "captured_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "status": "error",
            "error": f"Simulador indisponível: {_SIMULATOR_IMPORT_ERROR}",
            "backend_requested": scenario["backend_requested"],
            "backend_expected": scenario["backend_expected"],
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
            metadata={"origin": "capture_baseline", "scenario_id": scenario_id},
        )

        backend_used = str(result.metadata.get("backend_used", ""))
        backend_requested = str(result.metadata.get("backend_requested", scenario["backend_requested"]))
        fallback_reason = result.metadata.get("backend_fallback_reason")
        has_fallback = fallback_reason is not None

        kpis: dict[str, float | None] = {
            "methane_final_m3_day": float(result.summary.methane_final_m3_day),
            "biogas_final_m3_day": float(result.summary.biogas_final_m3_day),
            "ph_final": float(result.summary.ph_final),
            "vfa_final": float(result.summary.vfa_final),
            "effluent_cod_final": float(result.summary.effluent_cod_final),
            "stability_index": float(result.summary.stability_index),
        }

        # Warnings gerados pelo resultado (metadata pode conter lista)
        warnings: list[str] = []
        raw_warnings = result.metadata.get("warnings")
        if isinstance(raw_warnings, list):
            warnings = [str(w) for w in raw_warnings]

        return {
            "scenario_id": scenario_id,
            "captured_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "status": "ok",
            "error": None,
            "backend_requested": backend_requested,
            "backend_expected": scenario["backend_expected"],
            "backend_used": backend_used,
            "has_fallback": has_fallback,
            "fallback_reason": str(fallback_reason) if fallback_reason else None,
            "kpis": kpis,
            "warnings": warnings,
        }

    except Exception as exc:  # noqa: BLE001
        return {
            "scenario_id": scenario_id,
            "captured_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
            "backend_requested": scenario["backend_requested"],
            "backend_expected": scenario["backend_expected"],
            "backend_used": None,
            "has_fallback": None,
            "fallback_reason": None,
            "kpis": {},
            "warnings": [],
        }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Captura baseline dos cenários de regressão ADM1."
    )
    parser.add_argument(
        "--scenario",
        metavar="SCENARIO_ID",
        help="Captura apenas o cenário com o ID informado.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Sobrescreve baselines já existentes.",
    )
    args = parser.parse_args()

    BASELINES_DIR.mkdir(parents=True, exist_ok=True)

    if args.scenario:
        if args.scenario not in SCENARIOS_BY_ID:
            print(f"[ERRO] Cenário '{args.scenario}' não encontrado.", file=sys.stderr)
            print(f"Cenários disponíveis: {', '.join(SCENARIOS_BY_ID)}", file=sys.stderr)
            return 1
        scenarios = [SCENARIOS_BY_ID[args.scenario]]
    else:
        scenarios = REGRESSION_SCENARIOS

    results: list[dict[str, Any]] = []
    n_ok = n_error = n_skipped = 0

    print(f"\n{'='*60}")
    print(f"  Captura de Baseline — {len(scenarios)} cenário(s)")
    print(f"{'='*60}\n")

    for scenario in scenarios:
        sid = scenario["scenario_id"]
        out_path = BASELINES_DIR / f"{sid}.json"

        if out_path.exists() and not args.force:
            print(f"  [SKIP] {sid} — baseline já existe (use --force para sobrescrever)")
            n_skipped += 1
            continue

        print(f"  [ RUN] {sid} ...", end="", flush=True)
        record = run_scenario(scenario)
        results.append(record)

        if record["status"] == "ok":
            kpis = record["kpis"]
            ch4 = kpis.get("methane_final_m3_day")
            ph = kpis.get("ph_final")
            backend = record["backend_used"]
            print(
                f" OK  [backend={backend}, CH4={ch4:.4f} m³/d, pH={ph:.2f}]"
                if ch4 is not None and ph is not None
                else f" OK  [backend={backend}]"
            )
            n_ok += 1
        else:
            short_err = (record["error"] or "").splitlines()[0][:80]
            print(f" ERRO — {short_err}")
            n_error += 1

        out_path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"  Resultado: {n_ok} OK | {n_error} ERRO | {n_skipped} SKIP")
    print(f"  Baselines em: {BASELINES_DIR}")
    print(f"{'='*60}\n")

    return 0 if n_error == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
