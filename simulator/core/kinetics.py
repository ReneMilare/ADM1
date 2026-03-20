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

# ── Stoichiometric / thermodynamic constants for pH calculation ───────────────
# Molar COD masses: 64 gO2 per mol acetate (CH3COO⁻), 112 gO2 per mol propionate (C2H5COO⁻)
_COD_TO_MOL_ACETATE: float = 1000.0 / 64.0
_COD_TO_MOL_PROPIONATE: float = 1000.0 / 112.0
_N_TO_MOL: float = 1000.0 / 14.0  # kgN/m³ → mol/m³ (atomic N = 14 g/mol)

# Conversion from the model's dimensionless "alkalinity" state to total
# titratable alkalinity [mol/m³].  Calibrated so that the charge-balance
# pH matches BSM2-like operating conditions at 35 °C.  Physically represents
# roughly 17 mol HCO3⁻-equivalent per model alkalinity unit.
_ALK_TO_MOL: float = 17.0

# Assumed CO2 partial pressure in biogas headspace [atm].
# Typical range for anaerobic digesters: 0.25–0.40 atm (25–40 % CO2 in biogas).
_PCO2_ATM: float = 0.30


def _kh_co2(temperature_c: float) -> float:
    """Henry constant for CO2 dissolution [mol m⁻³ atm⁻¹].

    Van't Hoff extrapolation from KH(25°C)=34 mol/m³/atm.
    CO2 becomes less soluble with increasing temperature (ΔH_soln < 0),
    so KH decreases with T (≈ 26 mol/m³/atm at 35 °C, ≈ 16 at 55 °C).
    """
    T_K = temperature_c + 273.15
    return 34.0 * math.exp(2400.0 * (1.0 / T_K - 1.0 / 298.15))


def _pka_co2_first(temperature_c: float) -> float:
    """pKa1 for CO2 ⇌ H⁺ + HCO3⁻ equilibrium, temperature-corrected.

    Reference: Plummer & Busenberg (1982).  pKa1 decreases slightly with T
    (6.352 at 25 °C → 6.241 at 35 °C → 6.131 at 45 °C).
    """
    return 6.352 - 0.01106 * (temperature_c - 25.0)


def _pka_acetate(temperature_c: float) -> float:
    """pKa for acetic acid (CH3COOH ⇌ H⁺ + CH3COO⁻), temperature-corrected."""
    return 4.7613 + 0.0133 * (temperature_c - 25.0)


def _pka_propionate(temperature_c: float) -> float:
    """pKa for propionic acid (C2H5COOH ⇌ H⁺ + C2H5COO⁻), temperature-corrected."""
    return 4.8742 + 0.0154 * (temperature_c - 25.0)

