"""Abstrações de execução — isola o conceito de 'rodar uma simulação'.

Este módulo é um esqueleto para evolução futura (fila de jobs, execução
assíncrona, API remota). A interface ExecutionBackend define o protocolo
que qualquer backend de execução deve implementar.

NOTA: Para uso em Streamlit, prefira chamar execute_simulation() diretamente
e persista o resultado em st.session_state. SyncExecutionBackend retém apenas
o último resultado (sem estado acumulado entre jobs).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from simulator.core.models import SimulationResult
    from webapp.contracts import SimulationDraft


class ExecutionBackend(Protocol):
    """Interface para backend de execução de simulação."""

    def submit(self, draft: SimulationDraft) -> str:
        """Enfileira/executa a simulação. Retorna job_id."""
        ...

    def get_result(self, job_id: str) -> SimulationResult | None:
        """Retorna resultado se disponível, ou None."""
        ...

    def get_status(self, job_id: str) -> str:
        """Retorna status: 'pending' | 'running' | 'done' | 'failed'."""
        ...


class SyncExecutionBackend:
    """Implementação síncrona — executa inline, retém apenas o último resultado.

    Não acumula resultados entre chamadas. Para uso em Streamlit, prefira
    chamar execute_simulation() diretamente e gerencie o resultado no chamador.
    """

    def __init__(self) -> None:
        self._last_job_id: str = ""
        self._last_result: SimulationResult | None = None

    def submit(self, draft: SimulationDraft) -> str:
        """Executa imediatamente. Armazena apenas o resultado mais recente."""
        from webapp.features.simulation_actions import execute_simulation
        result, _error = execute_simulation(draft)
        job_id = str(uuid.uuid4())
        self._last_job_id = job_id
        self._last_result = result
        return job_id

    def get_result(self, job_id: str) -> SimulationResult | None:
        return self._last_result if job_id == self._last_job_id else None

    def get_status(self, job_id: str) -> str:
        if job_id != self._last_job_id:
            return "unknown"
        return "done" if self._last_result is not None else "failed"
