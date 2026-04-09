"""Contratos canônicos do WebApp ADM1.

Módulo 100% independente de Streamlit: usa apenas stdlib + typing.
Representa o caso técnico (SimulationDraft) e seus artefatos derivados.
"""

from __future__ import annotations

import dataclasses
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ─── helpers ──────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_uuid() -> str:
    return str(uuid.uuid4())


# ─── SimulationDraft ──────────────────────────────────────────────────────────

@dataclass
class SimulationDraft:
    """Representa o caso técnico antes da execução.

    Captura toda a configuração da UI (session_state) de forma estruturada e
    independente de Streamlit. Serve como fonte de verdade para revisão,
    persistência e passagem de argumentos ao serviço de simulação.
    """

    # Identificação
    draft_id: str = field(default_factory=_new_uuid)
    created_at: str = field(default_factory=_now_iso)

    # Caso técnico
    reactor_type: str = "cstr"        # "cstr" | "uasb" | "plug_flow" | "two_phase" | "tpad" | "batch"
    substrate_mode: str = "preset"    # "preset" | "codigestion" | "custom" | "manual"
    preset_id: str | None = None
    custom_substrate_name: str | None = None
    feed_name: str | None = None       # nome do substrato manual/custom

    # Feed manual (quando substrate_mode in {"manual", "custom"})
    # chaves: particulate_cod, soluble_cod, acetate, propionate, hydrogen,
    #         inorganic_nitrogen, alkalinity, sic_kmol_m3, ph
    feed_params: dict[str, float] = field(default_factory=dict)

    # Operação
    hydraulic_mode: str = "hrt"       # "hrt" | "flow_rate"
    volume_m3: float = 3000.0
    temperature_c: float = 35.0
    hrt_days: float = 20.0
    flow_rate_m3_day: float = 150.0

    # Backend
    backend_requested: str = "full"  # "pyadm1" | "full" | "auto" | "reduced"

    # Extensões do backend full
    extensions: list[str] = field(default_factory=list)
    # Chaves: session-state keys (ex: "srb_initial_so4", "phos_initial_s_ip")
    extension_state_overrides: dict[str, float] = field(default_factory=dict)
    extension_influent_overrides: dict[str, float] = field(default_factory=dict)
    extension_param_overrides: dict[str, float] = field(default_factory=dict)

    # Opções de execução
    duration_days: float = 45.0
    evaluation_points: int = 181
    solver: str = "BDF"
    persist: bool = True

    # Opções de inibição e variante de reator
    ammonia_inhibition_mode: str = "simple"  # "simple" | "fan"
    variant_config: dict[str, Any] | None = None  # configuração de two_phase/tpad/batch

    # Co-digestão personalizada (substrate_mode == "codigestion" + preset_id == "__custom__")
    codigestion_fractions: dict[str, float] | None = None  # {substrate_id: fraction}

    # Metadados
    origin: str = "manual"  # "manual" | "preset_user" | "preset_system"
    schema_version: str = "1"


# ─── SimulationReviewSnapshot ─────────────────────────────────────────────────

@dataclass
class SimulationReviewSnapshot:
    """Snapshot de revisão derivado de um SimulationDraft.

    Contém a resolução de backend, flags de consistência técnica e warnings
    calculados sem executar a simulação.
    """

    draft_id: str = ""
    reactor_type: str = "cstr"
    substrate_mode: str = "preset"
    preset_id: str | None = None

    backend_requested: str = "full"
    backend_predicted: str = "full"   # backend que será usado de fato
    backend_effective: str = "full"   # reservado para futuro (= predicted)
    fallback_reason: str | None = None

    extensions: list[str] = field(default_factory=list)

    consistency_flags: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    is_ready: bool = True

    schema_version: str = "1"


# ─── ScenarioArtifact (stub — Planos 04 e 05) ────────────────────────────────

@dataclass
class ScenarioArtifact:
    """Artefato persistido de um cenário de simulação."""

    scenario_id: str = field(default_factory=_new_uuid)
    draft: SimulationDraft = field(default_factory=SimulationDraft)
    result_id: str | None = None        # simulation_id do resultado mais recente
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    baseline_id: str | None = None      # scenario_id do cenário base para diff
    schema_version: str = "1"


# ─── ReportPayload (stub — Plano 05) ─────────────────────────────────────────

@dataclass
class ReportPayload:
    """Payload de relatório técnico gerado a partir de um cenário simulado."""

    report_id: str = field(default_factory=_new_uuid)
    scenario_id: str | None = None
    draft: SimulationDraft = field(default_factory=SimulationDraft)
    review: SimulationReviewSnapshot = field(default_factory=SimulationReviewSnapshot)
    kpis: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    interpretation: str = ""
    diff_with_baseline: dict[str, Any] | None = None
    generated_at: str = field(default_factory=_now_iso)
    schema_version: str = "1"


# ─── Serialização / Deserialização ───────────────────────────────────────────

def draft_to_dict(draft: SimulationDraft) -> dict[str, Any]:
    return dataclasses.asdict(draft)


def draft_from_dict(data: dict[str, Any]) -> SimulationDraft:
    known = {f.name for f in dataclasses.fields(SimulationDraft)}
    filtered = {k: v for k, v in data.items() if k in known}
    return SimulationDraft(**filtered)


def review_to_dict(review: SimulationReviewSnapshot) -> dict[str, Any]:
    return dataclasses.asdict(review)


def review_from_dict(data: dict[str, Any]) -> SimulationReviewSnapshot:
    known = {f.name for f in dataclasses.fields(SimulationReviewSnapshot)}
    filtered = {k: v for k, v in data.items() if k in known}
    return SimulationReviewSnapshot(**filtered)


def artifact_to_dict(artifact: ScenarioArtifact) -> dict[str, Any]:
    return dataclasses.asdict(artifact)


def artifact_from_dict(data: dict[str, Any]) -> ScenarioArtifact:
    known = {f.name for f in dataclasses.fields(ScenarioArtifact)}
    filtered = {k: v for k, v in data.items() if k in known}
    if "draft" in filtered and isinstance(filtered["draft"], dict):
        filtered["draft"] = draft_from_dict(filtered["draft"])
    return ScenarioArtifact(**filtered)
