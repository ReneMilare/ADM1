"""Cenários de referência para testes de regressão do webapp ADM1.

Cada cenário é um dict com campos bem definidos que cobrem combinações de
backend, tipo de reator, preset e extensões. Os valores de feed e operating
são derivados dos presets reais definidos em simulator/design_pipeline.py.

Campos do cenário
-----------------
scenario_id             : identificador único
description             : descrição legível
reactor_type            : "cstr" | "uasb" | "plug_flow" | "two_phase" | "tpad" | "batch"
backend_requested       : backend solicitado ("pyadm1" | "full" | "reduced" | "auto")
backend_expected        : backend efetivamente usado após resolução de fallback
fallback_expected       : True se espera fallback, False caso contrário
fallback_reason_contains: substring esperada na razão de fallback (None se não aplicável)
feed_params             : campos de FeedDefinition como dict
operating_params        : campos de OperatingConditions como dict
extensions              : lista de extensões full_model (e.g. ["srb"])
extension_overrides     : dict com initial_state_overrides e/ou influent_state_overrides
kpi_tolerances          : tolerâncias por KPI (sobrepõe DEFAULT_KPI_TOLERANCES quando presente)
required_warnings_contain   : substrings que devem aparecer nos warnings da simulação
forbidden_warnings_contain  : substrings que NÃO devem aparecer nos warnings
"""
from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Parâmetros extraídos dos presets reais (simulator/design_pipeline.py)
# ---------------------------------------------------------------------------

_LODO_FEED: dict[str, Any] = {
    "name": "Lodo de Esgoto",
    "particulate_cod": 14.0,
    "soluble_cod": 5.5,
    "acetate": 0.6,
    "propionate": 0.25,
    "hydrogen": 0.001,
    "inorganic_nitrogen": 1.3,
    "alkalinity": 4.8,
    "ph": 7.1,
}

_LODO_OPERATING: dict[str, Any] = {
    "volume_m3": 3000.0,
    "temperature_c": 35.0,
    "hrt_days": 20.0,
}

_ALIMENTAR_FEED: dict[str, Any] = {
    "name": "Resíduos Alimentares",
    "particulate_cod": 11.5,
    "soluble_cod": 7.2,
    "acetate": 1.15,
    "propionate": 0.55,
    "hydrogen": 0.0015,
    "inorganic_nitrogen": 1.45,
    "alkalinity": 4.4,
    "ph": 6.95,
}

_ALIMENTAR_OPERATING: dict[str, Any] = {
    "volume_m3": 2800.0,
    "temperature_c": 35.0,
    "hrt_days": 18.0,
}

# Parâmetros de entrada manual (valores default do simulador)
_MANUAL_FEED: dict[str, Any] = {
    "name": "Manual feed",
    "particulate_cod": 8.0,
    "soluble_cod": 4.0,
    "acetate": 0.5,
    "propionate": 0.2,
    "hydrogen": 0.001,
    "inorganic_nitrogen": 1.0,
    "alkalinity": 4.0,
    "ph": 7.0,
}

_MANUAL_OPERATING: dict[str, Any] = {
    "volume_m3": 3000.0,
    "temperature_c": 35.0,
    "hrt_days": 20.0,
}

# Overrides de estado para extensão SRB
_SRB_EXTENSION_OVERRIDES: dict[str, Any] = {
    "initial_state_overrides": {
        "X_SRB_ac": 0.10,
        "X_SRB_h2": 0.05,
        "X_SRB_pro": 0.05,
        "X_SRB_bu": 0.05,
    },
    "influent_state_overrides": {
        "S_SO4": 0.01,
    },
}

# ---------------------------------------------------------------------------
# Definição dos cenários
# ---------------------------------------------------------------------------

