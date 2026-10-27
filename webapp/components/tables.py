from __future__ import annotations

import streamlit as st

from simulator.core.models import SimulationResult
from webapp.services.simulation_service import result_series_frame, simulation_input_rows, simulation_summary_rows


def render_summary_table(result: SimulationResult) -> None:
    st.dataframe(simulation_summary_rows(result), width="stretch", hide_index=True)


def render_input_table(result: SimulationResult) -> None:
    st.dataframe(simulation_input_rows(result), width="stretch", hide_index=True)


def render_series_preview(result: SimulationResult, rows: int = 12) -> None:
    df = result_series_frame(result).head(rows)
    float_cols = [c for c in df.columns if df[c].dtype == float]
    styled = df.style.format({c: "{:.4g}" for c in float_cols})
    st.dataframe(styled, width="stretch", hide_index=True)


def render_frame(frame) -> None:
    st.dataframe(frame, width="stretch", hide_index=True)
