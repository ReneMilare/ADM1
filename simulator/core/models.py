from __future__ import annotations

import math
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
REACTOR_TYPES = ("cstr", "uasb", "plug_flow", "two_phase", "tpad", "batch")
SIMULATION_BACKENDS = ("reduced", "pyadm1", "full", "auto")
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
    alkalinity: float = Field(default=4.8, gt=0.0, description="Influent alkalinity proxy for the reduced model [legacy equivalent scale].")
    sic_kmol_m3: float | None = Field(default=None, ge=0.0, description="Influent dissolved inorganic carbon S_IC for full ADM1 / PyADM1 [kmol/m3].")
    ph: float = Field(default=7.1, ge=5.0, le=8.5, description="Influent pH.")
    flow_rate_m3_day: float | None = Field(default=None, gt=0.0, description="Influent flow. If omitted, volume/HRT is used.")

    def to_state_vector(self) -> list[float]:
        return [
            self.particulate_cod,
            self.soluble_cod - self.acetate - self.propionate,
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

    @model_validator(mode="after")
    def validate_feed_composition(self) -> "FeedDefinition":
        # VFA fractions must be a subset of soluble COD
        vfa = self.acetate + self.propionate
        if vfa > self.soluble_cod + 1e-6:
            raise ValueError(
                f"Acetate ({self.acetate:.3f}) + propionate ({self.propionate:.3f}) "
                f"= {vfa:.3f} kgCOD/m³ exceeds soluble_cod ({self.soluble_cod:.3f} kgCOD/m³). "
                "VFAs must be a subset of soluble COD."
            )
        # At least some substrate must be present
        if self.particulate_cod + self.soluble_cod == 0.0:
            raise ValueError(
                "Total feed COD (particulate_cod + soluble_cod) must be > 0 kgCOD/m³. "
                "A feed with no substrate cannot sustain anaerobic digestion."
            )
        return self


class SubstrateFraction(StrictModel):
    feed: FeedDefinition
    volume_fraction: float = Field(gt=0.0, le=1.0, description="Fração volumétrica do substrato na mistura.")


class CoDigestionBlend(StrictModel):
    name: str = Field(default="Co-digestion blend")
    components: list[SubstrateFraction] = Field(min_length=2, max_length=10)

    @model_validator(mode="after")
    def validate_fractions_sum_to_one(self) -> "CoDigestionBlend":
        total = sum(component.volume_fraction for component in self.components)
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"As frações volumétricas devem somar 1.0, obtido {total:.4f}")
        return self

    def blend(self) -> FeedDefinition:
        numeric_fields = (
            "particulate_cod",
            "soluble_cod",
            "acetate",
            "propionate",
            "hydrogen",
            "inorganic_nitrogen",
            "alkalinity",
        )
        blended: dict[str, float | str | None] = {"name": self.name}
        for field in numeric_fields:
            blended[field] = sum(component.volume_fraction * getattr(component.feed, field) for component in self.components)
        if all(component.feed.sic_kmol_m3 is not None for component in self.components):
            blended["sic_kmol_m3"] = sum(
                component.volume_fraction * float(component.feed.sic_kmol_m3 or 0.0)
                for component in self.components
            )
        else:
            blended["sic_kmol_m3"] = None
        blended_h_plus = sum(component.volume_fraction * 10.0 ** (-component.feed.ph) for component in self.components)
        blended["ph"] = -math.log10(max(blended_h_plus, 1e-14))
        flow_terms = [
            component.volume_fraction * component.feed.flow_rate_m3_day
            for component in self.components
            if component.feed.flow_rate_m3_day is not None
        ]
        blended["flow_rate_m3_day"] = sum(flow_terms) if flow_terms and len(flow_terms) == len(self.components) else None
        return FeedDefinition(**blended)

    def cn_ratio(self) -> float:
        blended = self.blend()
        total_cod = blended.particulate_cod + blended.soluble_cod + blended.acetate + blended.propionate
        if blended.inorganic_nitrogen <= 1e-9:
            return float("inf")
        return total_cod / blended.inorganic_nitrogen


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
    sic_kmol_m3: float | None = Field(default=None, ge=0.0)

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


class TwoPhaseConfig(StrictModel):
    phase1_volume_fraction: float = Field(default=0.3, gt=0.1, lt=0.6, description="Fração de volume líquido na fase 1. Em CSTRs em série com mesma vazão, esta fração também define a fração de HRT da fase 1.")
    phase1_ph_setpoint: float = Field(default=5.5, ge=4.5, le=6.5, description="Setpoint de pH da fase acidogênica. Usado pelo modelo reduzido como heurística cinética; o modelo full calcula pH dinamicamente.")
    phase2_ph_setpoint: float = Field(default=7.2, ge=6.5, le=8.0, description="Setpoint de pH da fase metanogênica. Usado pelo modelo reduzido como heurística cinética; o modelo full calcula pH dinamicamente.")


