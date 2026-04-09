from __future__ import annotations

from typing import Any

import plotly.graph_objects as go
import streamlit as st

from simulator.core.models import SimulationResult

_COLOR_MAP = {
    "methane": "#006d67",
    "biogas": "#c66c2b",
    "ph": "#2f4f6f",
    "vfa": "#7b3f00",
}
_COMPARISON_PALETTE = ["#006d67", "#c66c2b", "#2f4f6f", "#7b3f00", "#8f3b76", "#496b2d"]
SERIES_PLOT_OPTIONS = {
    "methane_m3_day": {"label": "Metano", "title": "Producao de metano", "y_axis_title": "Nm3/d"},
    "biogas_m3_day": {"label": "Biogas", "title": "Producao de biogas", "y_axis_title": "Nm3/d"},
    "ph": {"label": "pH", "title": "Perfil de pH", "y_axis_title": "pH"},
    "vfa_total": {"label": "VFA total", "title": "Perfil de VFA total", "y_axis_title": "kgCOD/m3"},
    "free_ammonia_kgN_m3": {"label": "Amonia livre (FAN)", "title": "Amonia livre (FAN)", "y_axis_title": "kgN/m3"},
}
_INHIBITION_SERIES = [
    "inh_nh3_acidogens",
    "inh_nh3_propionate",
    "inh_nh3_acetoclastic",
    "inh_nh3_hydrogenotrophic",
]
_COMPONENT_ORDER = ["methane", "stability", "effluent", "vfa", "ph"]
_COMPONENT_COLORS = {
    "methane": "#006d67",
    "stability": "#2f4f6f",
    "effluent": "#c66c2b",
    "vfa": "#7b3f00",
    "ph": "#8f3b76",
}
_PLOTLY_CONFIG = {
    "displayModeBar": True,
    "displaylogo": False,
    "responsive": True,
    "toImageButtonOptions": {
        "format": "png",
        "filename": "adm1_chart",
        "scale": 2,
    },
    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
}


def _render_figure(figure: go.Figure) -> None:
    st.plotly_chart(figure, use_container_width=True, config=_PLOTLY_CONFIG)


