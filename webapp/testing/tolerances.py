"""Tolerâncias padrão para comparação de KPIs em testes de regressão.

As tolerâncias são definidas por campo, com suporte a:
- ``abs``: desvio absoluto máximo permitido (None = não verificado)
- ``rel_pct``: desvio relativo máximo em % (None = não verificado)

Campos categóricos e flags são comparados por igualdade exata.
"""
from __future__ import annotations

DEFAULT_KPI_TOLERANCES: dict[str, dict[str, float | None]] = {
    "methane_final_m3_day": {"abs": 0.01, "rel_pct": 2.0},
    "biogas_final_m3_day": {"abs": 0.01, "rel_pct": 2.0},
    "ph_final": {"abs": 0.05, "rel_pct": None},
    "vfa_final": {"abs": 0.001, "rel_pct": 5.0},
    "effluent_cod_final": {"abs": 0.01, "rel_pct": 5.0},
    "stability_index": {"abs": 0.005, "rel_pct": None},
}

# Campos que devem bater exatamente (sem tolerância numérica)
CATEGORICAL_EXACT_FIELDS: list[str] = [
    "backend_used",
    "backend_requested",
    "has_fallback",
]

# Quando True, cada substring de required_warnings_contain deve aparecer
# em pelo menos um warning e nenhuma substring de forbidden_warnings_contain
# pode aparecer em qualquer warning.
WARNING_EXACT_MATCH: bool = True
