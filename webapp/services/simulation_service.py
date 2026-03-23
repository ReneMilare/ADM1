from __future__ import annotations

import json
from io import StringIO
from typing import Any, Mapping

import pandas as pd

from simulator.core.defaults import make_default_simulation_config
from simulator.core.models import (
    BatchConfig,
    CoDigestionBlend,
    FeedDefinition,
    KineticParameters,
    OperatingConditions,
    ReactorConfig,
    SimulationConfig,
    SimulationResult,
    TPADConfig,
    TwoPhaseConfig,
)
from simulator.service import ADM1SimulationService
from webapp.utils.presets import get_codigestion_blend, get_manual_defaults, get_preset_bundle

REACTOR_OPTIONS = {
    "cstr": "CSTR",
    "uasb": "UASB",
    "plug_flow": "Plug-Flow",
    "two_phase": "Duas Fases (AD)",
    "tpad": "TPAD",
    "batch": "Batelada (BMP)",
}
BACKEND_OPTIONS = {
    "pyadm1": "PyADM1 original",
    "full": "ADM1 full nativo",
    "auto": "Auto (CSTR -> PyADM1)",
    "reduced": "Reduced",
}
# Tipos de reator que requerem fallback para reduced quando pyadm1 é solicitado
_PYADM1_ONLY_CSTR = {"two_phase", "tpad", "batch", "uasb", "plug_flow"}


def get_reactor_options() -> dict[str, str]:
    return REACTOR_OPTIONS.copy()



def get_backend_options() -> dict[str, str]:
    return BACKEND_OPTIONS.copy()



def resolve_requested_backend(reactor_type: str, backend: str) -> tuple[str, str | None]:
    """Resolve o backend efetivo dado o tipo de reator e o backend solicitado.

    O backend `full` suporta todos os tipos de reator (CSTR, UASB, Plug-flow,
    Two-phase, TPAD, Batch). O `pyadm1` suporta apenas CSTR.
    O `auto` usa `pyadm1` para CSTR e `reduced` para outros tipos.
    """
    if backend == "pyadm1" and reactor_type != "cstr":
        return "reduced", "PyADM1 suporta apenas CSTR neste projeto. A execucao caira para o backend `reduced`."
    if backend == "full":
        return "full", f"Backend `full` selecionado para {reactor_type}. Suporta todos os tipos de reator com ADM1 nativo."
    if backend == "auto" and reactor_type != "cstr":
        return "reduced", "No modo `auto`, reatores nao CSTR continuam no backend `reduced`. Use `full` para ADM1 completo."
    if backend == "auto":
        return (
            "pyadm1",
            "No modo `auto`, CSTR continua em `pyadm1` por conservadorismo. Use `full` explicitamente quando quiser rodar o backend nativo.",
        )
    return backend, None



