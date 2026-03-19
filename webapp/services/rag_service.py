from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from functools import lru_cache
from io import StringIO
from typing import Any

import pandas as pd

from rag.repository import ADM1RAGRepository

_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")
CONTENT_TYPE_OPTIONS = {
    "text": "Texto corrido",
    "heading": "Titulo",
    "table": "Tabela",
    "equation": "Equacao",
}
EXAMPLE_QUERIES = [
    {
        "label": "Estados do ADM1",
        "query": "How many dynamic state concentration variables are in ADM1?",
    },
    {
        "label": "pH e alcalinidade",
        "query": "Como o ADM1 trata pH, alcalinidade e estabilidade do processo?",
    },
    {
        "label": "Temperatura",
        "query": "Como a temperatura afeta a digestao anaerobia e o desempenho do reator?",
    },
    {
        "label": "HRT e vazao",
        "query": "Como HRT e vazao influenciam o dimensionamento e a operacao do reator?",
    },
]
PARAMETER_BRIDGES = [
    {
        "priority": 100,
        "group": "Operacao",
        "parameter_path": "OperatingConditions.temperature_c",
        "ui_location": "Simular Reator > Temperatura [C]",
        "when_to_review": "quando a referencia discutir regime mesofilico/termofilico, aquecimento ou efeito cinetico da temperatura.",
        "keywords": ["temperatura", "temperature", "mesophilic", "thermophilic", "heat", "heating"],
    },
    {
        "priority": 95,
        "group": "Operacao",
        "parameter_path": "OperatingConditions.hrt_days",
        "ui_location": "Simular Reator > HRT [dias]",
        "when_to_review": "quando a literatura falar de HRT, tempo de residencia, vazao ou carga hidraulica.",
        "keywords": ["hrt", "retention time", "tempo de retencao", "residence time", "vazao", "flow"],
    },
    {
        "priority": 92,
        "group": "Feed",
        "parameter_path": "FeedDefinition.ph",
        "ui_location": "Simular Reator > modo manual > Influent pH",
        "when_to_review": "quando a pergunta envolver pH de alimentacao, faixa operacional ou risco de acidificacao.",
        "keywords": ["ph", "acidez", "acidification", "acidificacao"],
    },
    {
        "priority": 90,
        "group": "Feed",
        "parameter_path": "FeedDefinition.alkalinity",
        "ui_location": "Simular Reator > modo manual > Alkalinity [kmol/m3 eq.]",
        "when_to_review": "quando a referencia discutir buffer, alcalinidade ou estabilidade frente a VFA.",
        "keywords": ["alkalinity", "alcalinidade", "buffer", "buffering"],
    },
    {
        "priority": 88,
        "group": "Feed",
        "parameter_path": "FeedDefinition.acetate / FeedDefinition.propionate",
        "ui_location": "Simular Reator > modo manual > Acetate / Propionate",
        "when_to_review": "quando a pergunta tratar de VFA, acetato, propionato ou perfis intermediarios de acidogenese/acetogenese.",
        "keywords": ["vfa", "volatile fatty acids", "acetate", "acetato", "propionate", "propionato"],
    },
    {
        "priority": 84,
        "group": "Feed",
        "parameter_path": "FeedDefinition.particulate_cod / FeedDefinition.soluble_cod",
        "ui_location": "Simular Reator > modo manual > Particulate COD / Soluble COD",
        "when_to_review": "quando a literatura discutir composicao do substrato, biodegradabilidade ou particulado vs solubilizado.",
        "keywords": ["cod", "substrate", "substrato", "particulate", "soluble", "biodegradability"],
    },
    {
        "priority": 82,
        "group": "Feed",
        "parameter_path": "FeedDefinition.inorganic_nitrogen",
        "ui_location": "Simular Reator > modo manual > Inorganic nitrogen [kgN/m3]",
        "when_to_review": "quando a referencia falar de nitrogenio, amonia, amonio ou risco de inibicao amoniacal.",
        "keywords": ["nitrogen", "nitrogenio", "ammonia", "amonia", "ammonium", "nh4"],
    },
    {
        "priority": 80,
        "group": "Cinettica",
        "parameter_path": "KineticParameters.k_hyd / ReactorConfig.hydrolysis_multiplier",
        "ui_location": "Core do simulador; usar quando entrar em calibracao ou estudo avancado",
        "when_to_review": "quando a pergunta for sobre hidrolise, velocidade de degradacao ou limitacao hidrolitica.",
        "keywords": ["hydrolysis", "hidrolise", "hydrolytic", "k_hyd"],
    },
    {
        "priority": 76,
        "group": "Reator",
        "parameter_path": "ReactorConfig.reactor_type / ReactorConfig.segments",
        "ui_location": "Simular Reator > Tipo de reator",
        "when_to_review": "quando a literatura diferenciar CSTR, UASB, plug-flow, mistura ou escoamento pistonado.",
        "keywords": ["reactor", "reator", "cstr", "uasb", "plug flow", "plug-flow", "mixing", "mix"],
    },
    {
        "priority": 72,
        "group": "Cinettica",
        "parameter_path": "KineticParameters.ammonia_inhibition_k / free_ammonia_soft_limit",
        "ui_location": "Core do simulador; relevante para estudos avancados de inibicao",
        "when_to_review": "quando a pergunta tratar de inibicao por amonia, limite de amonia livre ou sensibilidade biologica.",
        "keywords": ["ammonia inhibition", "inibicao por amonia", "free ammonia", "amonia livre"],
    },
    {
        "priority": 68,
        "group": "Reator",
        "parameter_path": "ReactorConfig.gas_capture_efficiency",
        "ui_location": "Core do simulador; usar em estudos de captura de gas",
        "when_to_review": "quando a referencia discutir captura de gas, perdas, stripping ou desempenho do headspace.",
        "keywords": ["gas", "biogas", "methane", "metano", "capture", "stripping"],
    },
]


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return normalized.encode("ascii", "ignore").decode("ascii")



