from __future__ import annotations

from _bootstrap import ensure_project_root

ensure_project_root()

import streamlit as st

from webapp.components.status_cards import (
    render_issue_messages,
    render_sidebar_panel,
    render_summary_cards,
    render_usage_guide,
    render_workflow_links,
)
from webapp.components.tables import render_frame
from webapp.services.health import collect_health_snapshot
from webapp.services.preferences_service import (
    get_preferences,
    is_query_favorite,
    list_favorite_queries,
    list_recent_queries,
    record_recent_query,
    toggle_favorite_query,
)
from webapp.services.rag_service import (
    format_search_error,
    get_content_type_options,
    get_example_queries,
    get_source_catalog,
    get_source_options,
    load_page_context,
    search_results_csv_bytes,
    search_results_json_bytes,
    search_technical_docs,
)
from webapp.state.session_state import ensure_session_state
from webapp.utils.page_config import configure_page, render_page_header

configure_page("Consulta Tecnica")
ensure_session_state()
snapshot = collect_health_snapshot()
st.session_state["recent_page"] = "consulta_tecnica"
render_sidebar_panel(snapshot, current_page="Consulta Tecnica")
render_page_header(
    eyebrow="Fase W6 + W7",
    title="Consulta Tecnica",
    description="Busca tecnica ligada ao RAG local, com citacao por fonte e pagina, expansao estruturada da pagina recuperada, favoritos, historico recente e ponte direta para os parametros do simulador.",
)

if snapshot["issues"]:
    render_issue_messages(snapshot)
render_summary_cards(snapshot)
render_workflow_links(
    title="Fluxos relacionados",
    items=[
        {"path": "pages/01_Simular_Reator.py", "label": "Simular Reator", "caption": "Aplicar parametros sugeridos pela literatura consultada."},
        {"path": "pages/04_Validacao.py", "label": "Validacao", "caption": "Checar benchmark interno e literatura antes de fechar conclusoes."},
        {"path": "pages/06_Configuracoes.py", "label": "Configuracoes", "caption": "Gerenciar favoritos, historico e preferencias do workbench."},
    ],
)
render_usage_guide(
    title="Como usar esta tela",
    summary="A consulta tecnica foi refinada para uso recorrente: voce pode partir de exemplos guiados, guardar perguntas frequentes como favoritas e expandir a pagina recuperada sem sair da interface.",
    steps=[
        "Escolha uma pergunta guiada ou escreva uma consulta em linguagem natural.",
        "Ajuste filtros de fonte e tipo de trecho apenas se quiser restringir o escopo.",
        "Use a tabela de citacoes rapidas para confirmar fonte, pagina e secao.",
        "Expanda a pagina estruturada quando precisar de mais contexto antes de ajustar o simulador.",
    ],
    tips=[
        "Consultas frequentes podem ser favoritados e reaproveitadas na propria UI.",
        "As sugestoes de parametro sao heuristicas; trate-as como ponte operacional, nao como verdade automatica.",
    ],
)

preferences = get_preferences()
if "technical_top_k" not in st.session_state:
    st.session_state["technical_top_k"] = int(preferences.get("default_top_k", 5))

source_catalog = get_source_catalog()
source_options = get_source_options()
content_type_options = get_content_type_options()
example_queries = get_example_queries()
favorite_queries = list_favorite_queries()
recent_queries = list_recent_queries()
search_disabled = not bool(snapshot["summary"].get("rag_available", snapshot["summary"]["rag_ready"]))
auto_expand_top_result = bool(preferences.get("auto_expand_top_result", True))

search_tab, sources_tab = st.tabs(["Buscar no acervo", "Fontes indexadas"])