def build_feed_and_operating(
    *,
    substrate_mode: str,
    preset_id: str | None,
    manual_feed_values: dict[str, float | str],
    operating_values: dict[str, float],
    blend: CoDigestionBlend | None = None,
    custom_substrate_values: dict[str, float | str] | None = None,
) -> tuple[FeedDefinition, OperatingConditions, str | None]:
    """Constrói FeedDefinition e OperatingConditions a partir dos parâmetros da UI.

    Suporta quatro caminhos de substrato:
    - ``blend``: co-digestão com blending explícito
    - ``preset`` / ``codigestion``: preset nativo (SUBSTRATE_PRESETS / CODIGESTION_PRESETS)
    - ``custom``: substrato personalizado salvo pelo usuário
    - ``manual``: edição livre de todos os campos

    O campo ``operating_values`` aceita tanto ``hrt_days`` (para o modo HRT) quanto
    ``flow_rate_m3_day`` (para o modo vazão). Se a vazão for fornecida, o HRT efetivo
    é derivado como V / Q.
    """
    if blend is not None:
        feed = blend.blend()
        base_operating, note_link = _operating_from_preset(preset_id)
    elif substrate_mode in ("preset", "codigestion"):
        if not preset_id:
            raise ValueError("preset_id is required when substrate_mode='preset' or 'codigestion'")
        feed, base_operating, note_link = get_preset_bundle(preset_id)
    elif substrate_mode == "custom":
        # Substrato personalizado salvo pelo usuário
        feed, base_operating = get_manual_defaults()
        note_link = None
        values = custom_substrate_values or manual_feed_values
        feed = feed.model_copy(
            update={
                "name": str(values.get("name") or feed.name),
                "particulate_cod": float(values.get("particulate_cod", feed.particulate_cod)),
                "soluble_cod": float(values.get("soluble_cod", feed.soluble_cod)),
                "acetate": float(values.get("acetate", feed.acetate)),
                "propionate": float(values.get("propionate", feed.propionate)),
                "hydrogen": float(values.get("hydrogen", feed.hydrogen)),
                "inorganic_nitrogen": float(values.get("inorganic_nitrogen", feed.inorganic_nitrogen)),
                "alkalinity": float(values.get("alkalinity", feed.alkalinity)),
                "ph": float(values.get("ph", feed.ph)),
            }
        )
    else:
        # Modo manual temporário
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

    volume_m3 = float(operating_values.get("volume_m3", base_operating.volume_m3))
    temperature_c = float(operating_values.get("temperature_c", base_operating.temperature_c))

    # Modo HRT vs Modo Vazão: calcula HRT efetivo a partir de Q quando informado
    flow_rate = operating_values.get("flow_rate_m3_day")
    if flow_rate is not None and float(flow_rate) > 0.0:
        # Modo vazão: HRT = V / Q
        hrt_days = volume_m3 / float(flow_rate)
    else:
        hrt_days = float(operating_values.get("hrt_days", base_operating.hrt_days))

    operating = base_operating.model_copy(
        update={
            "volume_m3": volume_m3,
            "temperature_c": temperature_c,
            "hrt_days": hrt_days,
        }
    )
    return feed, operating, note_link


def _operating_from_preset(preset_id: str | None) -> tuple[OperatingConditions, str | None]:
    if preset_id:
        try:
            _, operating, note_link = get_preset_bundle(preset_id)
            return operating, note_link
        except ValueError:
            pass
    from simulator.core.defaults import make_default_operating_conditions
    return make_default_operating_conditions(), None



