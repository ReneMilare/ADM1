from __future__ import annotations

import json
from io import StringIO
from typing import Any, Mapping

import pandas as pd

from simulator.core.defaults import make_default_simulation_config
from simulator.core.models import FeedDefinition, KineticParameters, OperatingConditions, SimulationConfig, SimulationResult
from simulator.service import ADM1SimulationService
from webapp.utils.presets import get_manual_defaults, get_preset_bundle

REACTOR_OPTIONS = {
    "cstr": "CSTR",
    "uasb": "UASB",
    "plug_flow": "Plug-Flow",
}
BACKEND_OPTIONS = {
    "pyadm1": "PyADM1 original",
    "auto": "Auto",
    "reduced": "Reduced",
}


def get_reactor_options() -> dict[str, str]:
    return REACTOR_OPTIONS.copy()



def get_backend_options() -> dict[str, str]:
    return BACKEND_OPTIONS.copy()



def resolve_requested_backend(reactor_type: str, backend: str) -> tuple[str, str | None]:
    if backend == "pyadm1" and reactor_type != "cstr":
        return "reduced", "PyADM1 currently supports only CSTR in this project. The execution will fall back to the reduced backend."
    if backend == "auto" and reactor_type != "cstr":
        return "reduced", "Auto mode keeps the reduced backend for non-CSTR reactors."
    if backend == "auto":
        return "pyadm1", "Auto mode selects PyADM1 for CSTR."
    return backend, None



def build_feed_and_operating(
    *,
    substrate_mode: str,
    preset_id: str | None,
    manual_feed_values: dict[str, float | str],
    operating_values: dict[str, float],
) -> tuple[FeedDefinition, OperatingConditions, str | None]:
    if substrate_mode == "preset":
        if not preset_id:
            raise ValueError("preset_id is required when substrate_mode='preset'")
        feed, base_operating, note_link = get_preset_bundle(preset_id)
    else:
        feed, base_operating = get_manual_defaults()
        note_link = None
        feed = feed.model_copy(
            update={
                "name": str(manual_feed_values.get("name") or feed.name),
                "particulate_cod": float(manual_feed_values.get("particulate_cod", feed.particulate_cod)),
                "soluble_cod": float(manual_feed_values.get("soluble_cod", feed.soluble_cod)),
                "acetate": float(manual_feed_values.get("acetate", feed.acetate)),
                "propionate": float(manual_feed_values.get("propionate", feed.propionate)),
                "hydrogen": float(manual_feed_values.get("hydrogen", feed.hydrogen)),
                "inorganic_nitrogen": float(manual_feed_values.get("inorganic_nitrogen", feed.inorganic_nitrogen)),
                "alkalinity": float(manual_feed_values.get("alkalinity", feed.alkalinity)),
                "ph": float(manual_feed_values.get("ph", feed.ph)),
            }
        )

    operating = base_operating.model_copy(
        update={
            "volume_m3": float(operating_values.get("volume_m3", base_operating.volume_m3)),
            "temperature_c": float(operating_values.get("temperature_c", base_operating.temperature_c)),
            "hrt_days": float(operating_values.get("hrt_days", base_operating.hrt_days)),
        }
    )
    return feed, operating, note_link



def build_simulation_config(
    *,
    duration_days: float,
    evaluation_points: int,
    solver: str,
    backend: str,
    persist: bool,
) -> SimulationConfig:
    base = make_default_simulation_config()
    return base.model_copy(
        update={
            "duration_days": float(duration_days),
            "evaluation_points": int(evaluation_points),
            "solver": solver,
            "backend": backend,
            "persist": bool(persist),
        }
    )