class TPADConfig(StrictModel):
    thermo_temperature_c: float = Field(default=55.0, ge=45.0, le=65.0, description="Temperatura da fase termofílica [°C].")
    thermo_hrt_days: float = Field(default=3.0, gt=0.5, le=10.0, description="HRT da fase termofílica [dias].")
    meso_temperature_c: float = Field(default=35.0, ge=25.0, le=42.0, description="Temperatura da fase mesofílica [°C].")
    meso_hrt_days: float = Field(default=15.0, gt=5.0, le=40.0, description="HRT da fase mesofílica [dias].")

    @property
    def thermo_volume_fraction(self) -> float:
        """Derived: volume fraction of thermophilic phase = HRT_thermo / (HRT_thermo + HRT_meso)."""
        return self.thermo_hrt_days / (self.thermo_hrt_days + self.meso_hrt_days)


class BatchConfig(StrictModel):
    inoculum_fraction: float = Field(default=0.3, gt=0.05, le=0.8, description="Fração do volume total ocupada pelo inoculo.")


class ReactorConfig(StrictModel):
    reactor_type: Literal["cstr", "uasb", "plug_flow", "two_phase", "tpad", "batch"] = Field(default="cstr")
    name: str | None = Field(default=None)
    segments: int = Field(default=6, ge=1, le=20, description="Only used for plug-flow approximated as tanks in series.")
    biomass_washout_factor: float | None = Field(default=None, gt=0.0, le=1.0)
    gas_capture_efficiency: float | None = Field(default=None, ge=0.0, le=1.0)
    hydrolysis_multiplier: float | None = Field(default=None, gt=0.1, le=3.0)
    two_phase: TwoPhaseConfig | None = Field(default=None)
    tpad: TPADConfig | None = Field(default=None)
    batch: BatchConfig | None = Field(default=None)

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
        if reactor_type == "two_phase" and data.get("two_phase") is None:
            data["two_phase"] = {}
        if reactor_type == "tpad" and data.get("tpad") is None:
            data["tpad"] = {}
        if reactor_type == "batch" and data.get("batch") is None:
            data["batch"] = {}
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
    k_m_pro: float = Field(
        default=5.0,
        gt=0.0,
        description=(
            "Max specific propionate uptake rate [d⁻¹]. Must satisfy "
            "Y_pro × k_m_pro × Monod × H2_inhibition > decay + 1/HRT for biomass viability. "
            "At typical operating conditions (H2_inh≈0.72, Monod≈0.67, HRT=20d), "
            "minimum viable k_m_pro ≈ 3.7 d⁻¹. "
            "ADM1 reference: 13 d⁻¹; reduced-model value lower due to lumped-pathway approximation."
        ),
    )
    k_m_ac: float = Field(
        default=1.5,
        gt=0.0,
        description=(
            "Max specific acetate uptake rate [d⁻¹]. Must satisfy "
            "Y_ac × k_m_ac > decay + 1/HRT for biomass viability. "
            "Minimum for HRT=20d: (0.015 + 0.05)/0.055 ≈ 1.18 d⁻¹. "
            "ADM1 reference: 8 d⁻¹; reduced-model value lower due to lumped-pathway approximation."
        ),
    )
    k_m_h2: float = Field(
        default=3.5,
        gt=0.0,
        description=(
            "Max specific H2 uptake rate for hydrogenotrophic methanogenesis [d⁻¹]. "
            "Calibrated so that H2 production (from acidogenesis + propionate oxidation) "
            "is consumed fast enough to prevent runaway accumulation. "
            "NOTE: direct comparison with ADM1 k_m,h2=35 d⁻¹ is misleading — the "
            "'hydrogen' state in this model is a lumped proxy running at ~1000× the "
            "concentration of ADM1 dissolved H2. The effective first-order coefficient "
            "k_m_h2/k_s_h2 = 3.5/0.03 ≈ 117 m³/kgCOD/d governs the dynamics."
        ),
    )
    k_s_su: float = Field(default=1.1, gt=0.0)
    k_s_pro: float = Field(default=0.25, gt=0.0)
    k_s_ac: float = Field(default=0.15, gt=0.0)
    k_s_h2: float = Field(
        default=0.03,
        gt=0.0,
        description=(
            "Half-saturation constant for H2 in hydrogenotrophic methanogenesis [kgCOD/m³]. "
            "The 'hydrogen' state is a proxy (~1000× the concentration of actual dissolved H2 "
            "in ADM1 — Batstone et al. 2002 uses K_S,h2=7×10⁻⁶ kgCOD/m³ for dissolved H2). "
            "This value is correctly scaled for the proxy, so comparison with ADM1 absolute "
            "values is not meaningful. At typical steady-state (H2_proxy≈0.005), the model "
            "operates in the sub-saturated regime (h2/K_s ≈ 0.17), matching ADM1 kinetic regime."
        ),
    )
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
    ammonia_inhibition_mode: Literal["simple", "fan"] = Field(
        default="simple",
        description="'simple' usa TAN com threshold; 'fan' usa amônia livre com equilíbrio pH/temperatura.",
    )
    ammonia_inhibition_k: float = Field(default=2.8, gt=0.01)
    nitrogen_inhibition_threshold: float = Field(default=1.8, gt=0.0)
    ki_nh3_acidogens: float = Field(default=0.20, gt=0.0)
    ki_nh3_propionate: float = Field(default=0.10, gt=0.0)
    ki_nh3_acetoclastic: float = Field(default=0.015, gt=0.0)
    ki_nh3_hydrogenotrophic: float = Field(default=0.06, gt=0.0)
    hydrogen_inhibition_k: float = Field(default=0.08, gt=0.001)
    temperature_coefficient: float = Field(
        default=1.03,
        ge=1.0,
        le=1.2,
        description=(
            "Arrhenius Q10 per °C for acidogenic and methanogenic processes. "
            "ADM1 (Batstone et al. 2002) uses θ≈1.03 for acetoclastic/hydrogenotrophic methanogenesis."
        ),
    )
    hydrolysis_temperature_coefficient: float = Field(
        default=1.04,
        ge=1.0,
        le=1.2,
        description=(
            "Arrhenius Q10 per °C applied exclusively to hydrolysis. "
            "ADM1 (Batstone et al. 2002) uses θ≈1.04 for disintegration/hydrolysis, "
            "which is distinct from the methanogenic coefficient. Critical for TPAD "
            "where the thermophilic stage temperature differs from 35 °C."
        ),
    )
    gas_yield_ch4: float = Field(default=0.35, gt=0.0)
    gas_yield_co2: float = Field(default=0.38, gt=0.0)
    gas_yield_h2: float = Field(default=0.08, gt=0.0)