REGRESSION_SCENARIOS: list[dict[str, Any]] = [
    {
        "scenario_id": "caso_base_lite",
        "description": "CSTR + backend reduced + preset Lodo de Esgoto. Caso de referência mais leve.",
        "reactor_type": "cstr",
        "backend_requested": "reduced",
        "backend_expected": "reduced",
        "fallback_expected": False,
        "fallback_reason_contains": None,
        "feed_params": _LODO_FEED,
        "operating_params": _LODO_OPERATING,
        "extensions": [],
        "extension_overrides": {},
        "kpi_tolerances": {},
        "required_warnings_contain": [],
        "forbidden_warnings_contain": [],
    },
    {
        "scenario_id": "caso_base_full",
        "description": "CSTR + backend full + preset Lodo de Esgoto. Validação do backend nativo para o caso canônico.",
        "reactor_type": "cstr",
        "backend_requested": "full",
        "backend_expected": "full",
        "fallback_expected": False,
        "fallback_reason_contains": None,
        "feed_params": _LODO_FEED,
        "operating_params": _LODO_OPERATING,
        "extensions": [],
        "extension_overrides": {},
        "kpi_tolerances": {},
        "required_warnings_contain": [],
        "forbidden_warnings_contain": [],
    },
    {
        "scenario_id": "caso_full_extensoes",
        "description": (
            "CSTR + backend full + extensão SRB. "
            "Verifica que a extensão de redução de sulfato não regride os KPIs principais."
        ),
        "reactor_type": "cstr",
        "backend_requested": "full",
        "backend_expected": "full",
        "fallback_expected": False,
        "fallback_reason_contains": None,
        "feed_params": _LODO_FEED,
        "operating_params": _LODO_OPERATING,
        "extensions": ["srb"],
        "extension_overrides": _SRB_EXTENSION_OVERRIDES,
        "kpi_tolerances": {
            # extensão SRB compete com metanogênese; tolerância mais folgada
            "methane_final_m3_day": {"abs": 0.05, "rel_pct": 5.0},
            "biogas_final_m3_day": {"abs": 0.05, "rel_pct": 5.0},
        },
        "required_warnings_contain": [],
        "forbidden_warnings_contain": [],
    },
    {
        "scenario_id": "caso_substrato_manual",
        "description": (
            "CSTR + backend pyadm1 + inputs manuais. "
            "Verifica que a entrada manual com valores default não regride o modelo PyADM1."
        ),
        "reactor_type": "cstr",
        "backend_requested": "pyadm1",
        "backend_expected": "pyadm1",
        "fallback_expected": False,
        "fallback_reason_contains": None,
        "feed_params": _MANUAL_FEED,
        "operating_params": _MANUAL_OPERATING,
        "extensions": [],
        "extension_overrides": {},
        "kpi_tolerances": {},
        "required_warnings_contain": [],
        "forbidden_warnings_contain": [],
    },
    {
        "scenario_id": "caso_preset_usuario",
        "description": (
            "CSTR + backend auto + preset Resíduos Alimentares. "
            "Verifica que o modo auto seleciona pyadm1 para CSTR."
        ),
        "reactor_type": "cstr",
        "backend_requested": "auto",
        "backend_expected": "pyadm1",
        "fallback_expected": False,
        "fallback_reason_contains": None,
        "feed_params": _ALIMENTAR_FEED,
        "operating_params": _ALIMENTAR_OPERATING,
        "extensions": [],
        "extension_overrides": {},
        "kpi_tolerances": {},
        "required_warnings_contain": [],
        "forbidden_warnings_contain": [],
    },
    {
        "scenario_id": "caso_uasb_full",
        "description": (
            "UASB + backend full. "
            "Verifica suporte nativo do backend full para reatores não-CSTR "
            "e serve de baseline para comparar com o fallback pyadm1->reduced."
        ),
        "reactor_type": "uasb",
        "backend_requested": "full",
        "backend_expected": "full",
        "fallback_expected": False,
        "fallback_reason_contains": None,
        "feed_params": _LODO_FEED,
        "operating_params": _LODO_OPERATING,
        "extensions": [],
        "extension_overrides": {},
        "kpi_tolerances": {},
        "required_warnings_contain": [],
        "forbidden_warnings_contain": [],
    },
]

# Índice rápido por scenario_id
SCENARIOS_BY_ID: dict[str, dict[str, Any]] = {s["scenario_id"]: s for s in REGRESSION_SCENARIOS}
