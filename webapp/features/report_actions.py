"""Actions de relatório — sem Streamlit, recebe/retorna contratos."""

from __future__ import annotations

from typing import TYPE_CHECKING

from webapp.contracts import ReportPayload
from webapp.services.report_service import DEFAULT_VAULT_PATH

if TYPE_CHECKING:
    from simulator.core.models import SimulationResult


def generate_report(
    result: SimulationResult,
    *,
    scenario_id: str | None = None,
    baseline_id: str | None = None,
) -> ReportPayload:
    """Wrapper sobre build_report_payload."""
    from webapp.services.report_service import build_report_payload
    return build_report_payload(result, scenario_id=scenario_id, baseline_id=baseline_id)


def export_report(
    payload: ReportPayload,
    vault_path: str = DEFAULT_VAULT_PATH,
) -> tuple[str, str | None]:
    """Salva relatório no vault. Retorna (path, None) ou ('', error_msg)."""
    from webapp.services.report_service import export_report_to_vault
    try:
        path = export_report_to_vault(payload, vault_path)
        return path, None
    except Exception as exc:
        return "", str(exc)


def render_markdown(payload: ReportPayload) -> str:
    """Wrapper sobre render_report_markdown."""
    from webapp.services.report_service import render_report_markdown
    return render_report_markdown(payload)
