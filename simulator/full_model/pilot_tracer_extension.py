from __future__ import annotations

import numpy as np

from simulator.full_model.assembly import FullModelAssembly
from simulator.full_model.catalog_types import ParameterDefinition, ProcessDefinition, StateDefinition
from simulator.full_model.extensions import FullModelExtensionContribution
from simulator.full_model.units import DAY_INV, KG_COD_M3

SOURCE = "Projeto ADM1 - Fase 4; extens?o piloto para validar arquitetura"


class _PilotTracerExtension:
    name = "pilot_tracer"
    description = "Extens?o piloto m?nima para validar estados, processos, par?metros e diagn?sticos."

    def contribute(self) -> FullModelExtensionContribution:
        return FullModelExtensionContribution(
            states=(
                StateDefinition(
                    name="X_tracer",
                    description="Tra?ador particulado piloto da arquitetura de extens?es.",
                    unit=KG_COD_M3,
                    phase="solid",
                    domain="extension_pilot",
                    role="dynamic",
                    cod_role="cod",
                    elemental_proxy="C_xI",
                    source=SOURCE,
                    notes="Usado apenas para validar a composi??o incremental do backend full.",
                ),
            ),
            processes=(
                ProcessDefinition(
                    name="rho_ext_tracer_decay",
                    vendor_symbol="Rho_ext_1",
                    family="biochemical",
                    description="Decaimento de um tra?ador piloto para validar extens?o bioqu?mica.",
                    rate_expression="k_decay_tracer * X_tracer",
                    affected_states=("X_tracer", "X_I"),
                    parameters=("k_decay_tracer",),
                    inhibitions=(),
                    source=SOURCE,
                ),
            ),
            parameters=(
                ParameterDefinition(
                    name="k_decay_tracer",
                    value=0.15,
                    unit=DAY_INV,
                    group="biochemical",
                    classification="provisional",
                    description="Constante de decaimento do tra?ador piloto.",
                    source=SOURCE,
                ),
            ),
            biochemical_stoichiometry_rows={
                "rho_ext_tracer_decay": {
                    "X_tracer": "-1",
                    "X_I": "1",
                }
            },
            rate_function=self._rates,
            diagnostics_hook=self._diagnostics,
            validate_hook=self._validate,
        )

    def _rates(self, state, params):
        return {
            "rho_ext_tracer_decay": float(params["k_decay_tracer"] * max(float(state["X_tracer"]), 0.0)),
        }

    def _diagnostics(self, full_state_matrix: np.ndarray, assembly: FullModelAssembly, parameter_values):
        tracer = np.clip(full_state_matrix[:, assembly.full_state_index["X_tracer"]].astype(float), a_min=0.0, a_max=None)
        initial = max(float(tracer[0]), 1e-12)
        return {
            "pilot_tracer_inventory": tracer.astype(float).tolist(),
            "pilot_tracer_fraction_remaining": (tracer / initial).astype(float).tolist(),
        }

    def _validate(self, assembly: FullModelAssembly) -> None:
        if "X_tracer" not in assembly.dynamic_state_index:
            raise ValueError("A extens?o piloto exige X_tracer como estado din?mico.")


PILOT_TRACER_EXTENSION = _PilotTracerExtension()