with search_tab:
    quick_col1, quick_col2 = st.columns(2)
    with quick_col1:
        st.subheader("Perguntas guiadas")
        for index, example in enumerate(example_queries):
            button_col, text_col = st.columns((0.38, 1.0))
            with button_col:
                if st.button(example["label"], key=f"example_query_{index}", use_container_width=True):
                    st.session_state["technical_query_draft"] = example["query"]
                    st.rerun()
            with text_col:
                st.caption(example["query"])
    with quick_col2:
        st.subheader("Favoritos e historico")
        if favorite_queries:
            st.markdown("**Favoritas**")
            for index, item in enumerate(favorite_queries[:4]):
                if st.button(str(item.get("query")), key=f"favorite_query_{index}", use_container_width=True):
                    st.session_state["technical_query_draft"] = str(item.get("query"))
                    st.rerun()
        if recent_queries:
            st.markdown("**Recentes**")
            for index, item in enumerate(recent_queries[:4]):
                label = f"{item.get('query')} ({item.get('result_count')} resultados)"
                if st.button(label, key=f"recent_query_{index}", use_container_width=True):
                    st.session_state["technical_query_draft"] = str(item.get("query"))
                    st.rerun()
        if not favorite_queries and not recent_queries:
            st.caption("O historico local sera preenchido conforme voce usar a busca tecnica.")

    if search_disabled:
        st.warning("O RAG local ainda nao esta pronto para consulta. Verifique indice local, Ollama e modelo de embedding antes de usar a busca tecnica na interface.")

    with st.form("technical_search_form"):
        query = st.text_area(
            "Pergunta ou conceito tecnico",
            value=st.session_state.get("technical_query_draft", ""),
            height=100,
            placeholder="Ex.: Como HRT e temperatura afetam a estabilidade do processo?",
        )
        filter_col1, filter_col2, filter_col3 = st.columns((0.8, 1.3, 1.0))
        with filter_col1:
            st.slider("Top K", min_value=3, max_value=8, value=int(st.session_state.get("technical_top_k", 5)), step=1, key="technical_top_k")
        with filter_col2:
            selected_sources = st.multiselect(
                "Filtrar fontes",
                options=list(source_options),
                format_func=lambda value: source_options[value],
            )
        with filter_col3:
            selected_content_types = st.multiselect(
                "Tipos de trecho",
                options=list(content_type_options),
                format_func=lambda value: content_type_options[value],
            )
        submitted = st.form_submit_button("Buscar no acervo", use_container_width=True, disabled=search_disabled)

    if submitted:
        st.session_state["technical_query_draft"] = query
        try:
            payload = search_technical_docs(
                query,
                top_k=int(st.session_state.get("technical_top_k", 5)),
                selected_sources=selected_sources,
                content_types=selected_content_types,
            )
            st.session_state["latest_technical_results"] = payload
            st.session_state["latest_technical_error"] = None
            record_recent_query(
                payload["query"],
                result_count=int(payload.get("result_count", 0)),
                source_count=len(payload.get("source_hits", [])),
            )
        except Exception as exc:
            st.session_state["latest_technical_results"] = None
            st.session_state["latest_technical_error"] = format_search_error(exc)

    if st.session_state.get("latest_technical_error"):
        st.error(st.session_state["latest_technical_error"])

    payload = st.session_state.get("latest_technical_results")
    if payload:
        results = payload.get("results", [])
        current_query = str(payload.get("query") or "")
        metrics = st.columns(4)
        metrics[0].metric("Resultados", str(payload.get("result_count", 0)))
        metrics[1].metric("Fontes atingidas", str(len(payload.get("source_hits", []))))
        top_score = float(results[0].get("score") or 0.0) if results else 0.0
        metrics[2].metric("Score topo", f"{top_score:.3f}")
        page_hits = {item.get("page_reference") for item in results if item.get("page_reference")}
        metrics[3].metric("Paginas citadas", str(len(page_hits)))

        action_col1, action_col2, action_col3 = st.columns(3)
        with action_col1:
            favorite_label = "Remover dos favoritos" if is_query_favorite(current_query) else "Favoritar consulta atual"
            if st.button(favorite_label, use_container_width=True):
                toggle_favorite_query(current_query)
                st.rerun()
        with action_col2:
            st.download_button(
                label="Baixar resultados CSV",
                data=search_results_csv_bytes(payload),
                file_name="technical_search_results.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with action_col3:
            st.download_button(
                label="Baixar resultados JSON",
                data=search_results_json_bytes(payload),
                file_name="technical_search_results.json",
                mime="application/json",
                use_container_width=True,
            )

        if payload.get("filters_applied") and payload.get("result_count", 0) < payload.get("raw_result_count", 0):
            st.info("Os filtros reduziram o conjunto retornado pelo ranking bruto do RAG. Se o resultado parecer estreito demais, remova filtros e rode novamente.")

        summary_col1, summary_col2 = st.columns((1.2, 0.8))
        with summary_col1:
            st.markdown("**Citacoes rapidas**")
            render_frame(payload.get("citations", []))
        with summary_col2:
            st.markdown("**Fontes mais acionadas**")
            render_frame(payload.get("source_hits", []))

        suggestions = payload.get("parameter_suggestions", [])
        if suggestions:
            st.subheader("Parametros de simulacao relacionados")
            render_frame(suggestions)
            st.caption("As sugestoes abaixo sao inferidas a partir dos termos da consulta e dos trechos recuperados. Use-as como ponte para a tela `Simular Reator` ou para ajustes avancados no core.")

        st.subheader("Resultados recuperados")
        if not results:
            st.warning("A busca executou, mas nao retornou trechos com os filtros atuais.")
        for item in results:
            title = f"#{item['rank']} {item['source']} | {item['page_reference']} | score {float(item['score']):.3f}"
            expanded = auto_expand_top_result and int(item.get("rank") or 0) == 1
            with st.expander(title, expanded=expanded):
                st.markdown(f"**Secao:** {item.get('section') or 'Sem secao'}")
                st.caption(
                    " | ".join(
                        [
                            f"tipo: {item.get('content_type_label')}",
                            f"score: {float(item.get('score') or 0.0):.3f}",
                            f"semantico: {float(item.get('semantic_score') or 0.0):.3f}",
                            f"lexical: {float(item.get('lexical_score') or 0.0):.3f}",
                        ]
                    )
                )
                st.write(str(item.get("excerpt") or ""))

                page_options = list(item.get("available_pages") or [int(item.get("page_start") or item.get("page") or 1)])
                if len(page_options) > 1:
                    selected_page = st.selectbox(
                        "Pagina para expandir",
                        options=page_options,
                        key=f"page_select_{item['chunk_id']}",
                    )
                else:
                    selected_page = page_options[0]
                    st.caption(f"A expansao estruturada abaixo usa a pagina {selected_page}.")

                if st.toggle("Mostrar pagina estruturada", key=f"page_toggle_{item['chunk_id']}"):
                    try:
                        page_bundle = load_page_context(str(item.get("source") or ""), int(selected_page))
                        page_metrics = st.columns(4)
                        page_metrics[0].metric("Pagina", str(page_bundle.get("page")))
                        page_metrics[1].metric("Blocos", str(page_bundle.get("block_count")))
                        page_metrics[2].metric("Secoes", str(len(page_bundle.get("sections_on_page", []))))
                        page_metrics[3].metric("Tipos", str(len(page_bundle.get("content_type_counts", {}))))

                        sections_on_page = page_bundle.get("sections_on_page", [])
                        if sections_on_page:
                            st.markdown("**Secoes identificadas na pagina:**")
                            st.markdown("- " + "\n- ".join(str(section) for section in sections_on_page[:8]))

                        type_counts = page_bundle.get("content_type_counts", {})
                        if type_counts:
                            st.markdown("**Distribuicao de blocos na pagina:**")
                            st.markdown("- " + "\n- ".join(f"{label}: {hits}" for label, hits in type_counts.items()))

                        st.markdown("**Preview expandido da pagina**")
                        st.code(str(page_bundle.get("preview_text") or ""), language=None)
                        if page_bundle.get("preview_truncated"):
                            st.caption("Preview truncado para manter a leitura fluida. Use os blocos abaixo para inspecao mais granular.")

                        with st.expander("Blocos extraidos da pagina", expanded=False):
                            render_frame(page_bundle.get("block_preview", []))
                            if page_bundle.get("block_preview_truncated"):
                                st.caption("A tabela mostra apenas os primeiros blocos extraidos da pagina.")
                    except Exception as exc:
                        st.warning(format_search_error(exc))
    else:
        st.info("Escolha uma pergunta tecnica ou use uma das consultas guiadas acima para iniciar a busca no acervo.")

with sources_tab:
    st.subheader("Catalogo de fontes do RAG")
    source_metrics = st.columns(3)
    source_metrics[0].metric("Fontes indexadas", str(len(source_catalog)))
    source_metrics[1].metric("Paginas no manifesto", str(sum(int(item.get("page_count") or 0) for item in source_catalog)))
    source_metrics[2].metric("Blocos extraidos", str(sum(int(item.get("block_count") or 0) for item in source_catalog)))

    if source_catalog:
        render_frame(source_catalog)
    else:
        st.warning("Nenhuma fonte foi encontrada no manifesto do RAG. Rode `python rag\\extract_pdfs.py` e `python rag\\index_documents.py` antes de usar esta tela.")