# COD mass-balance splits (Batstone et al., 2002 ADM1 — simplified reduced-model pathways).
# Each dict maps liquid product → fraction of consumed substrate COD that appears in that
# product.  The remainder (1 − Σsplits) equals the biomass yield stored in KineticParameters,
# so splits + yield = 1.00 for every pathway (verified by test_cod_balance_* tests).
ACIDOGENESIS_SPLITS = {
    "acetate": 0.55,
    "propionate": 0.20,
    "hydrogen": 0.13,
}
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
    """pH from Henderson-Hasselbalch charge balance with bicarbonate/VFA equilibria.

    Implements the thermodynamic charge balance for an anaerobic digester:

        [HCO3⁻] + [Ac⁻] + [Pro⁻] + ... = TA_mol  (total titratable alkalinity)
        [HCO3⁻] = [CO2] × 10^(pH − pKa1_CO2)       (bicarbonate equilibrium)
        [Ac⁻]   = S_ac_mol × Ka_ac / ([H⁺] + Ka_ac) (acetate dissociation)
        [Pro⁻]  = S_pro_mol × Ka_pro / ([H⁺] + Ka_pro) (propionate dissociation)

    Solved iteratively by isolating [HCO3⁻] from the charge balance and
    computing pH from the bicarbonate/CO2 equilibrium.  Converges in ~8 steps.

    Assumptions
    -----------
    * Dissolved CO2 is in equilibrium with the biogas headspace at pCO2 ≈ 0.30 atm
      (temperature-corrected via Van't Hoff, 25–40 % CO2 typical for digesters).
    * All pKa values are temperature-corrected from 25 °C literature values.
    * The model's "alkalinity" state is a proxy for total titratable alkalinity
      scaled by _ALK_TO_MOL ≈ 17 mol m⁻³ per model unit (calibrated for BSM2).
    * CO3²⁻, OH⁻, H⁺, and NH3 contributions are negligible at pH 4–9
      (< 0.5 mol/m³ each at typical digester conditions).

    Parameters
    ----------
    state : 11-component state vector
    influent_ph : initial guess for iteration (not used as an anchor bias)
    temperature_c : reactor temperature [°C]
    """
    s_ac  = float(max(state[STATE_INDEX["acetate"]],   0.0))
    s_pro = float(max(state[STATE_INDEX["propionate"]], 0.0))
    s_alk = float(max(state[STATE_INDEX["alkalinity"]], EPSILON))

    # Convert to molar concentrations [mol/m³]
    s_ac_mol  = s_ac  * _COD_TO_MOL_ACETATE
    s_pro_mol = s_pro * _COD_TO_MOL_PROPIONATE
    ta_mol    = s_alk * _ALK_TO_MOL  # total titratable alkalinity [mol/m³]

    # Temperature-dependent equilibrium constants
    pka_co2 = _pka_co2_first(temperature_c)
    ka_ac   = 10.0 ** (-_pka_acetate(temperature_c))
    ka_pro  = 10.0 ** (-_pka_propionate(temperature_c))

    # Dissolved CO2 from Henry's law [mol/m³]
    s_co2 = _kh_co2(temperature_c) * _PCO2_ATM

    # Iterative solution: start from influent pH as initial guess.
    # Convergence is guaranteed by negative feedback:
    #   pH too high → more VFA dissociation → less HCO3⁻ → pH falls
    #   pH too low  → less VFA dissociation → more HCO3⁻ → pH rises
    ph = float(np.clip(influent_ph, 5.0, 8.5))
    for _ in range(15):
        h       = 10.0 ** (-ph)
        ac_ion  = s_ac_mol  * ka_ac  / (h + ka_ac)
        pro_ion = s_pro_mol * ka_pro / (h + ka_pro)
        hco3    = max(ta_mol - ac_ion - pro_ion, EPSILON)
        ph_new  = pka_co2 + math.log10(hco3 / max(s_co2, EPSILON))
        ph_new  = float(np.clip(ph_new, 4.0, 9.0))
        if abs(ph_new - ph) < 1e-5:
            ph = ph_new
            break
        ph = 0.7 * ph_new + 0.3 * ph  # damped update for numerical stability

    return float(np.clip(ph, 4.0, 9.0))


def _temperature_factor(temperature_c: float, params: KineticParameters) -> float:
    raw = params.temperature_coefficient ** (temperature_c - 35.0)
    return float(np.clip(raw, 0.25, 3.0))


def _temperature_factor_hydrolysis(temperature_c: float, params: KineticParameters) -> float:
    """Arrhenius temperature factor for hydrolysis only (θ=1.04 per ADM1)."""
    raw = params.hydrolysis_temperature_coefficient ** (temperature_c - 35.0)
    return float(np.clip(raw, 0.25, 3.0))


def _ph_inhibition(ph: float, params: KineticParameters) -> float:
    penalty = math.exp(-((ph - params.ph_optimum) / max(params.ph_tolerance, EPSILON)) ** 2)
    return float(np.clip(penalty, 0.05, 1.0))


def _ammonia_inhibition(inorganic_nitrogen: float, params: KineticParameters) -> float:
    overload = max(inorganic_nitrogen - params.nitrogen_inhibition_threshold, 0.0)
    inhibition = 1.0 / (1.0 + overload / max(params.ammonia_inhibition_k, EPSILON))
    return float(np.clip(inhibition, 0.1, 1.0))


def _pka_ammonia(temperature_c: float) -> float:
    return 0.09018 + 2729.92 / (temperature_c + 273.15)


def _free_ammonia_concentration(inorganic_nitrogen: float, ph: float, temperature_c: float) -> float:
    pka = _pka_ammonia(temperature_c)
    fraction = 1.0 / (1.0 + 10.0 ** (pka - ph))
    return float(max(inorganic_nitrogen, 0.0) * fraction)


