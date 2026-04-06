"""Módulo central de resolução de backend.

100% independente de Streamlit. Centraliza as regras de fallback de backend
que antes estavam espalhadas entre simulation_service.py e a página.
"""

from __future__ import annotations

from webapp.contracts import SimulationDraft

# Tipos de reator que não suportam pyadm1 (requerem fallback para reduced)
_PYADM1_NON_CSTR_TYPES: frozenset[str] = frozenset({"two_phase", "tpad", "batch", "uasb", "plug_flow"})


def resolve_backend(reactor_type: str, backend_requested: str) -> tuple[str, str | None]:
    """Resolve o backend efetivo dado o tipo de reator e o backend solicitado.

    Regras:
    - pyadm1 + non-CSTR  → reduced + mensagem de fallback
    - full  + qualquer   → full (sem fallback)
    - auto  + CSTR       → pyadm1 (sem fallback)
    - auto  + non-CSTR   → reduced + mensagem
    - reduced + qualquer → reduced (sem fallback)

    Returns:
        Tupla (backend_efetivo, razão_de_fallback_ou_None).
    """
    if backend_requested == "pyadm1" and reactor_type != "cstr":
        return (
            "reduced",
            f"PyADM1 suporta apenas CSTR neste projeto. A execucao caira para o backend `reduced`.",
        )
    if backend_requested == "full":
        return "full", None
    if backend_requested == "auto" and reactor_type != "cstr":
        return (
            "reduced",
            "No modo `auto`, reatores nao CSTR continuam no backend `reduced`. Use `full` para ADM1 completo.",
        )
    if backend_requested == "auto":
        return "pyadm1", None
    # "reduced" ou qualquer outro valor desconhecido
    return backend_requested, None


def predict_backend(draft: SimulationDraft) -> tuple[str, str | None]:
    """Wrapper que recebe draft e delega para resolve_backend."""
    return resolve_backend(draft.reactor_type, draft.backend_requested)