def validate_simulation_inputs(
    *,
    reactor_type: str,
    substrate_mode: str,
    manual_feed_values: dict[str, float | str],
    operating_values: dict[str, float],
    duration_days: float,
    evaluation_points: int,
    solver: str,
    backend: str,
) -> dict[str, list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    volume_m3 = float(operating_values.get("volume_m3", 0.0))
    temperature_c = float(operating_values.get("temperature_c", 0.0))
    hrt_days = float(operating_values.get("hrt_days", 0.0))

    if volume_m3 <= 0.0:
        errors.append("O volume do reator precisa ser maior que zero.")
    if hrt_days <= 0.0:
        errors.append("O HRT precisa ser maior que zero.")
    if duration_days <= 0.0:
        errors.append("A duracao da simulacao precisa ser maior que zero.")
    if evaluation_points < 21:
        errors.append("Use pelo menos 21 pontos de avaliacao para obter curvas interpretaveis.")

    if solver not in {"BDF", "Radau"}:
        errors.append("Solver invalido. Use `BDF` ou `Radau`.")

    if backend == "pyadm1" and reactor_type != "cstr":
        warnings.append("PyADM1 nao suporta esse reator neste projeto; o backend efetivo caira para `reduced`.")
    if backend == "auto" and reactor_type != "cstr":
        warnings.append("No modo `auto`, reatores nao CSTR continuam no backend `reduced`.")

    if duration_days < hrt_days:
        warnings.append("A duracao da simulacao esta menor que o HRT. O transiente pode ficar curto demais para analise tecnica.")
    if evaluation_points < 81:
        warnings.append("A discretizacao esta enxuta. Use mais pontos de avaliacao se quiser curvas mais suaves para export ou comparacao.")
    if temperature_c < 30.0 or temperature_c > 40.0:
        warnings.append("A temperatura esta fora da faixa mesofilica classica. Verifique se isso e intencional para o estudo.")
    if hrt_days < 5.0:
        warnings.append("HRT muito baixo tende a aumentar risco de washout e instabilidade. Revise o caso antes de interpretar o resultado.")
    if reactor_type == "plug_flow" and hrt_days < 8.0:
        warnings.append("Plug-Flow com HRT muito baixo pode reduzir a utilidade comparativa do caso frente aos outros reatores.")

    if substrate_mode == "manual":
        particulate_cod = float(manual_feed_values.get("particulate_cod", 0.0) or 0.0)
        soluble_cod = float(manual_feed_values.get("soluble_cod", 0.0) or 0.0)
        acetate = float(manual_feed_values.get("acetate", 0.0) or 0.0)
        propionate = float(manual_feed_values.get("propionate", 0.0) or 0.0)
        alkalinity = float(manual_feed_values.get("alkalinity", 0.0) or 0.0)
        influent_ph = float(manual_feed_values.get("ph", 0.0) or 0.0)
        inorganic_nitrogen = float(manual_feed_values.get("inorganic_nitrogen", 0.0) or 0.0)

        if particulate_cod + soluble_cod + acetate + propionate <= 0.0:
            errors.append("No modo manual, a alimentacao precisa ter carga organica maior que zero.")
        if influent_ph < 6.0 or influent_ph > 8.2:
            warnings.append("O pH de alimentacao esta fora da faixa usual. Revise a interpretacao de estabilidade e VFA para este caso.")
        if alkalinity < 1.0:
            warnings.append("Alcalinidade de entrada baixa pode comprometer a capacidade tampao do caso simulado.")
        if inorganic_nitrogen > 4.0:
            warnings.append("Nitrogenio inorganico alto pode aproximar o caso de regimes com sensibilidade a amonia.")

    return {"errors": errors, "warnings": warnings}



def format_simulation_error(exc: Exception) -> str:
    message = str(exc)
    if "Selecione pelo menos" in message:
        return message
    if "validation error" in message.lower():
        return "Os parametros informados nao passaram na validacao do modelo. Revise valores fisicos e tente novamente."
    if "pyadm1" in message.lower() and "support" in message.lower():
        return "O backend PyADM1 nao conseguiu executar esse caso. Se o reator nao for CSTR, use `reduced` ou `auto`."
    return message



def build_user_simulation_preset_payload(session_values: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "reactor_type": str(session_values.get("sim_reactor_type", "cstr")),
        "substrate_mode": str(session_values.get("sim_substrate_mode", "preset")),
        "preset_id": session_values.get("sim_preset_id"),
        "backend_choice": str(session_values.get("sim_backend_choice", "pyadm1")),
        "operating": {
            "volume_m3": float(session_values.get("volume_active", 3000.0)),
            "temperature_c": float(session_values.get("temperature_active", 35.0)),
            "hrt_days": float(session_values.get("hrt_active", 20.0)),
        },
        "simulation": {
            "duration_days": float(session_values.get("duration_days", 45.0)),
            "evaluation_points": int(session_values.get("evaluation_points", 181)),
            "solver": str(session_values.get("solver_choice", "BDF")),
            "persist": bool(session_values.get("persist_case", True)),
        },
        "manual_feed_values": {
            "name": str(session_values.get("manual_feed_name", "Manual feed")),
            "particulate_cod": float(session_values.get("manual_particulate_cod", 0.0)),
            "soluble_cod": float(session_values.get("manual_soluble_cod", 0.0)),
            "acetate": float(session_values.get("manual_acetate", 0.0)),
            "propionate": float(session_values.get("manual_propionate", 0.0)),
            "hydrogen": float(session_values.get("manual_hydrogen", 0.0)),
            "inorganic_nitrogen": float(session_values.get("manual_inorganic_nitrogen", 0.0)),
            "alkalinity": float(session_values.get("manual_alkalinity", 0.0)),
            "ph": float(session_values.get("manual_feed_ph", 7.0)),
        },
    }



def apply_user_simulation_preset(session_state: Any, payload: Mapping[str, Any]) -> None:
    session_state["sim_reactor_type"] = str(payload.get("reactor_type", "cstr"))
    session_state["sim_substrate_mode"] = str(payload.get("substrate_mode", "preset"))
    session_state["sim_preset_id"] = payload.get("preset_id")
    session_state["sim_backend_choice"] = str(payload.get("backend_choice", "pyadm1"))

    operating = payload.get("operating", {}) if isinstance(payload.get("operating"), dict) else {}
    simulation = payload.get("simulation", {}) if isinstance(payload.get("simulation"), dict) else {}
    manual_feed_values = payload.get("manual_feed_values", {}) if isinstance(payload.get("manual_feed_values"), dict) else {}

    session_state["volume_active"] = float(operating.get("volume_m3", 3000.0))
    session_state["temperature_active"] = float(operating.get("temperature_c", 35.0))
    session_state["hrt_active"] = float(operating.get("hrt_days", 20.0))
    session_state["duration_days"] = float(simulation.get("duration_days", 45.0))
    session_state["evaluation_points"] = int(simulation.get("evaluation_points", 181))
    session_state["solver_choice"] = str(simulation.get("solver", "BDF"))
    session_state["persist_case"] = bool(simulation.get("persist", True))

    for key, fallback in {
        "manual_feed_name": "Manual feed",
        "manual_particulate_cod": 8.0,
        "manual_soluble_cod": 4.0,
        "manual_acetate": 0.5,
        "manual_propionate": 0.2,
        "manual_hydrogen": 0.001,
        "manual_inorganic_nitrogen": 1.0,
        "manual_alkalinity": 4.0,
        "manual_feed_ph": 7.0,
    }.items():
        session_state[key] = manual_feed_values.get(key.removeprefix("manual_"), manual_feed_values.get(key, fallback))



def run_simulation(
    *,
    reactor_type: str,
    substrate_mode: str,
    preset_id: str | None,
    manual_feed_values: dict[str, float | str],
    operating_values: dict[str, float],
    duration_days: float,
    evaluation_points: int,
    solver: str,
    backend: str,
    persist: bool,
) -> SimulationResult:
    feed, operating, note_link = build_feed_and_operating(
        substrate_mode=substrate_mode,
        preset_id=preset_id,
        manual_feed_values=manual_feed_values,
        operating_values=operating_values,
    )
    simulation = build_simulation_config(
        duration_days=duration_days,
        evaluation_points=evaluation_points,
        solver=solver,
        backend=backend,
        persist=persist,
    )
    service = ADM1SimulationService()
    metadata: dict[str, Any] = {
        "ui_origin": "streamlit_w2_w7",
        "substrate_mode": substrate_mode,
    }
    if preset_id:
        metadata["substrate_preset"] = preset_id
    if note_link:
        metadata["substrate_note_link"] = note_link
    return service.simulate(
        reactor_type,
        feed=feed,
        operating_conditions=operating,
        simulation=simulation,
        parameters=KineticParameters(),
        metadata=metadata,
    )



def simulation_summary_rows(result: SimulationResult) -> list[dict[str, Any]]:
    metadata = result.metadata
    return [
        {"metric": "Metano final", "value": f"{result.summary.methane_final_m3_day:.3f} m3/d"},
        {"metric": "Biogas final", "value": f"{result.summary.biogas_final_m3_day:.3f} m3/d"},
        {"metric": "Fracao CH4 final", "value": f"{result.summary.ch4_fraction_final:.3f}"},
        {"metric": "pH final", "value": f"{result.summary.ph_final:.3f}"},
        {"metric": "VFA final", "value": f"{result.summary.vfa_final:.3f}"},
        {"metric": "Backend solicitado", "value": str(metadata.get("backend_requested", result.simulation.backend))},
        {"metric": "Backend usado", "value": str(metadata.get("backend_used", result.simulation.backend))},
        {"metric": "Simulation ID", "value": result.simulation_id},
    ]



def simulation_input_rows(result: SimulationResult) -> list[dict[str, Any]]:
    return [
        {"group": "Reator", "parameter": "Tipo", "value": result.reactor.reactor_type},
        {"group": "Operacao", "parameter": "Volume", "value": f"{result.operating_conditions.volume_m3:.2f} m3"},
        {"group": "Operacao", "parameter": "Temperatura", "value": f"{result.operating_conditions.temperature_c:.2f} C"},
        {"group": "Operacao", "parameter": "HRT", "value": f"{result.operating_conditions.hrt_days:.2f} d"},
        {"group": "Simulacao", "parameter": "Duracao", "value": f"{result.simulation.duration_days:.2f} d"},
        {"group": "Simulacao", "parameter": "Solver", "value": result.simulation.solver},
        {"group": "Feed", "parameter": "Nome", "value": result.feed.name},
        {"group": "Feed", "parameter": "Particulate COD", "value": f"{result.feed.particulate_cod:.3f} kgCOD/m3"},
        {"group": "Feed", "parameter": "Soluble COD", "value": f"{result.feed.soluble_cod:.3f} kgCOD/m3"},
        {"group": "Feed", "parameter": "Acetate", "value": f"{result.feed.acetate:.3f} kgCOD/m3"},
        {"group": "Feed", "parameter": "Propionate", "value": f"{result.feed.propionate:.3f} kgCOD/m3"},
        {"group": "Feed", "parameter": "Influent pH", "value": f"{result.feed.ph:.2f}"},
    ]



def result_series_frame(result: SimulationResult) -> pd.DataFrame:
    frame = pd.DataFrame({"time_days": result.time_days})
    for key, values in result.series.items():
        frame[key] = values
    return frame



def summary_json_bytes(result: SimulationResult) -> bytes:
    payload = {
        "simulation_id": result.simulation_id,
        "created_at": result.created_at,
        "reactor": result.reactor.model_dump(),
        "operating_conditions": result.operating_conditions.model_dump(),
        "feed": result.feed.model_dump(),
        "simulation": result.simulation.model_dump(),
        "summary": result.summary.model_dump(),
        "metadata": result.metadata,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")



def summary_csv_bytes(result: SimulationResult) -> bytes:
    buffer = StringIO()
    pd.DataFrame(simulation_summary_rows(result)).to_csv(buffer, index=False)
    return buffer.getvalue().encode("utf-8")



def series_csv_bytes(result: SimulationResult) -> bytes:
    buffer = StringIO()
    result_series_frame(result).to_csv(buffer, index=False)
    return buffer.getvalue().encode("utf-8")