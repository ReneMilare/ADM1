"""E11 — Fenólicos (Phenolics Pathway Extension).

Adds phenol/phenolic compounds (S_phen) and a two-step degradation pathway
via benzoate intermediate (S_ben), following Fezzani 2008/2009:

  Step 1: S_phen → S_ben + H2  (phenol ring → benzoate by X_phen)
  Step 2: S_ben  → S_ac + H2   (benzoate ring cleavage → acetate by X_ben)

Phenolics are relevant for olive mill wastewater, lignocellulosic hydrolysates,
and similar substrates where aromatic compounds are present. Phenol inhibits both
acetogens and methanogens.

Stoichiometry (per kgCOD substrate):
  Step 1 — Phenolics → Benzoate:
      S_phen → (1-Y_phen)*f_ben_phen*S_ben + (1-Y_phen)*f_h2_phen*S_h2 + Y_phen*X_phen
      f_ben_phen = 0.70, f_h2_phen = 0.30
      C6H5OH: MW = 94 g/mol, COD ≈ 224 gO2/mol (7 O2 per mol phenol)
      C_phen = 6/224 = 0.02679 kmolC/kgCOD

  Step 2 — Benzoate → Acetate:
      S_ben → (1-Y_ben)*f_ac_ben*S_ac + (1-Y_ben)*f_h2_ben*S_h2 + Y_ben*X_ben
      f_ac_ben = 0.80, f_h2_ben = 0.20
      C6H5COO⁻: 7 C, COD = 240 gO2/mol (15/2 O2 per mol benzoate)
      C_ben = 7/240 = 0.02917 kmolC/kgCOD

  Inhibition (Fezzani 2009, §2.1.4):
      Phenol and total VFA inhibit acetoclastic methanogenesis (rho_11) using
      noncompetitive factors. Phenol uptake also has noncompetitive inhibition.

Reference:
    Fezzani & Ben Cheikh (2008). "Two-phase anaerobic co-digestion of olive mill
    wastes in semi-continuous digesters." Bioresource Technology 99(15):6996-7003.
    doi:10.1016/j.biortech.2008.01.004
    Fezzani & Ben Cheikh (2009). "Extension of the anaerobic digestion model No. 1
    (ADM1) to include phenol compounds biodegradation for anaerobic co-digestion of
    olive mill wastes at mesophilic temperature." Journal of Hazardous Materials
    172(3):1430-1438. doi:10.1016/j.jhazmat.2009.08.017

Domain applicability:
    Parameters (K_S_phen = 30.5, K_I_phen = 50, k_m_phen = 15) were calibrated for
    olive mill wastewater with S_phen ≈ 5–50 kgCOD/m³. K_S_phen is 60–1500× larger
    than typical ADM1 half-saturation constants (0.02–0.5 kgCOD/m³). For any substrate
    other than olive mill effluent (municipal waste, sewage sludge, lignocellulosic
    hydrolysates, etc.) all phenolics parameters require full recalibration.
"""
from __future__ import annotations

from typing import Mapping

import numpy as np

from simulator.full_model.assembly import FullModelAssembly
from simulator.full_model.catalog_types import ParameterDefinition, ProcessDefinition, StateDefinition
from simulator.full_model.extensions import FullModelExtensionContribution
from simulator.full_model.units import DAY_INV, DIMENSIONLESS, KG_COD_M3, KMOL_C_PER_KG_COD

_SRC = "Fezzani & Ben Cheikh (2008) doi:10.1016/j.biortech.2008.01.004; (2009) doi:10.1016/j.jhazmat.2009.08.017"