def _normalize_text(text: str) -> str:
    return " ".join(_TOKEN_RE.findall(_strip_accents(text.casefold())))


@lru_cache(maxsize=1)
def _repository() -> ADM1RAGRepository:
    return ADM1RAGRepository()



def get_example_queries() -> list[dict[str, str]]:
    return [dict(item) for item in EXAMPLE_QUERIES]



def get_content_type_options() -> dict[str, str]:
    return CONTENT_TYPE_OPTIONS.copy()



def get_source_catalog() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in _repository().list_sources():
        rows.append(
            {
                "source": str(item.get("source") or ""),
                "page_count": int(item.get("page_count") or 0),
                "block_count": int(item.get("block_count") or 0),
                "extractor": str(item.get("extractor") or "n/d"),
                "source_path": str(item.get("source_path") or ""),
            }
        )
    return sorted(rows, key=lambda row: row["source"].casefold())



def get_source_options() -> dict[str, str]:
    options: dict[str, str] = {}
    for item in get_source_catalog():
        options[item["source"]] = f"{item['source']} ({item['page_count']} p., {item['block_count']} blocos)"
    return options



def format_result_citation(result: dict[str, Any]) -> str:
    source = str(result.get("source") or "fonte n/d")
    page_reference = page_reference_for_result(result)
    section = str(result.get("section") or "Sem secao")
    return f"{source} | {page_reference} | {section}"



def page_reference_for_result(result: dict[str, Any]) -> str:
    page_start = int(result.get("page_start") or result.get("page") or 0)
    page_end = int(result.get("page_end") or page_start or 0)
    if page_start <= 0:
        return "pagina n/d"
    if page_end > page_start:
        return f"pp. {page_start}-{page_end}"
    return f"p. {page_start}"



def page_options_for_result(result: dict[str, Any]) -> list[int]:
    page_start = int(result.get("page_start") or result.get("page") or 0)
    page_end = int(result.get("page_end") or page_start or 0)
    if page_start <= 0:
        return [1]
    if page_end < page_start:
        page_end = page_start
    if page_end - page_start >= 9:
        page_end = page_start + 9
    return list(range(page_start, page_end + 1))



def format_search_error(exc: Exception) -> str:
    message = str(exc)
    if "Could not reach Ollama" in message or "Failed to create embeddings via Ollama" in message:
        return "Nao foi possivel consultar o Ollama local. Verifique `ollama serve` e o modelo de embedding configurado para o RAG."
    if "Chroma collection not found" in message:
        return "O indice vetorial do RAG nao foi encontrado. Rode `python rag\\index_documents.py` antes de usar a busca tecnica."
    if "Search query cannot be empty" in message:
        return "Digite uma pergunta ou conceito tecnico antes de executar a busca."
    return message



def search_technical_docs(
    query: str,
    *,
    top_k: int = 5,
    selected_sources: list[str] | None = None,
    content_types: list[str] | None = None,
) -> dict[str, Any]:
    cleaned_query = query.strip()
    if not cleaned_query:
        raise ValueError("Search query cannot be empty.")

    top_k = max(1, min(int(top_k), 10))
    source_filter = {item for item in (selected_sources or []) if item}
    content_filter = {item for item in (content_types or []) if item}

    oversampled_k = min(max(top_k * 6, 18), 36)
    raw_results = _repository().search(cleaned_query, top_k=oversampled_k)

    filtered_results: list[dict[str, Any]] = []
    for item in raw_results:
        source = str(item.get("source") or "")
        content_type = str(item.get("content_type") or "text")
        if source_filter and source not in source_filter:
            continue
        if content_filter and content_type not in content_filter:
            continue
        enriched = dict(item)
        enriched["citation"] = format_result_citation(item)
        enriched["page_reference"] = page_reference_for_result(item)
        enriched["available_pages"] = page_options_for_result(item)
        enriched["content_type_label"] = CONTENT_TYPE_OPTIONS.get(content_type, content_type)
        filtered_results.append(enriched)

    results = filtered_results[:top_k]
    citations: list[dict[str, Any]] = []
    source_hits = Counter()
    content_hits = Counter()
    for item in results:
        citations.append(
            {
                "rank": int(item.get("rank") or 0),
                "source": item.get("source"),
                "page": item.get("page_reference"),
                "section": item.get("section"),
                "content_type": item.get("content_type_label"),
                "score": float(item.get("score") or 0.0),
            }
        )
        source_hits[str(item.get("source") or "fonte n/d")] += 1
        content_hits[str(item.get("content_type") or "text")] += 1

    parameter_suggestions = suggest_simulation_parameters(cleaned_query, results)

    return {
        "query": cleaned_query,
        "top_k": top_k,
        "result_count": len(results),
        "raw_result_count": len(raw_results),
        "filters_applied": bool(source_filter or content_filter),
        "selected_sources": sorted(source_filter),
        "selected_content_types": sorted(content_filter),
        "results": results,
        "citations": citations,
        "source_hits": [
            {"source": source, "hits": hits}
            for source, hits in sorted(source_hits.items(), key=lambda item: (-item[1], item[0].casefold()))
        ],
        "content_hits": [
            {"content_type": CONTENT_TYPE_OPTIONS.get(content_type, content_type), "hits": hits}
            for content_type, hits in sorted(content_hits.items(), key=lambda item: (-item[1], item[0]))
        ],
        "parameter_suggestions": parameter_suggestions,
    }