class SimulationConfig(StrictModel):
    duration_days: float = Field(default=60.0, gt=0.1, le=3650.0)
    evaluation_points: int = Field(default=241, ge=21, le=4001)
    solver: Literal["BDF", "Radau", "DOP853"] = Field(default="BDF")
    backend: Literal["reduced", "pyadm1", "full", "auto"] = Field(default="pyadm1")
    rtol: float = Field(default=1e-5, gt=0.0)
    atol: float = Field(default=1e-7, gt=0.0)
    persist: bool = Field(default=True)
    full_extensions: list[str] = Field(default_factory=list, max_length=20, description="Extens?es ativas do backend ADM1 full.")
    full_extension_parameter_overrides: dict[str, float] = Field(
        default_factory=dict,
        max_length=200,
        description="Overrides pontuais de par?metros do assembly full, incluindo extens?es ativas.",
    )
    full_initial_state_overrides: dict[str, float] = Field(
        default_factory=dict,
        max_length=200,
        description="Overrides pontuais do estado inicial completo do backend full, incluindo estados de extens?es.",
    )
    full_influent_state_overrides: dict[str, float] = Field(
        default_factory=dict,
        max_length=200,
        description="Overrides pontuais do afluente completo do backend full, incluindo estados de extens?es.",
    )

    @model_validator(mode="after")
    def normalize_full_extensions(self) -> "SimulationConfig":
        unique_extensions = list(dict.fromkeys(self.full_extensions))
        object.__setattr__(self, "full_extensions", unique_extensions)
        return self

    @model_validator(mode="after")
    def validate_solver_tolerances(self) -> "SimulationConfig":
        if self.atol > self.rtol:
            raise ValueError(
                f"atol ({self.atol:.2e}) must be ≤ rtol ({self.rtol:.2e}). "
                "Absolute tolerance must not exceed relative tolerance — "
                "inverted tolerances destabilize the ODE solver."
            )
        return self


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
    cn_ratio: float | None = Field(default=None)
    blend_components: list[str] | None = Field(default=None)
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


def get_feed_sic_kmol_m3(feed: Any) -> float | None:
    raw = getattr(feed, "sic_kmol_m3", None)
    if raw in (None, ""):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def coerce_simulation_result(value: Any) -> SimulationResult:
    if isinstance(value, SimulationResult):
        return value
    if isinstance(value, dict):
        payload = value
    elif hasattr(value, "model_dump"):
        payload = value.model_dump()
    else:
        raise TypeError("Unsupported simulation result payload.")
    return SimulationResult.model_validate(payload)


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
    time_days: float = Field(ge=0.0, le=3650.0)
    observed_methane_m3_day: float = Field(ge=0.0)


class CalibrationResult(StrictModel):
    parameter_path: str
    initial_value: float
    calibrated_value: float
    rmse_before: float
    rmse_after: float
    simulation_id: str