class _PhenolicsExtension:
    name = "phenolics"
    description = "E11: compostos fenólicos como substrato e inibidor para digestão anaeróbia (Fezzani 2008/2009)."

    def contribute(self) -> FullModelExtensionContribution:
        states = (
            StateDefinition(
                name="S_phen",
                description="Compostos fenólicos dissolvidos (S_phen).",
                unit=KG_COD_M3,
                phase="liquid",
                domain="soluble",
                role="dynamic",
                cod_role="cod",
                elemental_proxy=None,
                source=_SRC,
                notes="C_phen = 6/224 = 0.02679 kmolC/kgCOD. Inibidor para metanogênese.",
            ),
            StateDefinition(
                name="S_ben",
                description="Benzoato dissolvido (intermediário da degradação de fenólicos).",
                unit=KG_COD_M3,
                phase="liquid",
                domain="soluble",
                role="dynamic",
                cod_role="cod",
                elemental_proxy=None,
                source=_SRC,
                notes="C_ben = 7/240 = 0.02917 kmolC/kgCOD. C6H5COO⁻: 7 C, COD = 240 gO2/mol.",
            ),
            StateDefinition(
                name="X_phen",
                description="Biomassa de acetogens degradadores de fenólicos.",
                unit=KG_COD_M3,
                phase="solid",
                domain="active_biomass",
                role="dynamic",
                cod_role="cod",
                elemental_proxy="C_bac",
                source=_SRC,
            ),
            StateDefinition(
                name="X_ben",
                description="Biomassa de acetogens degradadores de benzoato.",
                unit=KG_COD_M3,
                phase="solid",
                domain="active_biomass",
                role="dynamic",
                cod_role="cod",
                elemental_proxy="C_bac",
                source=_SRC,
            ),
        )

        processes = (
            ProcessDefinition(
                name="rho_E11_uptake_phenolics",
                vendor_symbol="Rho_E11_1",
                family="biochemical",
                description="Degradação de fenólicos → benzoato por X_phen.",
                rate_expression="computed_by_extension",
                affected_states=("S_phen", "S_ben", "S_h2", "S_IC", "S_IN", "X_phen"),
                parameters=("k_m_phen", "K_S_phen", "Y_phen", "K_I_phen"),
                inhibitions=("I_pH_aa", "I_IN_lim", "I_h2_pro"),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E11_uptake_benzoate",
                vendor_symbol="Rho_E11_3",
                family="biochemical",
                description="Degradação de benzoato → acetato + H2 por X_ben.",
                rate_expression="computed_by_extension",
                affected_states=("S_ben", "S_ac", "S_h2", "S_IC", "S_IN", "X_ben"),
                parameters=("k_m_ben", "K_S_ben", "Y_ben"),
                inhibitions=("I_pH_aa", "I_IN_lim", "I_h2_fa"),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E11_decay_X_phen",
                vendor_symbol="Rho_E11_2",
                family="biochemical",
                description="Decaimento de X_phen → X_xc.",
                rate_expression="computed_by_extension",
                affected_states=("X_xc", "X_phen", "S_IC", "S_IN"),
                parameters=("k_dec_X_phen",),
                inhibitions=(),
                source=_SRC,
            ),
            ProcessDefinition(
                name="rho_E11_decay_X_ben",
                vendor_symbol="Rho_E11_4",
                family="biochemical",
                description="Decaimento de X_ben → X_xc.",
                rate_expression="computed_by_extension",
                affected_states=("X_xc", "X_ben", "S_IC", "S_IN"),
                parameters=("k_dec_X_ben",),
                inhibitions=(),
                source=_SRC,
            ),
        )

        parameters = (
            ParameterDefinition(
                name="k_m_phen",
                value=15.0,
                unit=DAY_INV,
                group="biochemical",
                classification="calibrated",
                description="Taxa máxima de consumo de fenólicos por X_phen.",
                source=_SRC,
                notes="Fezzani 2009 Table 6: k_m_phen = 15 d⁻¹, calibrado em co-digestão de "
                      "efluentes de azeitona (olive mill wastewater).",
            ),
            ParameterDefinition(
                name="K_S_phen",
                value=30.5,
                unit=KG_COD_M3,
                group="biochemical",
                classification="calibrated",
                description="Meia-saturação para fenólicos (X_phen).",
                source=_SRC,
                notes="Fezzani 2009 Table 6: K_S_phen = 30.5 kgCOD/m³. Alto valor reflete "
                      "alta concentração de fenólicos no efluente de azeitona (substrato de referência).",
            ),
            ParameterDefinition(
                name="Y_phen",
                value=0.010,
                unit=DIMENSIONLESS,
                group="stoichiometric",
                classification="calibrated",
                description="Rendimento de biomassa no consumo de fenólicos.",
                source=_SRC,
                notes="Fezzani 2009 Table 6: Y_phen = 0.010 kgCOD/kgCOD. Muito baixo — aromatic "
                      "ring cleavage via syntrophic acetogenesis yields little energy for growth.",
            ),
            ParameterDefinition(
                name="k_dec_X_phen",
                value=0.02,
                unit=DAY_INV,
                group="biochemical",
                classification="calibrated",
                description="Taxa de decaimento de X_phen.",
                source=_SRC,
                notes="Batstone 2002 (ADM1 standard): k_dec = 0.02 d⁻¹ para acetogens.",
            ),
            ParameterDefinition(
                name="K_I_phen",
                value=50.0,
                unit=KG_COD_M3,
                group="biochemical",
                classification="calibrated",
                description="Constante de inibição de fenólicos sobre metanogênese e acetogens.",
                source=_SRC,
                notes="Fezzani 2009, Table 6: phenol uptake inhibition constant; applied as noncompetitive inhibition.",
            ),
            ParameterDefinition(
                name="C_phen",
                value=0.02679,
                unit=KMOL_C_PER_KG_COD,
                group="stoichiometric",
                classification="canonical",
                description="Conteúdo de carbono dos fenólicos (6 molC / 224 gCOD = 0.02679).",
                source=_SRC,
                notes="C6H5OH: 6 mol C per mol, COD = 224 gO2/mol (7 O2 per mol phenol).",
            ),
            ParameterDefinition(
                name="C_ben",
                value=0.02917,
                unit=KMOL_C_PER_KG_COD,
                group="stoichiometric",
                classification="canonical",
                description="Conteúdo de carbono do benzoato (7 molC / 240 gCOD = 0.02917).",
                source=_SRC,
                notes="C6H5COO⁻: 7 mol C per mol, COD = 240 gO2/mol (15/2 O2 per mol benzoate).",
            ),
            ParameterDefinition(
                name="f_ben_phen",
                value=0.70,
                unit=DIMENSIONLESS,
                group="stoichiometric",
                classification="calibrated",
                description="Fração COD catabolisado de fenólicos → benzoato.",
                source=_SRC,
                notes="Fezzani 2008/2009: major product of phenol degradation is benzoate.",
            ),
            ParameterDefinition(
                name="f_h2_phen",
                value=0.30,
                unit=DIMENSIONLESS,
                group="stoichiometric",
                classification="calibrated",
                description="Fração COD catabolisado de fenólicos → H2.",
                source=_SRC,
                notes="Fezzani 2008/2009: f_ben_phen + f_h2_phen = 1.0 for the first degradation step.",
            ),
            ParameterDefinition(
                name="k_m_ben",
                value=8.0,
                unit=DAY_INV,
                group="biochemical",
                classification="calibrated",
                description="Taxa máxima de consumo de benzoato por X_ben.",
                source=_SRC,
                notes="Fezzani 2009, Table 6: estimated benzoate uptake rate.",
            ),
            ParameterDefinition(
                name="K_S_ben",
                value=15.5,
                unit=KG_COD_M3,
                group="biochemical",
                classification="calibrated",
                description="Meia-saturação para benzoato (X_ben).",
                source=_SRC,
                notes="Fezzani 2009, Table 6: Monod retained because no benzoate inhibition constant is reported, although the text mentions Haldane kinetics.",
            ),
            ParameterDefinition(
                name="Y_ben",
                value=0.0135,
                unit=DIMENSIONLESS,
                group="stoichiometric",
                classification="calibrated",
                description="Rendimento de biomassa no consumo de benzoato.",
                source=_SRC,
                notes="Fezzani 2009, Table 6: estimated benzoate yield.",
            ),
            ParameterDefinition(
                name="k_dec_X_ben",
                value=0.02,
                unit=DAY_INV,
                group="biochemical",
                classification="calibrated",
                description="Taxa de decaimento de X_ben.",
                source=_SRC,
                notes="Fezzani 2009, Table 6: benzoate biomass decline constant.",
            ),
            ParameterDefinition(
                name="f_ac_ben",
                value=0.80,
                unit=DIMENSIONLESS,
                group="stoichiometric",
                classification="calibrated",
                description="Fração COD catabolisado de benzoato → acetato.",
                source=_SRC,
                notes="Fezzani 2009: benzoate is converted primarily to acetate via ring cleavage.",
            ),
            ParameterDefinition(
                name="f_h2_ben",
                value=0.20,
                unit=DIMENSIONLESS,
                group="stoichiometric",
                classification="calibrated",
                description="Fração COD catabolisado de benzoato → H2.",
                source=_SRC,
            ),
        )

        # Step 1: S_phen → S_ben + H2
        # S_IC = C_phen - (1-Y_phen)*(f_ben_phen*C_ben + f_h2_phen*0.0) - Y_phen*C_bac
        # Step 2: S_ben → S_ac + H2
        # S_IC = C_ben - (1-Y_ben)*f_ac_ben*C_ac - Y_ben*C_bac
        biochemical_stoichiometry_rows = {
            "rho_E11_uptake_phenolics": {
                "S_phen": "-1",
                "S_ben": "(1.0 - Y_phen) * f_ben_phen",
                "S_h2": "(1.0 - Y_phen) * f_h2_phen",
                "S_IC": "C_phen - (1.0 - Y_phen) * (f_ben_phen * C_ben + f_h2_phen * 0.0) - Y_phen * C_bac",
                "S_IN": "-Y_phen * N_bac",
                "X_phen": "Y_phen",
            },
            "rho_E11_uptake_benzoate": {
                "S_ben": "-1",
                "S_ac": "(1.0 - Y_ben) * f_ac_ben",
                "S_h2": "(1.0 - Y_ben) * f_h2_ben",
                "S_IC": "C_ben - (1.0 - Y_ben) * f_ac_ben * C_ac - Y_ben * C_bac",
                "S_IN": "-Y_ben * N_bac",
                "X_ben": "Y_ben",
            },
            "rho_E11_decay_X_phen": {
                "X_xc": "1",
                "X_phen": "-1",
                "S_IC": "-s_13",
                "S_IN": "N_bac - N_xc",
            },
            "rho_E11_decay_X_ben": {
                "X_xc": "1",
                "X_ben": "-1",
                "S_IC": "-s_13",
                "S_IN": "N_bac - N_xc",
            },
        }

        return FullModelExtensionContribution(
            states=states,
            processes=processes,
            parameters=parameters,
            biochemical_stoichiometry_rows=biochemical_stoichiometry_rows,
            rate_function=self._rates,
            diagnostics_hook=self._diagnostics,
            inhibition_hook=self._inhibition,
        )

    def _rates(self, state: Mapping[str, float], params: Mapping[str, float]) -> dict[str, float]:
        s_phen = max(float(state.get("S_phen", 0.0)), 0.0)
        s_ben = max(float(state.get("S_ben", 0.0)), 0.0)
        x_phen = max(float(state.get("X_phen", 0.0)), 0.0)
        x_ben = max(float(state.get("X_ben", 0.0)), 0.0)
        s_h_ion = max(float(state.get("S_H_ion", 1e-7)), 1e-14)
        s_in = max(float(state.get("S_IN", 1e-4)), 1e-12)
        s_h2 = max(float(state.get("S_h2", 0.0)), 1e-12)

        i_ph_aa = (params["K_pH_aa"] ** params["nn_aa"]) / (s_h_ion ** params["nn_aa"] + params["K_pH_aa"] ** params["nn_aa"])
        i_in_lim = 1.0 / (1.0 + params["K_S_IN"] / s_in)
        i_h2_pro = 1.0 / (1.0 + s_h2 / params["K_I_h2_pro"])
        i_h2_fa = 1.0 / (1.0 + s_h2 / params["K_I_h2_fa"])
        # Fezzani 2009, Table 6: noncompetitive phenol uptake inhibition.
        k_i_phen = float(params.get("K_I_phen", 50.0))
        i_phen = 1.0 / (1.0 + s_phen / k_i_phen)

        rho_phen = float(params["k_m_phen"]) * s_phen / (float(params["K_S_phen"]) + s_phen) * x_phen * i_ph_aa * i_in_lim * i_h2_pro * i_phen
        rho_ben = float(params["k_m_ben"]) * s_ben / (float(params["K_S_ben"]) + s_ben) * x_ben * i_ph_aa * i_in_lim * i_h2_fa
        rho_dec_phen = float(params["k_dec_X_phen"]) * x_phen
        rho_dec_ben = float(params["k_dec_X_ben"]) * x_ben

        return {
            "rho_E11_uptake_phenolics": rho_phen,
            "rho_E11_uptake_benzoate": rho_ben,
            "rho_E11_decay_X_phen": rho_dec_phen,
            "rho_E11_decay_X_ben": rho_dec_ben,
        }

    def _inhibition(self, state: Mapping[str, float], params: Mapping[str, float]) -> dict[str, float]:
        # Fezzani 2009, §2.1.4: the converted text does not decode the equations;
        # use the ADM1 noncompetitive form for phenol and total VFA inhibition.
        s_phen = max(float(state.get("S_phen", 0.0)), 0.0)
        tvfa = sum(max(float(state.get(name, 0.0)), 0.0) for name in ("S_va", "S_bu", "S_pro", "S_ac"))
        i_phen = 1.0 / (1.0 + s_phen / float(params.get("K_I_phen", 50.0)))
        i_tvfa = 1.0 / (1.0 + tvfa / 47.5)
        return {"rho_11_uptake_acetate": i_phen * i_tvfa}

    def _diagnostics(
        self, matrix: np.ndarray, assembly: FullModelAssembly, params: Mapping[str, float]
    ) -> dict[str, list[float]]:
        s_phen = np.clip(matrix[:, assembly.full_state_index["S_phen"]], 0.0, None)
        s_ben = np.clip(matrix[:, assembly.full_state_index["S_ben"]], 0.0, None)
        x_phen = np.clip(matrix[:, assembly.full_state_index["X_phen"]], 0.0, None)
        x_ben = np.clip(matrix[:, assembly.full_state_index["X_ben"]], 0.0, None)
        return {
            "S_phen": s_phen.astype(float).tolist(),
            "S_ben": s_ben.astype(float).tolist(),
            "X_phen": x_phen.astype(float).tolist(),
            "X_ben": x_ben.astype(float).tolist(),
        }


PHENOLICS_EXTENSION = _PhenolicsExtension()