@lru_cache(maxsize=96)
def load_page_context(source: str, page: int) -> dict[str, Any]:
    payload = _repository().get_document_section(source, page)
    blocks = payload.get("blocks", [])
    text_blocks = [str(block.get("text") or "").strip() for block in blocks if str(block.get("text") or "").strip()]
    page_text = "\n\n".join(text_blocks)
    preview_text = page_text[:7000]

    content_type_counts = Counter(str(block.get("content_type") or "text") for block in blocks)
    block_preview: list[dict[str, Any]] = []
    for index, block in enumerate(blocks[:24], start=1):
        block_preview.append(
            {
                "bloco": index,
                "tipo": CONTENT_TYPE_OPTIONS.get(str(block.get("content_type") or "text"), str(block.get("content_type") or "text")),
                "secao": str(block.get("section") or "Sem secao"),
                "chars": int(block.get("char_count") or len(str(block.get("text") or ""))),
                "texto": str(block.get("text") or "")[:260],
            }
        )

    return {
        **payload,
        "page_text": page_text,
        "preview_text": preview_text,
        "preview_truncated": len(page_text) > len(preview_text),
        "content_type_counts": {
            CONTENT_TYPE_OPTIONS.get(content_type, content_type): hits
            for content_type, hits in sorted(content_type_counts.items(), key=lambda item: (-item[1], item[0]))
        },
        "block_preview": block_preview,
        "block_preview_truncated": len(blocks) > len(block_preview),
    }



def suggest_simulation_parameters(query: str, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_query = _normalize_text(query)
    normalized_results = []
    for item in results:
        combined = " ".join(
            [
                str(item.get("section") or ""),
                str(item.get("excerpt") or ""),
                str(item.get("source") or ""),
            ]
        )
        normalized_results.append(
            {
                "text": _normalize_text(combined),
                "citation": format_result_citation(item),
            }
        )

    suggestions: list[dict[str, Any]] = []
    for bridge in PARAMETER_BRIDGES:
        matched_terms: list[str] = []
        evidence = "Consulta atual"
        for keyword in bridge["keywords"]:
            normalized_keyword = _normalize_text(str(keyword))
            if not normalized_keyword:
                continue
            if normalized_keyword in normalized_query:
                matched_terms.append(str(keyword))
                continue
            for item in normalized_results:
                if normalized_keyword in item["text"]:
                    matched_terms.append(str(keyword))
                    if evidence == "Consulta atual":
                        evidence = str(item["citation"])
                    break
        unique_terms = list(dict.fromkeys(matched_terms))
        if not unique_terms:
            continue
        suggestions.append(
            {
                "grupo": bridge["group"],
                "parametro": bridge["parameter_path"],
                "onde_ajustar": bridge["ui_location"],
                "quando_revisar": bridge["when_to_review"],
                "termos_match": ", ".join(unique_terms),
                "evidencia": evidence,
                "score": len(unique_terms),
                "priority": bridge["priority"],
            }
        )

    suggestions.sort(key=lambda item: (-int(item["score"]), -int(item["priority"]), str(item["parametro"])))
    return suggestions[:8]



def search_results_frame(payload: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for item in payload.get("results", []):
        rows.append(
            {
                "rank": item.get("rank"),
                "source": item.get("source"),
                "page": item.get("page_reference"),
                "section": item.get("section"),
                "content_type": item.get("content_type_label"),
                "score": item.get("score"),
                "semantic_score": item.get("semantic_score"),
                "lexical_score": item.get("lexical_score"),
                "excerpt": item.get("excerpt"),
            }
        )
    return pd.DataFrame(rows)



def search_results_csv_bytes(payload: dict[str, Any]) -> bytes:
    buffer = StringIO()
    search_results_frame(payload).to_csv(buffer, index=False)
    return buffer.getvalue().encode("utf-8")



def search_results_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")