def _base_layout(title: str, *, height: int = 360) -> dict[str, Any]:
    return {
        "title": title,
        "template": "plotly_white",
        "margin": {"l": 20, "r": 20, "t": 60, "b": 20},
        "height": height,
        "legend": {"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "left", "x": 0.0},
        "paper_bgcolor": "rgba(255,255,255,0.85)",
        "plot_bgcolor": "rgba(255,255,255,0.85)",
    }


def _line_chart(result: SimulationResult, *, series_names: list[str], title: str, y_axis_title: str, color_key: str) -> go.Figure:
    figure = go.Figure()
    time_values = result.time_days
    for series_name in series_names:
        figure.add_trace(
            go.Scatter(
                x=time_values,
                y=result.series[series_name],
                mode="lines",
                name=series_name,
                line={"width": 3},
            )
        )
    figure.update_layout(**_base_layout(title, height=340))
    figure.update_xaxes(title_text="Time [days]")
    figure.update_yaxes(title_text=y_axis_title, gridcolor="rgba(20, 34, 48, 0.08)")
    # Auto scientific notation when values are very small or very large
    _all_vals = [v for name in series_names for v in (result.series.get(name) or []) if v is not None]
    if _all_vals:
        _max_abs = max(abs(v) for v in _all_vals)
        if _max_abs > 0 and (_max_abs < 1e-3 or _max_abs > 1e4):
            figure.update_yaxes(exponentformat="power")
            figure.update_traces(hovertemplate="%{x:.2f}d<br>%{y:.3e}<extra></extra>")
    base_color = _COLOR_MAP[color_key]
    for trace in figure.data:
        trace.line.color = base_color
    if len(figure.data) > 1:
        alt_colors = [base_color, "#3a9d96", "#8b5e3c", "#4d7ea8"]
        for index, trace in enumerate(figure.data):
            trace.line.color = alt_colors[index % len(alt_colors)]
    return figure


def _comparison_figure(
    results: list[SimulationResult],
    *,
    series_key: str,
    labels: dict[str, str] | None = None,
) -> go.Figure:
    metadata = SERIES_PLOT_OPTIONS[series_key]
    figure = go.Figure()
    for index, result in enumerate(results):
        if series_key not in result.series:
            continue
        trace_name = labels.get(result.simulation_id, result.simulation_id) if labels else result.simulation_id
        figure.add_trace(
            go.Scatter(
                x=result.time_days,
                y=result.series[series_key],
                mode="lines",
                name=trace_name,
                line={"width": 3, "color": _COMPARISON_PALETTE[index % len(_COMPARISON_PALETTE)]},
            )
        )
    figure.update_layout(**_base_layout(metadata["title"]))
    figure.update_xaxes(title_text="Time [days]")
    figure.update_yaxes(title_text=metadata["y_axis_title"], gridcolor="rgba(20, 34, 48, 0.08)")
    return figure


def _design_score_figure(report: dict[str, Any]) -> go.Figure:
    figure = go.Figure()
    reactors = [candidate["reactor_type"] for candidate in report["candidates"]]
    scores = [float(candidate["score"]) for candidate in report["candidates"]]
    colors = ["#006d67" if reactor == report["recommended_reactor"] else "#8fb7b2" for reactor in reactors]
    figure.add_trace(
        go.Bar(
            x=reactors,
            y=scores,
            marker_color=colors,
            text=[f"{score:.3f}" for score in scores],
            textposition="outside",
            name="Score total",
        )
    )
    figure.update_layout(**_base_layout("Ranking dos candidatos", height=380))
    figure.update_yaxes(title_text="Score total", range=[0.0, max(scores + [1.0]) * 1.18], gridcolor="rgba(20, 34, 48, 0.08)")
    return figure


def _design_component_figure(report: dict[str, Any]) -> go.Figure:
    figure = go.Figure()
    reactors = [candidate["reactor_type"] for candidate in report["candidates"]]
    for component in _COMPONENT_ORDER:
        values = [float(candidate["component_scores"][component]) for candidate in report["candidates"]]
        figure.add_trace(
            go.Bar(
                x=reactors,
                y=values,
                name=component,
                marker_color=_COMPONENT_COLORS[component],
            )
        )
    figure.update_layout(**_base_layout("Leitura dos componentes do score", height=380))
    figure.update_layout(barmode="group")
    figure.update_yaxes(title_text="Score normalizado", range=[0.0, 1.08], gridcolor="rgba(20, 34, 48, 0.08)")
    return figure


def _phase3_runtime_figure(report: dict[str, Any]) -> go.Figure:
    runtime = report["benchmark"]["runtime_seconds"]
    backends = list(runtime)
    values = [float(runtime[backend]["mean"]) for backend in backends]
    figure = go.Figure(
        data=[
            go.Bar(
                x=backends,
                y=values,
                marker_color=["#c66c2b", "#006d67"],
                text=[f"{value:.4f}s" for value in values],
                textposition="outside",
            )
        ]
    )
    figure.update_layout(**_base_layout("Runtime medio por backend", height=340))
    figure.update_yaxes(title_text="seconds", gridcolor="rgba(20, 34, 48, 0.08)")
    return figure


def _phase3_accuracy_figure(report: dict[str, Any]) -> go.Figure:
    summary_metrics = report["benchmark"]["summary_metrics"]
    selected_metrics = ["methane_final_m3_day", "biogas_final_m3_day", "vfa_final"]
    labels = []
    values = []
    for metric in selected_metrics:
        if metric in summary_metrics:
            labels.append(metric)
            values.append(float(summary_metrics[metric]["mean_rel_delta_pct_vs_pyadm1"]))
    figure = go.Figure(
        data=[
            go.Bar(
                x=labels,
                y=values,
                marker_color="#c66c2b",
                text=[f"{value:.2f}%" for value in values],
                textposition="outside",
            )
        ]
    )
    figure.update_layout(**_base_layout("Delta medio do reduced vs pyadm1", height=340))
    figure.update_yaxes(title_text="% rel delta", gridcolor="rgba(20, 34, 48, 0.08)")
    return figure


def _literature_error_figure(report: dict[str, Any]) -> go.Figure:
    pyadm1_metrics = report["pyadm1"]["comparison"]
    reduced_metrics = report["reduced"]["comparison"]
    labels = list(pyadm1_metrics.keys())[:7]
    pyadm1_values = [float(pyadm1_metrics[label]["rel_delta_pct"]) for label in labels]
    reduced_values = [float(reduced_metrics[label]["rel_delta_pct"]) if label in reduced_metrics else None for label in labels]
    figure = go.Figure()
    figure.add_trace(go.Bar(x=labels, y=pyadm1_values, name="pyadm1", marker_color="#006d67"))
    figure.add_trace(go.Bar(x=labels, y=reduced_values, name="reduced", marker_color="#c66c2b"))
    figure.update_layout(**_base_layout("Erro relativo vs benchmark BSM2", height=360))
    figure.update_layout(barmode="group")
    figure.update_yaxes(title_text="% rel delta", gridcolor="rgba(20, 34, 48, 0.08)")
    return figure


def render_core_profile_charts(result: SimulationResult) -> None:
    col1, col2 = st.columns(2)
    with col1:
        _render_figure(
            _line_chart(
                result,
                series_names=["methane_m3_day"],
                title="Methane production",
                y_axis_title="Nm3/d",
                color_key="methane",
            )
        )
    with col2:
        _render_figure(
            _line_chart(
                result,
                series_names=["biogas_m3_day"],
                title="Biogas production",
                y_axis_title="Nm3/d",
                color_key="biogas",
            )
        )

    col3, col4 = st.columns(2)
    with col3:
        _render_figure(
            _line_chart(
                result,
                series_names=["ph"],
                title="pH profile",
                y_axis_title="pH",
                color_key="ph",
            )
        )
    with col4:
        _render_figure(
            _line_chart(
                result,
                series_names=["vfa_total", "acetate", "propionate"],
                title="VFA profile",
                y_axis_title="kgCOD/m3",
                color_key="vfa",
            )
        )


def render_comparison_overlay_charts(
    results: list[SimulationResult],
    *,
    series_keys: list[str],
    labels: dict[str, str] | None = None,
) -> None:
    valid_series = [series_key for series_key in series_keys if series_key in SERIES_PLOT_OPTIONS]
    if not valid_series:
        st.info("Selecione pelo menos uma serie para comparar.")
        return

    for index in range(0, len(valid_series), 2):
        chunk = valid_series[index:index + 2]
        columns = st.columns(len(chunk))
        for column, series_key in zip(columns, chunk, strict=False):
            with column:
                _render_figure(_comparison_figure(results, series_key=series_key, labels=labels))


def render_design_score_charts(report: dict[str, Any]) -> None:
    col1, col2 = st.columns(2)
    with col1:
        _render_figure(_design_score_figure(report))
    with col2:
        _render_figure(_design_component_figure(report))


def render_phase3_validation_charts(report: dict[str, Any]) -> None:
    col1, col2 = st.columns(2)
    with col1:
        _render_figure(_phase3_runtime_figure(report))
    with col2:
        _render_figure(_phase3_accuracy_figure(report))


def render_literature_validation_charts(report: dict[str, Any]) -> None:
    _render_figure(_literature_error_figure(report))


def render_ammonia_charts(result: SimulationResult) -> None:
    """Render FAN timeseries and NH3 inhibition factor profiles (only when ammonia mode is 'fan')."""
    if "free_ammonia_kgN_m3" not in result.series:
        return
    col1, col2 = st.columns(2)
    with col1:
        _render_figure(
            _line_chart(
                result,
                series_names=["free_ammonia_kgN_m3"],
                title="Amonia livre (FAN)",
                y_axis_title="kgN/m3",
                color_key="vfa",
            )
        )
    with col2:
        available_inhibition = [s for s in _INHIBITION_SERIES if s in result.series]
        if available_inhibition:
            _render_figure(
                _line_chart(
                    result,
                    series_names=available_inhibition,
                    title="Fatores de inibicao por NH3",
                    y_axis_title="[-]",
                    color_key="methane",
                )
            )


def render_phase_profile_charts(result: SimulationResult) -> None:
    """Render per-phase pH and methane profiles for two_phase and tpad reactors."""
    reactor_type = result.reactor.reactor_type
    if reactor_type == "two_phase":
        phase_prefixes = ["phase1", "phase2"]
    elif reactor_type == "tpad":
        phase_prefixes = ["thermo", "meso"]
    else:
        return

    ph_series = [f"{p}_ph" for p in phase_prefixes if f"{p}_ph" in result.series]
    methane_series = [f"{p}_methane_rate_m3_day" for p in phase_prefixes if f"{p}_methane_rate_m3_day" in result.series]

    if not ph_series and not methane_series:
        return

    col1, col2 = st.columns(2)
    with col1:
        if ph_series:
            _render_figure(
                _line_chart(
                    result,
                    series_names=ph_series,
                    title="pH por fase",
                    y_axis_title="pH",
                    color_key="ph",
                )
            )
    with col2:
        if methane_series:
            _render_figure(
                _line_chart(
                    result,
                    series_names=methane_series,
                    title="Producao de metano por fase",
                    y_axis_title="Nm3/d",
                    color_key="methane",
                )
            )
