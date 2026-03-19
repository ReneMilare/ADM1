from __future__ import annotations

import streamlit as st

from simulator.core.models import SimulationResult
from webapp.services.simulation_service import result_series_frame, simulation_input_rows, simulation_summary_rows


def render_summary_table(result: SimulationResult) -> None:
    st.dataframe(simulation_summary_rows(result), use_container_width=True, hide_index=True)


def render_input_table(result: SimulationResult) -> None:
    st.dataframe(simulation_input_rows(result), use_container_width=True, hide_index=True)


def render_series_preview(result: SimulationResult, rows: int = 12) -> None:
    st.dataframe(result_series_frame(result).head(rows), use_container_width=True, hide_index=True)


def render_frame(frame) -> None:
    st.dataframe(frame, use_container_width=True, hide_index=True)
