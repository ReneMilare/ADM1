from __future__ import annotations

from typing import Any

import streamlit as st

from simulator.core.models import SimulationResult
from webapp.utils.page_config import status_chip

_PAGE_LINKS = [
    {"path": "app.py", "label": "Visao Geral"},
    {"path": "pages/01_Simular_Reator.py", "label": "Simular Reator"},
    {"path": "pages/02_Comparar_Cenarios.py", "label": "Comparar Cenarios"},
    {"path": "pages/03_Design_de_Reator.py", "label": "Design de Reator"},
    {"path": "pages/04_Validacao.py", "label": "Validacao"},
    {"path": "pages/06_Configuracoes.py", "label": "Configuracoes"},
]


def _safe_page_link(path: str, label: str) -> None:
    if hasattr(st, "page_link"):
        try:
            st.page_link(path, label=label, use_container_width=True)
            return
        except Exception:
            pass
    st.markdown(f"- {label}")


def render_sidebar_panel(snapshot: dict[str, Any], *, current_page: str) -> None:
    with st.sidebar:
        st.markdown("## ADM1 Workbench")
        st.caption("Interface web local para engenharia de processo.")
        st.markdown(f"Pagina atual: `{current_page}`")
        st.markdown("### Politica de backend")
        st.markdown("- `auto`: CSTR continua em `pyadm1`")
        st.markdown("- `full`: disponivel explicitamente para `cstr`")
        st.markdown("- `reduced`: fallback para reatores sem suporte nativo")
        st.markdown("### Navegacao direta")
        for item in _PAGE_LINKS:
            _safe_page_link(str(item["path"]), str(item["label"]))
        st.markdown("### Estado rapido")
        status_html = " ".join(
            [
                status_chip("Servicos prontos", "ok" if snapshot["summary"]["services_ok"] == snapshot["summary"]["services_total"] else "warning"),
                status_chip("Sem bloqueios", "ok" if snapshot["summary"]["critical_issues"] == 0 else "error"),
            ]
        )
        st.markdown(status_html, unsafe_allow_html=True)


def render_issue_messages(snapshot: dict[str, Any]) -> None:
    for issue in snapshot["issues"]:
        if issue["severity"] == "error":
            st.error(issue["message"])
        elif issue["severity"] == "warning":
            st.warning(issue["message"])
        else:
            st.info(issue["message"])


def render_summary_cards(snapshot: dict[str, Any]) -> None:
    required_ok = snapshot["summary"]["required_dependencies_ok"]
    required_total = snapshot["summary"]["required_dependencies_total"]
    services_ok = snapshot["summary"]["services_ok"]
    services_total = snapshot["summary"]["services_total"]
    artifacts = snapshot["artifacts"]
    columns = st.columns(4)
    columns[0].metric("Politica padrao", "auto -> pyadm1", "full disponivel para CSTR")
    columns[1].metric("Dependencias centrais", f"{required_ok}/{required_total}")
    columns[2].metric("Servicos importados", f"{services_ok}/{services_total}")
    columns[3].metric("Cenarios salvos", str(artifacts["saved_scenario_count"]))


def render_dependency_table(snapshot: dict[str, Any]) -> None:
    rows = []
    for item in snapshot["dependencies"]:
        rows.append(
            {
                "nome": item["name"],
                "obrigatoria": "sim" if item["required"] else "nao",
                "status": item["status"],
                "detalhe": item["detail"],
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)


def render_service_table(snapshot: dict[str, Any]) -> None:
    rows = []
    for item in snapshot["services"]:
        rows.append(
            {
                "servico": item["name"],
                "status": item["status"],
                "detalhe": item["detail"],
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)


def render_artifact_table(snapshot: dict[str, Any]) -> None:
    artifacts = snapshot["artifacts"]
    rows = [
        {"artefato": "Cenarios salvos", "valor": artifacts["saved_scenario_count"]},
        {"artefato": "Benchmark runs", "valor": artifacts["benchmark_run_count"]},
        {"artefato": "Validation runs", "valor": artifacts["validation_run_count"]},
        {"artefato": "Literature validation runs", "valor": artifacts["literature_validation_count"]},
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)


def render_placeholder_block(*, description: str, next_step: str, bullets: list[str]) -> None:
    st.info(description)
    st.markdown(f"**Proxima entrega:** {next_step}")
    for bullet in bullets:
        st.markdown(f"- {bullet}")


def render_simulation_kpis(result: SimulationResult) -> None:
    summary = result.summary
    metadata = result.metadata
    columns = st.columns(5)
    columns[0].metric("Metano final", f"{summary.methane_final_m3_day:.2f} Nm3/d")
    columns[1].metric("Biogas final", f"{summary.biogas_final_m3_day:.2f} Nm3/d")
    columns[2].metric("Fracao CH4", f"{summary.ch4_fraction_final:.3f}")
    columns[3].metric("pH final", f"{summary.ph_final:.3f}")
    columns[4].metric("VFA final", f"{summary.vfa_final:.3f}")

    requested = str(metadata.get("backend_requested", result.simulation.backend))
    used = str(metadata.get("backend_used", result.simulation.backend))
    if requested != used:
        reason = str(metadata.get("backend_fallback_reason", ""))
        st.warning(f"Fallback de backend detectado: solicitado `{requested}` e executado `{used}`. {reason}")
    else:
        st.success(f"Backend executado: `{used}`")

    if used == "full":
        active_extensions = metadata.get("full_model_active_extensions", [])
        extensions_text = ", ".join(str(item) for item in active_extensions) if active_extensions else "nenhuma"
        st.info(
            " | ".join(
                [
                    f"ADM1 full nativo: runtime `{metadata.get('full_model_runtime', 'native')}`",
                    f"pH convergiu: {'sim' if bool(metadata.get('full_model_ph_converged', False)) else 'nao'}",
                    f"Iteracoes max pH: {metadata.get('full_model_ph_iterations_max', '-')}",
                    f"Extensoes ativas: {extensions_text}",
                ]
            )
        )


def render_usage_guide(*, title: str, summary: str, steps: list[str], tips: list[str] | None = None) -> None:
    with st.expander(title, expanded=False):
        st.markdown(summary)
        st.markdown("**Passos sugeridos**")
        for index, step in enumerate(steps, start=1):
            st.markdown(f"{index}. {step}")
        if tips:
            st.markdown("**Notas operacionais**")
            for item in tips:
                st.markdown(f"- {item}")


def render_workflow_links(*, title: str, items: list[dict[str, str]]) -> None:
    st.markdown(f"**{title}**")
    columns = st.columns(min(3, max(1, len(items))))
    for index, item in enumerate(items):
        with columns[index % len(columns)]:
            _safe_page_link(str(item["path"]), str(item["label"]))
            caption = str(item.get("caption") or "")
            if caption:
                st.caption(caption)
