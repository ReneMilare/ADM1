from __future__ import annotations

import streamlit as st


def ensure_session_state() -> None:
    defaults = {
        "backend_preference": "full",
        "ui_mode": "basic",
        "latest_error": None,
        "latest_simulation": None,
        "latest_design": None,
        "latest_design_error": None,
        "latest_phase3_validation": None,
        "latest_phase3_validation_error": None,
        "latest_literature_validation": None,
        "latest_literature_validation_error": None,
        "latest_technical_results": None,
        "latest_technical_error": None,
        "technical_query_draft": "",
        "recent_page": "home",
        "ammonia_inhibition_mode": "simple",
        "codigestion_preset": None,
        "variant_config": None,
        # ── Plano 02: chaves de simulação canônicas ────────────────────────────
        # Estas chaves são também inicializadas em 01_Simular_Reator.py com
        # valores derivados de preferências do usuário. Aqui ficam apenas os
        # defaults de segurança para acesso cross-página.
        "sim_reactor_type": "cstr",
        "sim_substrate_mode": "preset",
        # sim_preset_id é inicializado pela página 01_Simular_Reator.py com o
        # primeiro preset disponível — não definir aqui para não bloquear esse default.
        "sim_custom_substrate_name": None,
        "sim_backend_choice": "full",
        "sim_full_extensions": [],
        "hydraulic_mode": "hrt",
        "volume_active": 3000.0,
        "temperature_active": 35.0,
        "hrt_active": 20.0,
        "flow_rate_active": 150.0,
        "duration_days": 45.0,
        "evaluation_points": 181,
        "solver_choice": "BDF",
        "persist_case": True,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value