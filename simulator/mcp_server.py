from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from simulator.core.models import (
    BatchConfig,
    CalibrationPoint,
    CoDigestionBlend,
    FeedDefinition,
    KineticParameters,
    OperatingConditions,
    ReactorConfig,
    SimulationConfig,
    SubstrateFraction,
    TPADConfig,
    TwoPhaseConfig,
)
from simulator.design_pipeline import ADM1DesignPipeline, SUBSTRATE_ALIASES, SUBSTRATE_PRESETS
from simulator.full_model import list_registered_extensions as _list_registered_extensions
from simulator.service import ADM1SimulationService
from simulator.validation import run_phase3_validation as run_phase3_validation_report

mcp = FastMCP("adm1_simulator_mcp")
_service: ADM1SimulationService | None = None
_pipeline: ADM1DesignPipeline | None = None


def _get_service() -> ADM1SimulationService:
    global _service
    if _service is None:
        _service = ADM1SimulationService()
    return _service


def _get_pipeline() -> ADM1DesignPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = ADM1DesignPipeline(service=_get_service())
    return _pipeline


class SimulateReactorInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    reactor_type: str = Field(..., description="One of: cstr, uasb, plug_flow, two_phase, tpad, batch.")
    backend: str = Field(default="pyadm1", description="One of: reduced, pyadm1, full or auto.")
    substrate: str = Field(default="generic_sludge", description="Label saved with the scenario metadata.")
    volume_m3: float = Field(default=3000.0, gt=0.0)
    temperature_c: float = Field(default=35.0, ge=15.0, le=60.0)
    hrt_days: float = Field(default=20.0, gt=0.1)
    duration_days: float = Field(default=60.0, gt=0.1)
    feed_cod_kg_m3: float = Field(default=19.5, gt=0.0)
    particulate_fraction: float = Field(default=0.72, ge=0.0, le=0.95)
    acetate_fraction: float = Field(default=0.06, ge=0.0, le=0.3)
    propionate_fraction: float = Field(default=0.03, ge=0.0, le=0.3)
    ammonium_kg_n_m3: float = Field(default=1.3, ge=0.0)
    alkalinity_kmol_m3: float = Field(default=4.8, gt=0.0)
    ph: float = Field(default=7.1, ge=5.0, le=8.5)
    segments: int = Field(default=6, ge=2, le=20)
    ammonia_inhibition_mode: str = Field(default="simple", description="One of: simple or fan.")
    full_extensions: list[str] = Field(default_factory=list, description="Active extensions for the full backend, e.g. ['srb', 'lactate']. Use list_extensions to see available options.")
    full_extension_parameter_overrides: dict[str, float] = Field(default_factory=dict, description="Parameter overrides for extensions, e.g. {'K_I_H2S': 0.01}.")
    full_initial_state_overrides: dict[str, float] = Field(default_factory=dict, description="Initial state overrides for extensions, e.g. {'S_SO4': 0.005}.")


class ProfileInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    simulation_id: str = Field(..., min_length=5)


class CompareScenariosInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    simulation_ids: list[str] = Field(..., min_length=2, description="List of persisted simulation identifiers.")


class CompareBackendsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    reactor_type: str = Field(default="cstr", description="One of: cstr, uasb, plug_flow, two_phase, tpad, batch.")
    backends: list[str] = Field(default_factory=lambda: ["pyadm1", "full"], min_length=2)
    substrate: str = Field(default="generic_sludge", description="Label saved with the scenario metadata.")
    volume_m3: float = Field(default=3000.0, gt=0.0)
    temperature_c: float = Field(default=35.0, ge=15.0, le=60.0)
    hrt_days: float = Field(default=20.0, gt=0.1)
    duration_days: float = Field(default=60.0, gt=0.1)
    feed_cod_kg_m3: float = Field(default=19.5, gt=0.0)
    particulate_fraction: float = Field(default=0.72, ge=0.0, le=0.95)
    acetate_fraction: float = Field(default=0.06, ge=0.0, le=0.3)
    propionate_fraction: float = Field(default=0.03, ge=0.0, le=0.3)
    ammonium_kg_n_m3: float = Field(default=1.3, ge=0.0)
    alkalinity_kmol_m3: float = Field(default=4.8, gt=0.0)
    ph: float = Field(default=7.1, ge=5.0, le=8.5)
    segments: int = Field(default=6, ge=2, le=20)
    ammonia_inhibition_mode: str = Field(default="simple", description="One of: simple or fan.")
    full_extensions: list[str] = Field(default_factory=list, description="Active extensions for the full backend, e.g. ['srb', 'lactate'].")
    full_extension_parameter_overrides: dict[str, float] = Field(default_factory=dict, description="Parameter overrides for extensions.")
    full_initial_state_overrides: dict[str, float] = Field(default_factory=dict, description="Initial state overrides for extensions.")


class OptimizeParameterInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    parameter_path: str = Field(..., description="Example: kinetics.k_hyd or operating.temperature_c.")
    objective: str = Field(default="methane_final_m3_day")
    goal: str = Field(default="maximize")
    minimum: float = Field(...)
    maximum: float = Field(...)
    steps: int = Field(default=7, ge=3, le=21)
    reactor_type: str = Field(default="cstr")
    backend: str = Field(default="pyadm1", description="One of: reduced, pyadm1, full or auto.")
    volume_m3: float = Field(default=3000.0, gt=0.0)
    temperature_c: float = Field(default=35.0, ge=15.0, le=60.0)
    hrt_days: float = Field(default=20.0, gt=0.1)
    duration_days: float = Field(default=60.0, gt=0.1)


class CalibrateModelInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    experimental_points_json: str = Field(
        ...,
        description='JSON array like [{"time_days": 5, "observed_methane_m3_day": 120.0}, ...]',
    )
    parameter_path: str = Field(default="kinetics.k_hyd")
    minimum: float = Field(default=0.1)
    maximum: float = Field(default=1.5)
    reactor_type: str = Field(default="cstr")
    backend: str = Field(default="pyadm1", description="One of: reduced, pyadm1, full or auto.")
    volume_m3: float = Field(default=3000.0, gt=0.0)
    temperature_c: float = Field(default=35.0, ge=15.0, le=60.0)
    hrt_days: float = Field(default=20.0, gt=0.1)
    duration_days: float = Field(default=60.0, gt=0.1)


