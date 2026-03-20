from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReferenceCaseDefinition:
    name: str
    description: str
    source_title: str
    source_tables: tuple[int, ...]
    operating_conditions: dict[str, float]
    tracked_outputs: tuple[str, ...]
    implementation_anchor: str


BSM2_REFERENCE_CASES = (
    ReferenceCaseDefinition(
        name="bsm2_tables_5_6_steady_state",
        description="Caso canônico do benchmark BSM2 usado no projeto para validar o caso-base ADM1 em CSTR.",
        source_title="Aspects on ADM1 Implementation within the BSM2 Framework",
        source_tables=(5, 6),
        operating_conditions={
            "temperature_c": 35.0,
            "liquid_volume_m3": 3400.0,
            "gas_volume_m3": 300.0,
            "flow_rate_m3_day": 170.0,
            "simulation_days": 200.0,
        },
        tracked_outputs=(
            "pH",
            "Qgas_Nm3_day",
            "S_ac",
            "S_pro",
            "S_IN",
            "X_ac",
            "X_h2",
            "S_gas_ch4",
            "Pgas_bar",
        ),
        implementation_anchor="simulator/literature_validation.py",
    ),
)
