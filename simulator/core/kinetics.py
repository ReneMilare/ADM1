from __future__ import annotations

import math

import numpy as np

from simulator.core.models import KineticParameters, STATE_NAMES

STATE_INDEX = {name: index for index, name in enumerate(STATE_NAMES)}
BIOMASS_INDICES = (
    STATE_INDEX["acidogens"],
    STATE_INDEX["propionate_biomass"],
    STATE_INDEX["acetoclastic_biomass"],
    STATE_INDEX["hydrogenotrophic_biomass"],
)
EPSILON = 1e-9

# COD mass-balance splits (Batstone et al., 2002 ADM1 — simplified reduced-model pathways).
# Each dict maps liquid product → fraction of consumed substrate COD that appears in that
# product.  The remainder (1 − Σsplits) equals the biomass yield stored in KineticParameters,
# so splits + yield = 1.00 for every pathway (verified by test_cod_balance_* tests).
#
# Acidogenesis of sugars/amino acids (ADM1 Table 3.1 stoichiometry, f_ac,su / f_pro,su / f_h2,su):
#   acetate:    0.55  (f_ac,su  — dominant fermentation product)
#   propionate: 0.20  (f_pro,su — secondary VFA pathway)
#   hydrogen:   0.13  (f_h2,su  — dissolved H2 produced)
#   acidogen_yield: 0.12  →  0.55 + 0.20 + 0.13 + 0.12 = 1.00 ✓
ACIDOGENESIS_SPLITS = {
    "acetate": 0.55,
    "propionate": 0.20,
    "hydrogen": 0.13,
}
# Propionate oxidation via syntrophic acetogenesis (ADM1 Table 3.1, f_ac,pro / f_h2,pro):
#   acetate:   0.57  (f_ac,pro  — main product of propionate β-oxidation)
#   hydrogen:  0.39  (f_h2,pro  — obligate H2 release by syntrophs)
#   propionate_yield: 0.04  →  0.57 + 0.39 + 0.04 = 1.00 ✓
PROPIONATE_SPLITS = {
    "acetate": 0.57,
    "hydrogen": 0.39,
}


def clip_state_vector(values: np.ndarray) -> np.ndarray:
    return np.maximum(np.asarray(values, dtype=float), 0.0)


def vector_to_dict(values: np.ndarray) -> dict[str, float]:
    vector = clip_state_vector(values)
    return {name: float(vector[index]) for index, name in enumerate(STATE_NAMES)}


def estimate_ph(state: np.ndarray, influent_ph: float, temperature_c: float) -> float:
    acetate = float(state[STATE_INDEX["acetate"]])
    propionate = float(state[STATE_INDEX["propionate"]])
    alkalinity = float(max(state[STATE_INDEX["alkalinity"]], EPSILON))
    vfa_total = acetate + propionate
    # Empirical reduced-model pH proxy (Batstone et al., 2002, simplified):
    #   - 0.25 / 0.2: buffer offsets that prevent log(0) when alkalinity or VFA are near zero,
    #     calibrated so that the ratio ≈ 1 at typical steady-state conditions (alk ≈ 4-6 kmol/m³,
    #     VFA ≈ 0-2 kgCOD/m³), yielding a pH correction close to 0.
    #   - 0.3: empirical log-scale gain; maps the alkalinity/VFA ratio to a ±0.3 pH unit range
    #     representative of ADM1 operating windows.
    #   - 0.015: temperature coefficient (pH/°C), consistent with the van-'t-Hoff influence on
    #     carbonate equilibrium; shifts pH by ≈ ±0.15 units over a ±10 °C deviation from 35 °C.
    ratio = (alkalinity + 0.25) / (vfa_total + 0.2)
    ph = influent_ph + 0.3 * math.log10(max(ratio, EPSILON)) + 0.015 * (temperature_c - 35.0)
    return float(np.clip(ph, 5.5, 8.3))


def _temperature_factor(temperature_c: float, params: KineticParameters) -> float:
    raw = params.temperature_coefficient ** (temperature_c - 35.0)
    return float(np.clip(raw, 0.25, 3.0))


def _ph_inhibition(ph: float, params: KineticParameters) -> float:
    penalty = math.exp(-((ph - params.ph_optimum) / max(params.ph_tolerance, EPSILON)) ** 2)
    return float(np.clip(penalty, 0.05, 1.0))


