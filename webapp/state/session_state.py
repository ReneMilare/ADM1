from __future__ import annotations

import streamlit as st


def ensure_session_state() -> None:
    defaults = {
        "backend_preference": "pyadm1",
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
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value