def build_simulation_config(
    *,
    duration_days: float,
    evaluation_points: int,
    solver: str,
    backend: str,
    persist: bool,
    ammonia_inhibition_mode: str = "simple",
    full_extensions: list[str] | None = None,
    full_initial_state_overrides: dict[str, float] | None = None,
    full_influent_state_overrides: dict[str, float] | None = None,
    full_extension_parameter_overrides: dict[str, float] | None = None,
) -> SimulationConfig:
    base = make_default_simulation_config()
    return base.model_copy(
        update={
            "duration_days": float(duration_days),
            "evaluation_points": int(evaluation_points),
            "solver": solver,
            "backend": backend,
            "persist": bool(persist),
            "full_extensions": list(full_extensions or []),
            "full_initial_state_overrides": dict(full_initial_state_overrides or {}),
            "full_influent_state_overrides": dict(full_influent_state_overrides or {}),
            "full_extension_parameter_overrides": dict(full_extension_parameter_overrides or {}),
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
    variant_config: dict[str, Any] | None = None,
    ammonia_inhibition_mode: str = "simple",
    feed_nitrogen: float = 0.0,
) -> dict[str, list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    volume_m3 = float(operating_values.get("volume_m3", 0.0))
    temperature_c = float(operating_values.get("temperature_c", 0.0))
    hrt_days = float(operating_values.get("hrt_days", 0.0))

    if volume_m3 <= 0.0:
        errors.append("O volume do reator precisa ser maior que zero.")

    if reactor_type != "batch":
        if hrt_days <= 0.0:
            errors.append("O HRT precisa ser maior que zero.")
    if duration_days <= 0.0:
        errors.append("A duracao da simulacao precisa ser maior que zero.")
    if evaluation_points < 21:
        errors.append("Use pelo menos 21 pontos de avaliacao para obter curvas interpretaveis.")

    if solver not in {"BDF", "Radau"}:
        errors.append("Solver invalido. Use `BDF` ou `Radau`.")

    if backend == "pyadm1" and reactor_type != "cstr":
        warnings.append("PyADM1 suporta apenas CSTR; o backend efetivo cairá para `reduced`.")
    if backend == "full" and reactor_type != "cstr":
        warnings.append(f"Backend `full` selecionado para `{reactor_type}` — suportado nativamente com ADM1 completo.")
    if backend == "auto" and reactor_type != "cstr":
        warnings.append("No modo `auto`, reatores não-CSTR continuam no backend `reduced`. Use `full` para ADM1 nativo.")
    if backend == "auto" and reactor_type == "cstr":
        warnings.append("No modo `auto`, CSTR continua em `pyadm1`. Use `full` explicitamente para o backend nativo.")

    if reactor_type != "batch" and duration_days > 0 and hrt_days > 0 and duration_days < hrt_days:
        warnings.append("A duracao da simulacao esta menor que o HRT. O transiente pode ficar curto demais para analise tecnica.")

    if evaluation_points < 81:
        warnings.append("A discretizacao esta enxuta. Use mais pontos de avaliacao se quiser curvas mais suaves para export ou comparacao.")
    if temperature_c > 0 and (temperature_c < 30.0 or temperature_c > 40.0):
        warnings.append("A temperatura esta fora da faixa mesofilica classica. Verifique se isso e intencional para o estudo.")
    if reactor_type != "batch" and hrt_days > 0 and hrt_days < 5.0:
        warnings.append("HRT muito baixo tende a aumentar risco de washout e instabilidade. Revise o caso antes de interpretar o resultado.")
    if reactor_type == "plug_flow" and hrt_days > 0 and hrt_days < 8.0:
        warnings.append("Plug-Flow com HRT muito baixo pode reduzir a utilidade comparativa do caso frente aos outros reatores.")

    # Variant-specific validation
    vc = variant_config or {}
    if reactor_type == "two_phase":
        p1_ph = float(vc.get("phase1_ph_setpoint", 5.5))
        p2_ph = float(vc.get("phase2_ph_setpoint", 7.2))
        if p1_ph >= p2_ph:
            errors.append("Two-Phase: o pH da fase 1 (acidogênica) deve ser menor que o da fase 2 (metanogênica).")
    if reactor_type == "tpad":
        thermo_t = float(vc.get("thermo_temperature_c", 55.0))
        meso_t = float(vc.get("meso_temperature_c", 35.0))
        if thermo_t <= meso_t:
            errors.append("TPAD: a temperatura termofílica deve ser maior que a mesofílica.")

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
        feed_nitrogen = max(feed_nitrogen, inorganic_nitrogen)

    # Recommendation: fan mode
    if ammonia_inhibition_mode == "simple" and (feed_nitrogen > 2.0 or substrate_mode == "codigestion"):
        warnings.append(
            "💡 Recomendado: modo `fan` para este cenário (nitrogênio alto ou co-digestão). "
            "A inibição diferencial por grupo trófico fornece resultados mais realistas."
        )

    return {"errors": errors, "warnings": warnings}



def format_simulation_error(exc: Exception) -> str:
    message = str(exc)
    if "Selecione pelo menos" in message:
        return message
    if "validation error" in message.lower():
        return "Os parametros informados nao passaram na validacao do modelo. Revise valores fisicos e tente novamente."
    if "pyadm1" in message.lower() and "support" in message.lower():
        return "O backend PyADM1 nao conseguiu executar esse caso. Se o reator nao for CSTR, use `reduced`, `auto` ou `full` para CSTR."
    if "full" in message.lower() and "support" in message.lower():
        return "O backend `full` ainda esta restrito a CSTR nesta fase. Para variantes e nao CSTR, use `reduced` ou `auto`."
    return message



def build_user_simulation_preset_payload(session_values: Mapping[str, Any]) -> dict[str, Any]:
    # Modo hidráulico: "hrt" ou "flow_rate"
    hydraulic_mode = str(session_values.get("hydraulic_mode", "hrt"))
    operating: dict[str, Any] = {
        "volume_m3": float(session_values.get("volume_active", 3000.0)),
        "temperature_c": float(session_values.get("temperature_active", 35.0)),
        "hrt_days": float(session_values.get("hrt_active", 20.0)),
        "hydraulic_mode": hydraulic_mode,
    }
    if hydraulic_mode == "flow_rate":
        operating["flow_rate_m3_day"] = float(session_values.get("flow_rate_active", 150.0))

    return {
        "reactor_type": str(session_values.get("sim_reactor_type", "cstr")),
        "substrate_mode": str(session_values.get("sim_substrate_mode", "preset")),
        "preset_id": session_values.get("sim_preset_id"),
        "custom_substrate_name": session_values.get("sim_custom_substrate_name"),
        "backend_choice": str(session_values.get("sim_backend_choice", "pyadm1")),
        "ammonia_inhibition_mode": str(session_values.get("ammonia_inhibition_mode", "simple")),
        "codigestion_preset": session_values.get("codigestion_preset"),
        "variant_config": session_values.get("variant_config"),
        "operating": operating,
        "simulation": {
            "duration_days": float(session_values.get("duration_days", 45.0)),
            "evaluation_points": int(session_values.get("evaluation_points", 181)),
            "solver": str(session_values.get("solver_choice", "BDF")),
            "persist": bool(session_values.get("persist_case", True)),
        },
        "full_extension_state_inputs": {
            "srb_influent_so4": float(session_values.get("srb_influent_so4", 0.01)),
            "srb_initial_so4": float(session_values.get("srb_initial_so4", 0.01)),
            "srb_initial_srb_ac": float(session_values.get("srb_initial_srb_ac", 0.10)),
            "srb_initial_srb_h2": float(session_values.get("srb_initial_srb_h2", 0.05)),
            "srb_initial_srb_pro": float(session_values.get("srb_initial_srb_pro", 0.05)),
            "srb_initial_srb_bu": float(session_values.get("srb_initial_srb_bu", 0.05)),
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
    session_state["sim_custom_substrate_name"] = payload.get("custom_substrate_name", None)
    session_state["sim_backend_choice"] = str(payload.get("backend_choice", "pyadm1"))
    # New extension fields — backward compatible: default to safe values if absent
    session_state["ammonia_inhibition_mode"] = str(payload.get("ammonia_inhibition_mode", "simple"))
    session_state["codigestion_preset"] = payload.get("codigestion_preset", None)
    session_state["variant_config"] = payload.get("variant_config", None)

    operating = payload.get("operating", {}) if isinstance(payload.get("operating"), dict) else {}
    simulation = payload.get("simulation", {}) if isinstance(payload.get("simulation"), dict) else {}
    manual_feed_values = payload.get("manual_feed_values", {}) if isinstance(payload.get("manual_feed_values"), dict) else {}
    full_extension_state_inputs = payload.get("full_extension_state_inputs", {}) if isinstance(payload.get("full_extension_state_inputs"), dict) else {}

    session_state["volume_active"] = float(operating.get("volume_m3", 3000.0))
    session_state["temperature_active"] = float(operating.get("temperature_c", 35.0))
    session_state["hrt_active"] = float(operating.get("hrt_days", 20.0))
    # Modo hidráulico — retrocompatível: default "hrt" quando ausente
    session_state["hydraulic_mode"] = str(operating.get("hydraulic_mode", "hrt"))
    if "flow_rate_m3_day" in operating:
        session_state["flow_rate_active"] = float(operating["flow_rate_m3_day"])
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

    for key, fallback in {
        "srb_influent_so4": 0.01,
        "srb_initial_so4": 0.01,
        "srb_initial_srb_ac": 0.10,
        "srb_initial_srb_h2": 0.05,
        "srb_initial_srb_pro": 0.05,
        "srb_initial_srb_bu": 0.05,
    }.items():
        session_state[key] = float(full_extension_state_inputs.get(key, fallback))



def _build_reactor_config(reactor_type: str, variant_config: dict[str, Any] | None) -> ReactorConfig:
    vc = variant_config or {}
    if reactor_type == "two_phase":
        return ReactorConfig(
            reactor_type="two_phase",
            two_phase=TwoPhaseConfig(
                phase1_volume_fraction=float(vc.get("phase1_volume_fraction", 0.30)),
                phase1_ph_setpoint=float(vc.get("phase1_ph_setpoint", 5.5)),
                phase2_ph_setpoint=float(vc.get("phase2_ph_setpoint", 7.2)),
            ),
        )
    if reactor_type == "tpad":
        return ReactorConfig(
            reactor_type="tpad",
            tpad=TPADConfig(
                thermo_temperature_c=float(vc.get("thermo_temperature_c", 55.0)),
                thermo_hrt_days=float(vc.get("thermo_hrt_days", 3.0)),
                meso_temperature_c=float(vc.get("meso_temperature_c", 35.0)),
                meso_hrt_days=float(vc.get("meso_hrt_days", 15.0)),
            ),
        )
    if reactor_type == "batch":
        return ReactorConfig(
            reactor_type="batch",
            batch=BatchConfig(
                inoculum_fraction=float(vc.get("inoculum_fraction", 0.30)),
            ),
        )
    if reactor_type == "uasb":
        kwargs: dict[str, Any] = {"reactor_type": "uasb"}
        if "biomass_washout_factor" in vc:
            kwargs["biomass_washout_factor"] = float(vc["biomass_washout_factor"])
        return ReactorConfig(**kwargs)  # type: ignore[arg-type]
    if reactor_type == "plug_flow":
        return ReactorConfig(
            reactor_type="plug_flow",
            segments=int(vc.get("segments", 6)),
        )
    return ReactorConfig(reactor_type=reactor_type)  # type: ignore[arg-type]


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
    ammonia_inhibition_mode: str = "simple",
    variant_config: dict[str, Any] | None = None,
    blend: CoDigestionBlend | None = None,
    full_extensions: list[str] | None = None,
    full_initial_state_overrides: dict[str, float] | None = None,
    full_influent_state_overrides: dict[str, float] | None = None,
    full_extension_parameter_overrides: dict[str, float] | None = None,
    custom_substrate_values: dict[str, float | str] | None = None,
    hydraulic_mode: str = "hrt",
) -> SimulationResult:
    """Executa simulação ADM1 com os parâmetros fornecidos.

    Args:
        hydraulic_mode: ``"hrt"`` para definir HRT diretamente, ou ``"flow_rate"``
            para derivar HRT = V/Q (nesse caso, ``operating_values`` deve conter
            ``flow_rate_m3_day``).
        custom_substrate_values: Valores de substrato personalizado salvo pelo
            usuário. Usado quando ``substrate_mode == "custom"``.
    """
    # Se blend não for fornecido explicitamente, deriva do preset de co-digestão
    if blend is None and substrate_mode == "codigestion" and preset_id:
        blend = get_codigestion_blend(preset_id)

    feed, operating, note_link = build_feed_and_operating(
        substrate_mode=substrate_mode,
        preset_id=preset_id,
        manual_feed_values=manual_feed_values,
        operating_values=operating_values,
        blend=blend,
        custom_substrate_values=custom_substrate_values,
    )
    simulation = build_simulation_config(
        duration_days=duration_days,
        evaluation_points=evaluation_points,
        solver=solver,
        backend=backend,
        persist=persist,
        ammonia_inhibition_mode=ammonia_inhibition_mode,
        full_extensions=full_extensions,
        full_initial_state_overrides=full_initial_state_overrides,
        full_influent_state_overrides=full_influent_state_overrides,
        full_extension_parameter_overrides=full_extension_parameter_overrides,
    )
    reactor_config = _build_reactor_config(reactor_type, variant_config)
    kinetics = KineticParameters(ammonia_inhibition_mode=ammonia_inhibition_mode)  # type: ignore[arg-type]

    service = ADM1SimulationService()

    # Calcula Q e HRT efetivos para o metadado de resumo
    effective_volume = float(operating.volume_m3)
    effective_hrt = float(operating.hrt_days)
    effective_q = effective_volume / effective_hrt if effective_hrt > 0.0 else 0.0

    metadata: dict[str, Any] = {
        "ui_origin": "streamlit_w2_w7",
        "substrate_mode": substrate_mode,
        "ammonia_inhibition_mode": ammonia_inhibition_mode,
        "hydraulic_mode": hydraulic_mode,
        "effective_flow_rate_m3_day": round(effective_q, 4),
        "effective_hrt_days": round(effective_hrt, 4),
    }
    if preset_id:
        metadata["substrate_preset"] = preset_id
    if note_link:
        metadata["substrate_note_link"] = note_link
    if variant_config:
        metadata["variant_config"] = variant_config
    if full_extensions:
        metadata["full_extensions_requested"] = full_extensions
    if full_initial_state_overrides:
        metadata["full_initial_state_overrides_requested"] = dict(full_initial_state_overrides)
    if full_influent_state_overrides:
        metadata["full_influent_state_overrides_requested"] = dict(full_influent_state_overrides)
    if substrate_mode == "custom" and custom_substrate_values:
        metadata["custom_substrate_name"] = str(custom_substrate_values.get("name", ""))

    return service.simulate(
        reactor_config,
        feed=feed,
        blend=blend,
        operating_conditions=operating,
        simulation=simulation,
        parameters=kinetics,
        metadata=metadata,
    )




def compare_backends_for_result(
    result: SimulationResult,
    *,
    backends: tuple[str, ...] = ("pyadm1", "full"),
) -> dict[str, Any]:
    service = ADM1SimulationService()
    report = service.compare_backends(
        backends,
        reactor=result.reactor,
        operating_conditions=result.operating_conditions,
        feed=result.feed,
        initial_state=result.initial_state,
        parameters=result.parameters,
        simulation=result.simulation.model_copy(update={"persist": False}, deep=True),
    )
    return {key: value for key, value in report.items()}



def backend_comparison_frame(report: Mapping[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for index, entry in enumerate(report.get("entries", []), start=1):
        summary = entry.get("summary", {}) if isinstance(entry.get("summary"), dict) else {}
        deltas = entry.get("delta_vs_baseline", {}) if isinstance(entry.get("delta_vs_baseline"), dict) else {}
        methane_delta = deltas.get("methane_final_m3_day", {}) if isinstance(deltas.get("methane_final_m3_day"), dict) else {}
        biogas_delta = deltas.get("biogas_final_m3_day", {}) if isinstance(deltas.get("biogas_final_m3_day"), dict) else {}
        ph_delta = deltas.get("ph_final", {}) if isinstance(deltas.get("ph_final"), dict) else {}
        rows.append(
            {
                "ordem": index,
                "backend_requested": entry.get("backend_requested"),
                "backend_used": entry.get("backend_used"),
                "fallback_reason": entry.get("fallback_reason") or "",
                "methane_final_m3_day": round(float(summary.get("methane_final_m3_day", 0.0)), 6),
                "delta_methane_pct": round(float(methane_delta.get("relative_pct", 0.0)), 6),
                "biogas_final_m3_day": round(float(summary.get("biogas_final_m3_day", 0.0)), 6),
                "delta_biogas_pct": round(float(biogas_delta.get("relative_pct", 0.0)), 6),
                "ph_final": round(float(summary.get("ph_final", 0.0)), 6),
                "delta_ph_abs": round(float(ph_delta.get("absolute", 0.0)), 6),
                "vfa_final": round(float(summary.get("vfa_final", 0.0)), 6),
                "effluent_cod_final": round(float(summary.get("effluent_cod_final", 0.0)), 6),
                "stability_index": round(float(summary.get("stability_index", 0.0)), 6),
            }
        )
    return pd.DataFrame(rows)

def simulation_summary_rows(result: SimulationResult) -> list[dict[str, Any]]:
    metadata = result.metadata
    rows = [
        {"metric": "Metano final", "value": f"{result.summary.methane_final_m3_day:.3f} m3/d"},
        {"metric": "Biogas final", "value": f"{result.summary.biogas_final_m3_day:.3f} m3/d"},
        {"metric": "Fracao CH4 final", "value": f"{result.summary.ch4_fraction_final:.3f}"},
        {"metric": "pH final", "value": f"{result.summary.ph_final:.3f}"},
        {"metric": "VFA final", "value": f"{result.summary.vfa_final:.3f}"},
        {"metric": "Backend solicitado", "value": str(metadata.get("backend_requested", result.simulation.backend))},
        {"metric": "Backend usado", "value": str(metadata.get("backend_used", result.simulation.backend))},
        {"metric": "Simulation ID", "value": result.simulation_id},
    ]
    # Conditional metrics
    fan_series = result.series.get("free_ammonia_kgN_m3")
    if fan_series:
        rows.append({"metric": "Amônia livre final (FAN)", "value": f"{fan_series[-1]:.4f} kgN/m³"})
    inh_ac = result.series.get("inh_nh3_acetoclastic")
    if inh_ac:
        rows.append({"metric": "Inibição acetoclástica (NH₃)", "value": f"{inh_ac[-1]:.1%}"})
    cn_ratio = result.summary.cn_ratio if result.summary.cn_ratio is not None else metadata.get("cn_ratio")
    if cn_ratio is not None:
        rows.append({"metric": "Razão C/N", "value": f"{float(cn_ratio):.1f}"})
    blend_name = metadata.get("blend_name")
    if blend_name:
        components = metadata.get("blend_components", [])
        rows.append({"metric": "Blend", "value": f"{blend_name} ({', '.join(str(c) for c in components)})"})
    if str(metadata.get("backend_used", result.simulation.backend)) == "full":
        rows.append({"metric": "Full runtime", "value": str(metadata.get("full_model_runtime", "native"))})
        rows.append({"metric": "Full pH convergiu", "value": "sim" if bool(metadata.get("full_model_ph_converged", False)) else "nao"})
        rows.append({"metric": "Full it. max pH", "value": str(metadata.get("full_model_ph_iterations_max", "-"))})
        active_extensions = metadata.get("full_model_active_extensions", [])
        rows.append({"metric": "Full extensoes ativas", "value": ", ".join(str(item) for item in active_extensions) if active_extensions else "nenhuma"})
    return rows



def simulation_input_rows(result: SimulationResult) -> list[dict[str, Any]]:
    rows = [
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
    # Extensions group
    inh_mode = result.parameters.ammonia_inhibition_mode if result.parameters else result.metadata.get("ammonia_inhibition_mode", "simple")
    rows.append({"group": "Extensões", "parameter": "Modo inibição NH₃", "value": str(inh_mode)})
    if result.reactor.two_phase is not None:
        cfg = result.reactor.two_phase
        rows.extend([
            {"group": "Extensões", "parameter": "Fração vol. fase 1 (= HRT)", "value": f"{cfg.phase1_volume_fraction:.2f}"},
            {"group": "Extensões", "parameter": "pH setpoint fase 1 (reduzido)", "value": f"{cfg.phase1_ph_setpoint:.1f}"},
            {"group": "Extensões", "parameter": "pH setpoint fase 2 (reduzido)", "value": f"{cfg.phase2_ph_setpoint:.1f}"},
        ])
    if result.reactor.tpad is not None:
        cfg = result.reactor.tpad
        rows.extend([
            {"group": "Extensões", "parameter": "Temp. termofílica [C]", "value": f"{cfg.thermo_temperature_c:.1f}"},
            {"group": "Extensões", "parameter": "HRT termofílico [d]", "value": f"{cfg.thermo_hrt_days:.1f}"},
            {"group": "Extensões", "parameter": "Temp. mesofílica [C]", "value": f"{cfg.meso_temperature_c:.1f}"},
            {"group": "Extensões", "parameter": "HRT mesofílico [d]", "value": f"{cfg.meso_hrt_days:.1f}"},
            {"group": "Extensões", "parameter": "Fração vol. termofílica (derivado)", "value": f"{cfg.thermo_volume_fraction:.2f}"},
        ])
    if result.reactor.batch is not None:
        rows.append({"group": "Extensões", "parameter": "Fração inóculo", "value": f"{result.reactor.batch.inoculum_fraction:.2f}"})
    blend_name = result.metadata.get("blend_name")
    if blend_name:
        rows.append({"group": "Extensões", "parameter": "Blend (co-digestão)", "value": str(blend_name)})
    if str(result.metadata.get("backend_used", result.simulation.backend)) == "full":
        rows.extend(
            [
                {"group": "Backend full", "parameter": "Runtime", "value": str(result.metadata.get("full_model_runtime", "native"))},
                {"group": "Backend full", "parameter": "pH convergiu", "value": "sim" if bool(result.metadata.get("full_model_ph_converged", False)) else "nao"},
                {"group": "Backend full", "parameter": "H2 convergiu", "value": "sim" if bool(result.metadata.get("full_model_hydrogen_converged", False)) else "nao"},
                {"group": "Backend full", "parameter": "Iteracoes max pH", "value": str(result.metadata.get("full_model_ph_iterations_max", "-"))},
                {"group": "Backend full", "parameter": "Extensoes ativas", "value": ", ".join(str(item) for item in result.metadata.get("full_model_active_extensions", [])) or "nenhuma"},
            ]
        )
    return rows



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



