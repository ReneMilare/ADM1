from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

STATE_NAMES = (
    "particulate_cod",
    "soluble_cod",
    "acetate",
    "propionate",
    "hydrogen",
    "acidogens",
    "propionate_biomass",
    "acetoclastic_biomass",
    "hydrogenotrophic_biomass",
    "inorganic_nitrogen",
    "alkalinity",
)
REACTOR_TYPES = ("cstr", "uasb", "plug_flow")
SIMULATION_BACKENDS = ("reduced", "pyadm1", "auto")
OBJECTIVE_NAMES = (
    "methane_final_m3_day",
    "methane_peak_m3_day",
    "methane_cumulative_m3",
    "biogas_final_m3_day",
    "ch4_fraction_final",
    "ph_final",
    "vfa_final",
    "effluent_cod_final",
    "volatile_solids_proxy",
    "stability_index",
)


class StrictModel(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid", str_strip_whitespace=True)


class FeedDefinition(StrictModel):
    name: str = Field(default="BSM2-like sludge feed")
    particulate_cod: float = Field(default=14.0, ge=0.0, description="Influent particulate COD concentration [kgCOD/m3].")
    soluble_cod: float = Field(default=5.5, ge=0.0, description="Influent readily biodegradable COD [kgCOD/m3].")
    acetate: float = Field(default=0.6, ge=0.0, description="Influent acetate equivalent [kgCOD/m3].")
    propionate: float = Field(default=0.25, ge=0.0, description="Influent propionate equivalent [kgCOD/m3].")
    hydrogen: float = Field(default=0.001, ge=0.0, description="Influent dissolved hydrogen proxy [kgCOD/m3].")
    inorganic_nitrogen: float = Field(default=1.3, ge=0.0, description="Influent inorganic nitrogen proxy [kgN/m3].")
    alkalinity: float = Field(default=4.8, gt=0.0, description="Influent alkalinity proxy [kmol/m3 equivalent].")
    ph: float = Field(default=7.1, ge=5.0, le=8.5, description="Influent pH.")
    flow_rate_m3_day: float | None = Field(default=None, gt=0.0, description="Influent flow. If omitted, volume/HRT is used.")

    def to_state_vector(self) -> list[float]:
        return [
            self.particulate_cod,
            self.soluble_cod,
            self.acetate,
            self.propionate,
            self.hydrogen,
            0.0,
            0.0,
            0.0,
            0.0,
            self.inorganic_nitrogen,
            self.alkalinity,
        ]


class InitialState(StrictModel):
    particulate_cod: float = Field(default=11.0, ge=0.0)
    soluble_cod: float = Field(default=4.0, ge=0.0)
    acetate: float = Field(default=1.2, ge=0.0)
    propionate: float = Field(default=0.6, ge=0.0)
    hydrogen: float = Field(default=0.015, ge=0.0)
    acidogens: float = Field(default=1.53, ge=0.0)
    propionate_biomass: float = Field(default=0.27, ge=0.0)
    acetoclastic_biomass: float = Field(default=0.9, ge=0.0)
    hydrogenotrophic_biomass: float = Field(default=0.35, ge=0.0)
    inorganic_nitrogen: float = Field(default=1.4, ge=0.0)
    alkalinity: float = Field(default=5.1, gt=0.0)

    def to_vector(self) -> list[float]:
        return [
            self.particulate_cod,
            self.soluble_cod,
            self.acetate,
            self.propionate,
            self.hydrogen,
            self.acidogens,
            self.propionate_biomass,
            self.acetoclastic_biomass,
            self.hydrogenotrophic_biomass,
            self.inorganic_nitrogen,
            self.alkalinity,
        ]


class ReactorConfig(StrictModel):
    reactor_type: Literal["cstr", "uasb", "plug_flow"] = Field(default="cstr")
    name: str | None = Field(default=None)
    segments: int = Field(default=6, ge=1, le=20, description="Only used for plug-flow approximated as tanks in series.")
    biomass_washout_factor: float | None = Field(default=None, gt=0.0, le=1.0)
    gas_capture_efficiency: float | None = Field(default=None, ge=0.0, le=1.0)
    hydrolysis_multiplier: float | None = Field(default=None, gt=0.1, le=3.0)

    @model_validator(mode="before")
    @classmethod
    def validate_segments(cls, payload: Any) -> Any:
        if not isinstance(payload, dict):
            return payload
        data = dict(payload)
        reactor_type = str(data.get("reactor_type", "cstr"))
        segments = int(data.get("segments", 6))
        if reactor_type != "plug_flow":
            data["segments"] = 1
        elif segments < 2:
            raise ValueError("plug_flow reactors require at least 2 segments")
        if not data.get("name"):
            data["name"] = reactor_type.upper().replace("_", "-")
        return data


class OperatingConditions(StrictModel):
    volume_m3: float = Field(default=3000.0, gt=0.0)
    temperature_c: float = Field(default=35.0, ge=15.0, le=60.0)
    hrt_days: float = Field(default=20.0, gt=0.1)
    pressure_atm: float = Field(default=1.0, gt=0.1, le=5.0)


class KineticParameters(StrictModel):
    k_hyd: float = Field(default=0.45, gt=0.0)
    k_m_su: float = Field(default=0.85, gt=0.0)
    k_m_pro: float = Field(default=0.42, gt=0.0)
    k_m_ac: float = Field(default=0.35, gt=0.0)
    k_m_h2: float = Field(default=1.05, gt=0.0)
    k_s_su: float = Field(default=1.1, gt=0.0)
    k_s_pro: float = Field(default=0.25, gt=0.0)
    k_s_ac: float = Field(default=0.15, gt=0.0)
    k_s_h2: float = Field(default=0.03, gt=0.0)
    acidogen_yield: float = Field(default=0.12, gt=0.0, le=1.0)
    propionate_yield: float = Field(default=0.04, gt=0.0, le=1.0)
    acetoclastic_yield: float = Field(default=0.055, gt=0.0, le=1.0)
    hydrogenotrophic_yield: float = Field(default=0.035, gt=0.0, le=1.0)
    decay_acidogens: float = Field(default=0.02, gt=0.0)
    decay_propionate_biomass: float = Field(default=0.02, gt=0.0)
    decay_acetoclastic: float = Field(default=0.015, gt=0.0)
    decay_hydrogenotrophic: float = Field(default=0.012, gt=0.0)
    hydrolysis_nitrogen_release: float = Field(default=0.03, ge=0.0, le=1.0)
    biomass_decay_nitrogen_content: float = Field(default=0.018, ge=0.0, le=1.0)
    gas_stripping_h2: float = Field(default=0.06, gt=0.0)
    ph_optimum: float = Field(default=7.05, ge=5.0, le=8.5)
    ph_tolerance: float = Field(default=0.55, gt=0.05)
    ammonia_inhibition_k: float = Field(default=2.8, gt=0.01)
    nitrogen_inhibition_threshold: float = Field(default=1.8, gt=0.0)
    hydrogen_inhibition_k: float = Field(default=0.08, gt=0.001)
    temperature_coefficient: float = Field(default=1.03, ge=1.0, le=1.2)
    gas_yield_ch4: float = Field(default=0.35, gt=0.0)
    gas_yield_co2: float = Field(default=0.38, gt=0.0)
    gas_yield_h2: float = Field(default=0.08, gt=0.0)


class SimulationConfig(StrictModel):
    duration_days: float = Field(default=60.0, gt=0.1)
    evaluation_points: int = Field(default=241, ge=21, le=4001)
    solver: Literal["BDF", "Radau"] = Field(default="BDF")
    backend: Literal["reduced", "pyadm1", "auto"] = Field(default="pyadm1")
    rtol: float = Field(default=1e-5, gt=0.0)
    atol: float = Field(default=1e-7, gt=0.0)
    persist: bool = Field(default=True)


class SimulationSummary(StrictModel):
    methane_final_m3_day: float
    methane_peak_m3_day: float
    methane_cumulative_m3: float
    biogas_final_m3_day: float
    ch4_fraction_final: float
    ph_final: float
    vfa_final: float
    effluent_cod_final: float
    effluent_particulate_final: float
    volatile_solids_proxy: float
    stability_index: float
    final_states: dict[str, float]


class SimulationResult(StrictModel):
    simulation_id: str
    created_at: str
    reactor: ReactorConfig
    operating_conditions: OperatingConditions
    feed: FeedDefinition
    initial_state: InitialState
    parameters: KineticParameters
    simulation: SimulationConfig
    time_days: list[float]
    series: dict[str, list[float]]
    summary: SimulationSummary
    metadata: dict[str, Any] = Field(default_factory=dict)


class SensitivityPoint(StrictModel):
    delta_fraction: float
    parameter_value: float
    objective_value: float


class SensitivityResult(StrictModel):
    parameter_path: str
    objective: str
    baseline_value: float
    baseline_objective: float
    points: list[SensitivityPoint]


class ScenarioComparisonEntry(StrictModel):
    simulation_id: str
    reactor_type: str
    backend_used: str
    methane_final_m3_day: float
    methane_cumulative_m3: float
    biogas_final_m3_day: float
    ch4_fraction_final: float
    ph_final: float
    vfa_final: float
    effluent_cod_final: float


class ScenarioComparison(StrictModel):
    scenario_count: int
    scenarios: list[ScenarioComparisonEntry]


class OptimizationEvaluation(StrictModel):
    parameter_value: float
    objective_value: float


class OptimizationResult(StrictModel):
    parameter_path: str
    objective: str
    goal: Literal["maximize", "minimize"]
    best_value: float
    best_objective: float
    simulation_id: str
    evaluations: list[OptimizationEvaluation]


class CalibrationPoint(StrictModel):
    time_days: float = Field(ge=0.0)
    observed_methane_m3_day: float = Field(ge=0.0)


class CalibrationResult(StrictModel):
    parameter_path: str
    initial_value: float
    calibrated_value: float
    rmse_before: float
    rmse_after: float
    simulation_id: str