def _ammonia_inhibition(inorganic_nitrogen: float, params: KineticParameters) -> float:
    overload = max(inorganic_nitrogen - params.nitrogen_inhibition_threshold, 0.0)
    inhibition = 1.0 / (1.0 + overload / max(params.ammonia_inhibition_k, EPSILON))
    return float(np.clip(inhibition, 0.1, 1.0))


def _hydrogen_inhibition(hydrogen: float, params: KineticParameters) -> float:
    inhibition = 1.0 / (1.0 + hydrogen / max(params.hydrogen_inhibition_k, EPSILON))
    return float(np.clip(inhibition, 0.08, 1.0))


def reaction_vector(
    state: np.ndarray,
    *,
    influent_ph: float,
    temperature_c: float,
    params: KineticParameters,
    hydrolysis_multiplier: float,
    gas_capture_efficiency: float,
) -> tuple[np.ndarray, dict[str, float]]:
    values = clip_state_vector(state)
    particulate = float(values[STATE_INDEX["particulate_cod"]])
    soluble = float(values[STATE_INDEX["soluble_cod"]])
    acetate = float(values[STATE_INDEX["acetate"]])
    propionate = float(values[STATE_INDEX["propionate"]])
    hydrogen = float(values[STATE_INDEX["hydrogen"]])
    acidogens = float(values[STATE_INDEX["acidogens"]])
    propionate_biomass = float(values[STATE_INDEX["propionate_biomass"]])
    acetoclastic = float(values[STATE_INDEX["acetoclastic_biomass"]])
    hydrogenotrophic = float(values[STATE_INDEX["hydrogenotrophic_biomass"]])
    inorganic_nitrogen = float(values[STATE_INDEX["inorganic_nitrogen"]])

    ph = estimate_ph(values, influent_ph=influent_ph, temperature_c=temperature_c)
    temp_factor = _temperature_factor(temperature_c, params)
    ph_factor = _ph_inhibition(ph, params)
    ammonia_factor = _ammonia_inhibition(inorganic_nitrogen, params)
    hydrogen_factor = _hydrogen_inhibition(hydrogen, params)

    hydrolysis = params.k_hyd * hydrolysis_multiplier * particulate * temp_factor
    acidogenesis = (
        params.k_m_su
        * acidogens
        * (soluble / (params.k_s_su + soluble))
        * ph_factor
        * ammonia_factor
        * temp_factor
    )
    propionate_conversion = (
        params.k_m_pro
        * propionate_biomass
        * (propionate / (params.k_s_pro + propionate))
        * ph_factor
        * hydrogen_factor
        * temp_factor
    )
    acetate_methanogenesis = (
        params.k_m_ac
        * acetoclastic
        * (acetate / (params.k_s_ac + acetate))
        * ph_factor
        * ammonia_factor
        * temp_factor
    )
    hydrogen_methanogenesis = (
        params.k_m_h2
        * hydrogenotrophic
        * (hydrogen / (params.k_s_h2 + hydrogen))
        * ph_factor
        * ammonia_factor
        * temp_factor
    )

    total_biomass_decay = (
        params.decay_acidogens * acidogens
        + params.decay_propionate_biomass * propionate_biomass
        + params.decay_acetoclastic * acetoclastic
        + params.decay_hydrogenotrophic * hydrogenotrophic
    )

    reaction = np.zeros(len(STATE_NAMES), dtype=float)
    # Biomass decay is routed back to the particulate COD pool as lysed solids/composites,
    # matching the ADM1 assumption that cell death recycles COD inside the liquid phase.
    reaction[STATE_INDEX["particulate_cod"]] += total_biomass_decay - hydrolysis
    reaction[STATE_INDEX["soluble_cod"]] += hydrolysis - acidogenesis
    reaction[STATE_INDEX["acetate"]] += (
        ACIDOGENESIS_SPLITS["acetate"] * acidogenesis
        + PROPIONATE_SPLITS["acetate"] * propionate_conversion
        - acetate_methanogenesis
    )
    reaction[STATE_INDEX["propionate"]] += ACIDOGENESIS_SPLITS["propionate"] * acidogenesis - propionate_conversion
    reaction[STATE_INDEX["hydrogen"]] += (
        ACIDOGENESIS_SPLITS["hydrogen"] * acidogenesis
        + PROPIONATE_SPLITS["hydrogen"] * propionate_conversion
        - hydrogen_methanogenesis
        - params.gas_stripping_h2 * hydrogen
    )
    reaction[STATE_INDEX["acidogens"]] += params.acidogen_yield * acidogenesis - params.decay_acidogens * acidogens
    reaction[STATE_INDEX["propionate_biomass"]] += (
        params.propionate_yield * propionate_conversion - params.decay_propionate_biomass * propionate_biomass
    )
    reaction[STATE_INDEX["acetoclastic_biomass"]] += params.acetoclastic_yield * acetate_methanogenesis - params.decay_acetoclastic * acetoclastic
    reaction[STATE_INDEX["hydrogenotrophic_biomass"]] += params.hydrogenotrophic_yield * hydrogen_methanogenesis - params.decay_hydrogenotrophic * hydrogenotrophic
    # Inorganic nitrogen balance (simplified ADM1, Batstone et al., 2002):
    #   +hydrolysis_nitrogen_release per hydrolysis: release of organic N from
    #          particulate matter; the default 0.03 kgN/kgCOD is a reduced-model
    #          proxy for sludge protein hydrolysis.
    #   +biomass_decay_nitrogen_content per biomass decay: release of cell-bound
    #          ammonium upon lysis; the default 0.018 kgN/kgCOD is intentionally
    #          conservative and can be compared against ADM1-style values around
    #          0.06-0.08 kgN/kgCOD when benchmarking against PyADM1.
    reaction[STATE_INDEX["inorganic_nitrogen"]] += (
        params.hydrolysis_nitrogen_release * hydrolysis
        + params.biomass_decay_nitrogen_content * total_biomass_decay
    )
    # Alkalinity balance (empirical reduced-model proxy, Batstone et al., 2002):
    #   +0.050 per acetate methanogenesis: HCO3- produced as CO2 is stripped and
    #          consumed by acetogens, net alkalinity gain from VFA removal.
    #   +0.035 per hydrogen methanogenesis: minor HCO3- production from CO2 fixation.
    #   -0.045 per acidogenesis: VFA production lowers alkalinity via acid dissociation.
    #   +0.015 per propionate conversion: partial alkalinity recovery as propionate
    #          is oxidised to acetate and CO2 by syntrophic acetogens.
    reaction[STATE_INDEX["alkalinity"]] += 0.05 * acetate_methanogenesis + 0.035 * hydrogen_methanogenesis - 0.045 * acidogenesis + 0.015 * propionate_conversion

    # Gas production rates: fraction of substrate COD leaving as gas = (1 − biomass yield).
    # Stoichiometric basis (Batstone et al., 2002):
    #   Acetate methanogenesis: CH3COO⁻ + H2O → CH4 + HCO3⁻; yield fraction stays as biomass,
    #     (1 − Y_ac) ≈ 0.945 kgCOD_CH4 / kgCOD_acetate consumed.
    #   Hydrogen methanogenesis: 4H2 + CO2 → CH4 + 2H2O; (1 − Y_h2) ≈ 0.965 kgCOD_CH4 / kgCOD_H2.
    #   gas_yield_ch4 = 0.35 m³CH4 / kgCOD converts the COD flux to volumetric methane (STP).
    methane_rate = gas_capture_efficiency * params.gas_yield_ch4 * (
        (1.0 - params.acetoclastic_yield) * acetate_methanogenesis
        + (1.0 - params.hydrogenotrophic_yield) * hydrogen_methanogenesis
    )
    co2_rate = gas_capture_efficiency * params.gas_yield_co2 * (
        0.25 * acidogenesis + 0.12 * propionate_conversion + 0.35 * acetate_methanogenesis
    )
    h2_rate = gas_capture_efficiency * params.gas_yield_h2 * params.gas_stripping_h2 * hydrogen
    biogas_rate = methane_rate + co2_rate + h2_rate
    vfa_total = acetate + propionate

    diagnostics = {
        "ph": ph,
        "vfa_total": vfa_total,
        "methane_rate_m3_m3_day": methane_rate,
        "co2_rate_m3_m3_day": co2_rate,
        "h2_rate_m3_m3_day": h2_rate,
        "biogas_rate_m3_m3_day": biogas_rate,
        "hydrolysis_rate": hydrolysis,
        "acidogenesis_rate": acidogenesis,
        "propionate_conversion_rate": propionate_conversion,
        "acetate_methanogenesis_rate": acetate_methanogenesis,
        "hydrogen_methanogenesis_rate": hydrogen_methanogenesis,
    }
    return reaction, diagnostics