class ValidatePhase3Input(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    include_openmodelica: bool = Field(default=True)


class CoDigestionComponentInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    name: str = Field(...)
    fraction: float = Field(..., gt=0.0, le=1.0)


class DesignReactorInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    substrate: str = Field(..., description="Preset name such as 'Lodo de Esgoto', 'Residuos Alimentares', 'Residuos Agricolas' or a co-digestion preset.")
    design_goal: str = Field(default="balanced", description="One of: balanced, maximize_methane, maximize_stability, minimize_effluent_cod.")
    backend: str = Field(default="auto", description="One of: reduced, pyadm1, full or auto.")
    volume_m3: float | None = Field(default=None, gt=0.0)
    temperature_c: float | None = Field(default=None, ge=15.0, le=60.0)
    hrt_days: float | None = Field(default=None, gt=0.1)
    duration_days: float = Field(default=45.0, gt=0.1)
    evaluation_points: int = Field(default=181, ge=21, le=4001)
    candidate_reactors: list[str] = Field(default_factory=lambda: ["cstr", "uasb", "plug_flow"])
    persist_note: bool = Field(default=False)
    note_title: str | None = Field(default=None)
    full_extensions: list[str] = Field(default_factory=list, description="Active extensions for the full backend, e.g. ['srb', 'lactate'].")
    full_extension_parameter_overrides: dict[str, float] = Field(default_factory=dict, description="Parameter overrides for extensions.")
    full_initial_state_overrides: dict[str, float] = Field(default_factory=dict, description="Initial state overrides for extensions.")


def _build_feed(
    *,
    feed_cod_kg_m3: float,
    particulate_fraction: float,
    acetate_fraction: float,
    propionate_fraction: float,
    ammonium_kg_n_m3: float,
    alkalinity_kmol_m3: float,
    ph: float,
    substrate: str,
) -> FeedDefinition:
    particulate_cod = feed_cod_kg_m3 * particulate_fraction
    acetate = feed_cod_kg_m3 * acetate_fraction
    propionate = feed_cod_kg_m3 * propionate_fraction
    soluble_cod = max(feed_cod_kg_m3 - particulate_cod - acetate - propionate, 0.2)
    return FeedDefinition(
        name=substrate,
        particulate_cod=particulate_cod,
        soluble_cod=soluble_cod,
        acetate=acetate,
        propionate=propionate,
        inorganic_nitrogen=ammonium_kg_n_m3,
        alkalinity=alkalinity_kmol_m3,
        ph=ph,
    )


def _build_kinetics(ammonia_inhibition_mode: str) -> KineticParameters:
    return KineticParameters(ammonia_inhibition_mode=ammonia_inhibition_mode)


def _resolve_preset_feed(name: str) -> FeedDefinition:
    normalized = name.casefold().strip()
    preset_id = SUBSTRATE_ALIASES.get(normalized, normalized)
    if preset_id not in SUBSTRATE_PRESETS:
        raise ValueError(f"Unsupported substrate preset '{name}'.")
    return SUBSTRATE_PRESETS[preset_id]["feed"].model_copy(deep=True)


def _build_blend_from_json(substrates_json: str) -> CoDigestionBlend:
    try:
        raw_components = json.loads(substrates_json)
    except json.JSONDecodeError as exc:
        raise ValueError("substrates_json must be a valid JSON array.") from exc
    components = [CoDigestionComponentInput.model_validate(item) for item in raw_components]
    fractions = [
        SubstrateFraction(feed=_resolve_preset_feed(component.name), volume_fraction=component.fraction)
        for component in components
    ]
    names = " + ".join(component.feed.name for component in fractions)
    return CoDigestionBlend(name=f"Co-digestion {names}", components=fractions)


def _result_payload(result) -> dict[str, object]:
    payload: dict[str, object] = {
        "simulation_id": result.simulation_id,
        "reactor_type": result.reactor.reactor_type,
        "backend_requested": result.metadata.get("backend_requested"),
        "backend_used": result.metadata.get("backend_used"),
        "fallback_reason": result.metadata.get("backend_fallback_reason"),
        "summary": result.summary.model_dump(),
    }
    if str(result.metadata.get("backend_used", "")) == "full":
        payload["diagnostics"] = {
            "full_model_runtime": result.metadata.get("full_model_runtime"),
            "full_model_ph_converged": result.metadata.get("full_model_ph_converged"),
            "full_model_hydrogen_converged": result.metadata.get("full_model_hydrogen_converged"),
            "full_model_ph_iterations_max": result.metadata.get("full_model_ph_iterations_max"),
            "full_model_hydrogen_iterations_max": result.metadata.get("full_model_hydrogen_iterations_max"),
            "full_model_active_extensions": result.metadata.get("full_model_active_extensions", []),
        }
    return payload




@mcp.tool(
    name="simulate_reactor",
    annotations={
        "title": "Simulate ADM1 Reactor",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def simulate_reactor(
    reactor_type: str,
    backend: str = "pyadm1",
    substrate: str = "generic_sludge",
    volume_m3: float = 3000.0,
    temperature_c: float = 35.0,
    hrt_days: float = 20.0,
    duration_days: float = 60.0,
    feed_cod_kg_m3: float = 19.5,
    particulate_fraction: float = 0.72,
    acetate_fraction: float = 0.06,
    propionate_fraction: float = 0.03,
    ammonium_kg_n_m3: float = 1.3,
    alkalinity_kmol_m3: float = 4.8,
    ph: float = 7.1,
    segments: int = 6,
    ammonia_inhibition_mode: str = "simple",
    full_extensions: list[str] | None = None,
    full_extension_parameter_overrides: dict[str, float] | None = None,
    full_initial_state_overrides: dict[str, float] | None = None,
) -> str:
    """Run a persisted ADM1-oriented simulation for a configured reactor."""

    params = SimulateReactorInput(
        reactor_type=reactor_type,
        backend=backend,
        substrate=substrate,
        volume_m3=volume_m3,
        temperature_c=temperature_c,
        hrt_days=hrt_days,
        duration_days=duration_days,
        feed_cod_kg_m3=feed_cod_kg_m3,
        particulate_fraction=particulate_fraction,
        acetate_fraction=acetate_fraction,
        propionate_fraction=propionate_fraction,
        ammonium_kg_n_m3=ammonium_kg_n_m3,
        alkalinity_kmol_m3=alkalinity_kmol_m3,
        ph=ph,
        segments=segments,
        ammonia_inhibition_mode=ammonia_inhibition_mode,
        full_extensions=full_extensions or [],
        full_extension_parameter_overrides=full_extension_parameter_overrides or {},
        full_initial_state_overrides=full_initial_state_overrides or {},
    )
    feed = _build_feed(
        feed_cod_kg_m3=params.feed_cod_kg_m3,
        particulate_fraction=params.particulate_fraction,
        acetate_fraction=params.acetate_fraction,
        propionate_fraction=params.propionate_fraction,
        ammonium_kg_n_m3=params.ammonium_kg_n_m3,
        alkalinity_kmol_m3=params.alkalinity_kmol_m3,
        ph=params.ph,
        substrate=params.substrate,
    )
    reactor_config = ReactorConfig(
        reactor_type=params.reactor_type,
        segments=params.segments if params.reactor_type == "plug_flow" else 1,
    )
    operating = OperatingConditions(volume_m3=params.volume_m3, temperature_c=params.temperature_c, hrt_days=params.hrt_days)
    simulation = SimulationConfig(
        duration_days=params.duration_days,
        backend=params.backend,
        full_extensions=params.full_extensions,
        full_extension_parameter_overrides=params.full_extension_parameter_overrides,
        full_initial_state_overrides=params.full_initial_state_overrides,
    )
    result = _get_service().simulate(
        reactor=reactor_config,
        operating_conditions=operating,
        feed=feed,
        simulation=simulation,
        parameters=_build_kinetics(params.ammonia_inhibition_mode),
        metadata={"substrate": params.substrate},
    )
    return json.dumps(_result_payload(result), ensure_ascii=False, indent=2)


@mcp.tool(
    name="simulate_codigestion",
    annotations={
        "title": "Simulate Co-digestion",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def simulate_codigestion(
    reactor_type: str,
    substrates_json: str,
    backend: str = "auto",
    volume_m3: float = 3000.0,
    temperature_c: float = 35.0,
    hrt_days: float = 20.0,
    duration_days: float = 60.0,
    ammonia_inhibition_mode: str = "fan",
    segments: int = 6,
    full_extensions: list[str] | None = None,
    full_extension_parameter_overrides: dict[str, float] | None = None,
    full_initial_state_overrides: dict[str, float] | None = None,
) -> str:
    """Simulate weighted co-digestion of multiple substrate presets."""

    blend = _build_blend_from_json(substrates_json)
    reactor_config = ReactorConfig(reactor_type=reactor_type, segments=segments if reactor_type == "plug_flow" else 1)
    operating = OperatingConditions(volume_m3=volume_m3, temperature_c=temperature_c, hrt_days=hrt_days)
    simulation = SimulationConfig(
        duration_days=duration_days,
        backend=backend,
        full_extensions=full_extensions or [],
        full_extension_parameter_overrides=full_extension_parameter_overrides or {},
        full_initial_state_overrides=full_initial_state_overrides or {},
    )
    result = _get_service().simulate(
        reactor=reactor_config,
        operating_conditions=operating,
        blend=blend,
        simulation=simulation,
        parameters=_build_kinetics(ammonia_inhibition_mode),
        metadata={"substrate": blend.name},
    )
    return json.dumps(_result_payload(result), ensure_ascii=False, indent=2)


@mcp.tool(
    name="simulate_two_phase",
    annotations={
        "title": "Simulate Two-Phase AD",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def simulate_two_phase(
    backend: str = "auto",
    substrate: str = "generic_sludge",
    volume_m3: float = 3000.0,
    temperature_c: float = 35.0,
    hrt_days: float = 20.0,
    duration_days: float = 60.0,
    feed_cod_kg_m3: float = 19.5,
    particulate_fraction: float = 0.72,
    acetate_fraction: float = 0.06,
    propionate_fraction: float = 0.03,
    ammonium_kg_n_m3: float = 1.3,
    alkalinity_kmol_m3: float = 4.8,
    ph: float = 7.1,
    phase1_volume_fraction: float = 0.3,
    phase1_ph_setpoint: float = 5.5,
    phase2_ph_setpoint: float = 7.2,
    ammonia_inhibition_mode: str = "fan",
    full_extensions: list[str] | None = None,
    full_extension_parameter_overrides: dict[str, float] | None = None,
    full_initial_state_overrides: dict[str, float] | None = None,
) -> str:
    """Simulate two-phase anaerobic digestion with acidogenic and methanogenic stages."""

    feed = _build_feed(
        feed_cod_kg_m3=feed_cod_kg_m3,
        particulate_fraction=particulate_fraction,
        acetate_fraction=acetate_fraction,
        propionate_fraction=propionate_fraction,
        ammonium_kg_n_m3=ammonium_kg_n_m3,
        alkalinity_kmol_m3=alkalinity_kmol_m3,
        ph=ph,
        substrate=substrate,
    )
    reactor_config = ReactorConfig(
        reactor_type="two_phase",
        two_phase=TwoPhaseConfig(
            phase1_volume_fraction=phase1_volume_fraction,
            phase1_ph_setpoint=phase1_ph_setpoint,
            phase2_ph_setpoint=phase2_ph_setpoint,
        ),
    )
    operating = OperatingConditions(volume_m3=volume_m3, temperature_c=temperature_c, hrt_days=hrt_days)
    simulation = SimulationConfig(
        duration_days=duration_days,
        backend=backend,
        full_extensions=full_extensions or [],
        full_extension_parameter_overrides=full_extension_parameter_overrides or {},
        full_initial_state_overrides=full_initial_state_overrides or {},
    )
    result = _get_service().simulate(
        reactor=reactor_config,
        operating_conditions=operating,
        feed=feed,
        simulation=simulation,
        parameters=_build_kinetics(ammonia_inhibition_mode),
        metadata={"substrate": substrate},
    )
    return json.dumps(_result_payload(result), ensure_ascii=False, indent=2)


@mcp.tool(
    name="simulate_tpad",
    annotations={
        "title": "Simulate TPAD",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def simulate_tpad(
    backend: str = "auto",
    substrate: str = "generic_sludge",
    volume_m3: float = 3000.0,
    hrt_days: float = 18.0,
    duration_days: float = 60.0,
    feed_cod_kg_m3: float = 19.5,
    particulate_fraction: float = 0.72,
    acetate_fraction: float = 0.06,
    propionate_fraction: float = 0.03,
    ammonium_kg_n_m3: float = 1.3,
    alkalinity_kmol_m3: float = 4.8,
    ph: float = 7.1,
    thermo_temperature_c: float = 55.0,
    thermo_hrt_days: float = 3.0,
    meso_temperature_c: float = 35.0,
    meso_hrt_days: float = 15.0,
    ammonia_inhibition_mode: str = "fan",
    full_extensions: list[str] | None = None,
    full_extension_parameter_overrides: dict[str, float] | None = None,
    full_initial_state_overrides: dict[str, float] | None = None,
) -> str:
    """Simulate temperature-phased anaerobic digestion."""

    feed = _build_feed(
        feed_cod_kg_m3=feed_cod_kg_m3,
        particulate_fraction=particulate_fraction,
        acetate_fraction=acetate_fraction,
        propionate_fraction=propionate_fraction,
        ammonium_kg_n_m3=ammonium_kg_n_m3,
        alkalinity_kmol_m3=alkalinity_kmol_m3,
        ph=ph,
        substrate=substrate,
    )
    reactor_config = ReactorConfig(
        reactor_type="tpad",
        tpad=TPADConfig(
            thermo_temperature_c=thermo_temperature_c,
            thermo_hrt_days=thermo_hrt_days,
            meso_temperature_c=meso_temperature_c,
            meso_hrt_days=meso_hrt_days,
        ),
    )
    operating = OperatingConditions(volume_m3=volume_m3, temperature_c=meso_temperature_c, hrt_days=hrt_days)
    simulation = SimulationConfig(
        duration_days=duration_days,
        backend=backend,
        full_extensions=full_extensions or [],
        full_extension_parameter_overrides=full_extension_parameter_overrides or {},
        full_initial_state_overrides=full_initial_state_overrides or {},
    )
    result = _get_service().simulate(
        reactor=reactor_config,
        operating_conditions=operating,
        feed=feed,
        simulation=simulation,
        parameters=_build_kinetics(ammonia_inhibition_mode),
        metadata={"substrate": substrate},
    )
    return json.dumps(_result_payload(result), ensure_ascii=False, indent=2)


@mcp.tool(
    name="simulate_batch",
    annotations={
        "title": "Simulate Batch Reactor",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def simulate_batch(
    backend: str = "reduced",
    substrate: str = "generic_sludge",
    volume_m3: float = 100.0,
    temperature_c: float = 35.0,
    duration_days: float = 30.0,
    feed_cod_kg_m3: float = 19.5,
    particulate_fraction: float = 0.72,
    acetate_fraction: float = 0.06,
    propionate_fraction: float = 0.03,
    ammonium_kg_n_m3: float = 1.3,
    alkalinity_kmol_m3: float = 4.8,
    ph: float = 7.1,
    inoculum_fraction: float = 0.3,
    ammonia_inhibition_mode: str = "fan",
    full_extensions: list[str] | None = None,
    full_extension_parameter_overrides: dict[str, float] | None = None,
    full_initial_state_overrides: dict[str, float] | None = None,
) -> str:
    """Simulate a batch ADM1 case such as BMP tests."""

    feed = _build_feed(
        feed_cod_kg_m3=feed_cod_kg_m3,
        particulate_fraction=particulate_fraction,
        acetate_fraction=acetate_fraction,
        propionate_fraction=propionate_fraction,
        ammonium_kg_n_m3=ammonium_kg_n_m3,
        alkalinity_kmol_m3=alkalinity_kmol_m3,
        ph=ph,
        substrate=substrate,
    )
    reactor_config = ReactorConfig(reactor_type="batch", batch=BatchConfig(inoculum_fraction=inoculum_fraction))
    operating = OperatingConditions(volume_m3=volume_m3, temperature_c=temperature_c, hrt_days=max(duration_days, 0.1))
    simulation = SimulationConfig(
        duration_days=duration_days,
        backend=backend,
        full_extensions=full_extensions or [],
        full_extension_parameter_overrides=full_extension_parameter_overrides or {},
        full_initial_state_overrides=full_initial_state_overrides or {},
    )
    result = _get_service().simulate(
        reactor=reactor_config,
        operating_conditions=operating,
        feed=feed,
        simulation=simulation,
        parameters=_build_kinetics(ammonia_inhibition_mode),
        metadata={"substrate": substrate},
    )
    return json.dumps(_result_payload(result), ensure_ascii=False, indent=2)


@mcp.tool(
    name="get_biogas_production",
    annotations={
        "title": "Get Biogas Production Profile",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def get_biogas_production(simulation_id: str) -> str:
    """Return methane, CO2, H2 and total biogas profiles for a persisted scenario."""

    params = ProfileInput(simulation_id=simulation_id)
    payload = _get_service().get_biogas_production(params.simulation_id)
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool(
    name="get_vfa_profile",
    annotations={
        "title": "Get VFA Profile",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def get_vfa_profile(simulation_id: str) -> str:
    """Return acetate, propionate and total VFA profiles for a persisted scenario."""

    params = ProfileInput(simulation_id=simulation_id)
    payload = _get_service().get_vfa_profile(params.simulation_id)
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool(
    name="get_ph_profile",
    annotations={
        "title": "Get pH Profile",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def get_ph_profile(simulation_id: str) -> str:
    """Return pH and alkalinity profiles for a persisted scenario."""

    params = ProfileInput(simulation_id=simulation_id)
    payload = _get_service().get_ph_profile(params.simulation_id)
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool(
    name="compare_backends",
    annotations={
        "title": "Compare Backends for One Case",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def compare_backends(
    reactor_type: str = "cstr",
    backends: list[str] | None = None,
    substrate: str = "generic_sludge",
    volume_m3: float = 3000.0,
    temperature_c: float = 35.0,
    hrt_days: float = 20.0,
    duration_days: float = 60.0,
    feed_cod_kg_m3: float = 19.5,
    particulate_fraction: float = 0.72,
    acetate_fraction: float = 0.06,
    propionate_fraction: float = 0.03,
    ammonium_kg_n_m3: float = 1.3,
    alkalinity_kmol_m3: float = 4.8,
    ph: float = 7.1,
    segments: int = 6,
    ammonia_inhibition_mode: str = "simple",
    full_extensions: list[str] | None = None,
    full_extension_parameter_overrides: dict[str, float] | None = None,
    full_initial_state_overrides: dict[str, float] | None = None,
) -> str:
    """Compare explicit backend executions for the same ADM1 case."""

    params = CompareBackendsInput(
        reactor_type=reactor_type,
        backends=backends or ["pyadm1", "full"],
        substrate=substrate,
        volume_m3=volume_m3,
        temperature_c=temperature_c,
        hrt_days=hrt_days,
        duration_days=duration_days,
        feed_cod_kg_m3=feed_cod_kg_m3,
        particulate_fraction=particulate_fraction,
        acetate_fraction=acetate_fraction,
        propionate_fraction=propionate_fraction,
        ammonium_kg_n_m3=ammonium_kg_n_m3,
        alkalinity_kmol_m3=alkalinity_kmol_m3,
        ph=ph,
        segments=segments,
        ammonia_inhibition_mode=ammonia_inhibition_mode,
        full_extensions=full_extensions or [],
        full_extension_parameter_overrides=full_extension_parameter_overrides or {},
        full_initial_state_overrides=full_initial_state_overrides or {},
    )
    feed = _build_feed(
        feed_cod_kg_m3=params.feed_cod_kg_m3,
        particulate_fraction=params.particulate_fraction,
        acetate_fraction=params.acetate_fraction,
        propionate_fraction=params.propionate_fraction,
        ammonium_kg_n_m3=params.ammonium_kg_n_m3,
        alkalinity_kmol_m3=params.alkalinity_kmol_m3,
        ph=params.ph,
        substrate=params.substrate,
    )
    reactor_config = ReactorConfig(
        reactor_type=params.reactor_type,
        segments=params.segments if params.reactor_type == "plug_flow" else 1,
    )
    operating = OperatingConditions(volume_m3=params.volume_m3, temperature_c=params.temperature_c, hrt_days=params.hrt_days)
    simulation = SimulationConfig(
        duration_days=params.duration_days,
        backend=params.backends[0],
        persist=False,
        full_extensions=params.full_extensions,
        full_extension_parameter_overrides=params.full_extension_parameter_overrides,
        full_initial_state_overrides=params.full_initial_state_overrides,
    )
    payload = _get_service().compare_backends(
        params.backends,
        reactor=reactor_config,
        operating_conditions=operating,
        feed=feed,
        simulation=simulation,
        parameters=_build_kinetics(params.ammonia_inhibition_mode),
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool(
    name="compare_scenarios",
    annotations={
        "title": "Compare Persisted Scenarios",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def compare_scenarios(simulation_ids: list[str]) -> str:
    """Compare multiple persisted scenarios side by side."""

    params = CompareScenariosInput(simulation_ids=simulation_ids)
    payload = _get_service().compare_scenarios(params.simulation_ids)
    return payload.model_dump_json(indent=2)


@mcp.tool(
    name="optimize_parameter",
    annotations={
        "title": "Optimize ADM1 Parameter",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def optimize_parameter(
    parameter_path: str,
    minimum: float,
    maximum: float,
    objective: str = "methane_final_m3_day",
    goal: str = "maximize",
    steps: int = 7,
    reactor_type: str = "cstr",
    backend: str = "pyadm1",
    volume_m3: float = 3000.0,
    temperature_c: float = 35.0,
    hrt_days: float = 20.0,
    duration_days: float = 60.0,
) -> str:
    """Sweep a single parameter and persist the best scenario according to the chosen objective."""

    params = OptimizeParameterInput(
        parameter_path=parameter_path,
        minimum=minimum,
        maximum=maximum,
        objective=objective,
        goal=goal,
        steps=steps,
        reactor_type=reactor_type,
        backend=backend,
        volume_m3=volume_m3,
        temperature_c=temperature_c,
        hrt_days=hrt_days,
        duration_days=duration_days,
    )
    operating = OperatingConditions(volume_m3=params.volume_m3, temperature_c=params.temperature_c, hrt_days=params.hrt_days)
    simulation = SimulationConfig(duration_days=params.duration_days, backend=params.backend)
    payload = _get_service().optimize_parameter(
        params.parameter_path,
        minimum=params.minimum,
        maximum=params.maximum,
        steps=params.steps,
        objective=params.objective,
        goal=params.goal,
        reactor=params.reactor_type,
        operating_conditions=operating,
        simulation=simulation,
    )
    return payload.model_dump_json(indent=2)


@mcp.tool(
    name="calibrate_model",
    annotations={
        "title": "Calibrate ADM1 Parameter",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def calibrate_model(
    experimental_points_json: str,
    parameter_path: str = "kinetics.k_hyd",
    minimum: float = 0.1,
    maximum: float = 1.5,
    reactor_type: str = "cstr",
    backend: str = "pyadm1",
    volume_m3: float = 3000.0,
    temperature_c: float = 35.0,
    hrt_days: float = 20.0,
    duration_days: float = 60.0,
) -> str:
    """Fit a single kinetic parameter to methane observations supplied as JSON."""

    params = CalibrateModelInput(
        experimental_points_json=experimental_points_json,
        parameter_path=parameter_path,
        minimum=minimum,
        maximum=maximum,
        reactor_type=reactor_type,
        backend=backend,
        volume_m3=volume_m3,
        temperature_c=temperature_c,
        hrt_days=hrt_days,
        duration_days=duration_days,
    )
    try:
        raw_points = json.loads(params.experimental_points_json)
    except json.JSONDecodeError as exc:
        raise ValueError("experimental_points_json must be a valid JSON array of calibration points.") from exc
    experimental_data = [CalibrationPoint.model_validate(item) for item in raw_points]
    operating = OperatingConditions(volume_m3=params.volume_m3, temperature_c=params.temperature_c, hrt_days=params.hrt_days)
    simulation = SimulationConfig(duration_days=params.duration_days, backend=params.backend)
    payload = _get_service().calibrate_model(
        experimental_data,
        parameter_path=params.parameter_path,
        minimum=params.minimum,
        maximum=params.maximum,
        reactor=params.reactor_type,
        operating_conditions=operating,
        simulation=simulation,
    )
    return payload.model_dump_json(indent=2)


@mcp.tool(
    name="run_phase3_validation",
    annotations={
        "title": "Run Phase 3 Validation",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def run_phase3_validation(include_openmodelica: bool = True) -> str:
    """Run the Phase 3 validation workflow, including local backend benchmark and OpenModelica readiness checks."""

    params = ValidatePhase3Input(include_openmodelica=include_openmodelica)
    report, output_dir = run_phase3_validation_report(include_openmodelica=params.include_openmodelica)
    payload = {
        "output_dir": str(output_dir),
        "openmodelica_status": report["openmodelica"]["status"],
        "prefer_pyadm1_for_cstr_fidelity": report["conclusion"]["prefer_pyadm1_for_cstr_fidelity"],
        "promote_pyadm1_as_global_default": report["conclusion"]["promote_pyadm1_as_global_default"],
        "rationale": report["conclusion"]["rationale"],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool(
    name="design_reactor",
    annotations={
        "title": "Design Reactor Study",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def design_reactor(
    substrate: str,
    design_goal: str = "balanced",
    backend: str = "auto",
    volume_m3: float | None = None,
    temperature_c: float | None = None,
    hrt_days: float | None = None,
    duration_days: float = 45.0,
    evaluation_points: int = 181,
    candidate_reactors: list[str] | None = None,
    persist_note: bool = False,
    note_title: str | None = None,
    full_extensions: list[str] | None = None,
    full_extension_parameter_overrides: dict[str, float] | None = None,
    full_initial_state_overrides: dict[str, float] | None = None,
) -> str:
    """Run the design workflow for a substrate preset and recommend a reactor configuration."""

    params = DesignReactorInput(
        substrate=substrate,
        design_goal=design_goal,
        backend=backend,
        volume_m3=volume_m3,
        temperature_c=temperature_c,
        hrt_days=hrt_days,
        duration_days=duration_days,
        evaluation_points=evaluation_points,
        candidate_reactors=candidate_reactors or ["cstr", "uasb", "plug_flow"],
        persist_note=persist_note,
        note_title=note_title,
        full_extensions=full_extensions or [],
        full_extension_parameter_overrides=full_extension_parameter_overrides or {},
        full_initial_state_overrides=full_initial_state_overrides or {},
    )
    payload = _get_pipeline().run(
        substrate=params.substrate,
        design_goal=params.design_goal,
        backend=params.backend,
        volume_m3=params.volume_m3,
        temperature_c=params.temperature_c,
        hrt_days=params.hrt_days,
        duration_days=params.duration_days,
        evaluation_points=params.evaluation_points,
        reactor_candidates=params.candidate_reactors,
        persist_note=params.persist_note,
        note_title=params.note_title,
        active_extensions=params.full_extensions,
        extension_parameter_overrides=params.full_extension_parameter_overrides,
        extension_initial_state_overrides=params.full_initial_state_overrides,
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool(
    name="list_extensions",
    annotations={
        "title": "List Available Full Model Extensions",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def list_extensions() -> str:
    """List all registered ADM1 full model extensions with descriptions."""

    from simulator.full_model import resolve_full_model_assembly

    extensions = _list_registered_extensions()
    items = []
    for name in extensions:
        try:
            assembly = resolve_full_model_assembly([name])
            ext_states = [s for s in assembly.full_state_names if s not in ("X_tracer",)]
            items.append({
                "name": name,
                "total_states": len(assembly.full_state_names),
                "total_processes": len(assembly.full_process_names),
            })
        except Exception:
            items.append({"name": name, "error": "failed to resolve"})

    payload = {
        "available_extensions": list(extensions),
        "note": "Pass extension names in the 'full_extensions' parameter of simulate_reactor, design_reactor, etc. Backend must be 'full' to activate extensions.",
        "details": items,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