def _fan_inhibition(s_nh3: float, ki_nh3: float) -> float:
    return float(ki_nh3 / (ki_nh3 + max(s_nh3, 0.0)))


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
    acidogenesis_multiplier: float = 1.0,
    propionate_multiplier: float = 1.0,
    acetoclastic_multiplier: float = 1.0,
    hydrogenotrophic_multiplier: float = 1.0,
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
    temp_factor_hyd = _temperature_factor_hydrolysis(temperature_c, params)
    ph_factor = _ph_inhibition(ph, params)
    hydrogen_factor = _hydrogen_inhibition(hydrogen, params)

    if params.ammonia_inhibition_mode == "fan":
        s_nh3 = _free_ammonia_concentration(inorganic_nitrogen, ph, temperature_c)
        inh_nh3_acidogens = _fan_inhibition(s_nh3, params.ki_nh3_acidogens)
        inh_nh3_propionate = _fan_inhibition(s_nh3, params.ki_nh3_propionate)
        inh_nh3_acetoclastic = _fan_inhibition(s_nh3, params.ki_nh3_acetoclastic)
        inh_nh3_hydrogenotrophic = _fan_inhibition(s_nh3, params.ki_nh3_hydrogenotrophic)
    else:
        s_nh3 = 0.0
        inh_simple = _ammonia_inhibition(inorganic_nitrogen, params)
        inh_nh3_acidogens = inh_simple
        inh_nh3_propionate = 1.0
        inh_nh3_acetoclastic = inh_simple
        inh_nh3_hydrogenotrophic = inh_simple

    hydrolysis = params.k_hyd * hydrolysis_multiplier * particulate * temp_factor_hyd
    acidogenesis = (
        params.k_m_su
        * acidogens
        * (soluble / (params.k_s_su + soluble))
        * ph_factor
        * inh_nh3_acidogens
        * temp_factor
        * acidogenesis_multiplier
    )
    propionate_conversion = (
        params.k_m_pro
        * propionate_biomass
        * (propionate / (params.k_s_pro + propionate))
        * ph_factor
        * hydrogen_factor
        * inh_nh3_propionate
        * temp_factor
        * propionate_multiplier
    )
    acetate_methanogenesis = (
        params.k_m_ac
        * acetoclastic
        * (acetate / (params.k_s_ac + acetate))
        * ph_factor
        * inh_nh3_acetoclastic
        * temp_factor
        * acetoclastic_multiplier
    )
    hydrogen_methanogenesis = (
        params.k_m_h2
        * hydrogenotrophic
        * (hydrogen / (params.k_s_h2 + hydrogen))
        * ph_factor
        * inh_nh3_hydrogenotrophic
        * temp_factor
        * hydrogenotrophic_multiplier
    )

    total_biomass_decay = (
        params.decay_acidogens * acidogens
        + params.decay_propionate_biomass * propionate_biomass
        + params.decay_acetoclastic * acetoclastic
        + params.decay_hydrogenotrophic * hydrogenotrophic
    )

    reaction = np.zeros(len(STATE_NAMES), dtype=float)
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
    reaction[STATE_INDEX["acetoclastic_biomass"]] += (
        params.acetoclastic_yield * acetate_methanogenesis - params.decay_acetoclastic * acetoclastic
    )
    reaction[STATE_INDEX["hydrogenotrophic_biomass"]] += (
        params.hydrogenotrophic_yield * hydrogen_methanogenesis - params.decay_hydrogenotrophic * hydrogenotrophic
    )
    reaction[STATE_INDEX["inorganic_nitrogen"]] += (
        params.hydrolysis_nitrogen_release * hydrolysis
        + params.biomass_decay_nitrogen_content * total_biomass_decay
    )
    reaction[STATE_INDEX["alkalinity"]] += (
        0.05 * acetate_methanogenesis
        + 0.035 * hydrogen_methanogenesis
        - 0.045 * acidogenesis
        + 0.015 * propionate_conversion
    )

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
        "free_ammonia_kgN_m3": s_nh3,
        "inh_nh3_acidogens": inh_nh3_acidogens,
        "inh_nh3_propionate": inh_nh3_propionate,
        "inh_nh3_acetoclastic": inh_nh3_acetoclastic,
        "inh_nh3_hydrogenotrophic": inh_nh3_hydrogenotrophic,
        "hydrogen_inhibition_factor": hydrogen_factor,
    }
    return reaction, diagnostics
