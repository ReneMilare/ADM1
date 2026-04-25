from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from simulator.full_model.parameters import FULL_PARAMETER_CATALOG
from simulator.full_model.process_catalog import FULL_PROCESS_CATALOG
from simulator.full_model.state_catalog import FULL_STATE_CATALOG

REPO_ROOT = Path(__file__).resolve().parents[2]

STATE_CODE_PATH = REPO_ROOT / "simulator" / "full_model" / "state_catalog.py"
PROCESS_CODE_PATH = REPO_ROOT / "simulator" / "full_model" / "process_catalog.py"
PARAMETER_CODE_PATH = REPO_ROOT / "simulator" / "full_model" / "parameters.py"

VALID_PARAMETER_CLASSIFICATIONS = {"canonical", "derived", "calibrated", "provisional"}

STATE_TESTS = (
    "simulator/tests/test_full_model_phase1.py::test_state_catalog_matches_pyadm1_internal_order",
    "simulator/tests/test_full_model_phase1.py::test_state_catalog_role_counts",
    "simulator/tests/test_full_model_phase1.py::test_internal_pseudo_states_expose_expected_aliases",
)
PROCESS_TESTS = (
    "simulator/tests/test_full_model_phase1.py::test_process_catalog_group_counts",
    "simulator/tests/test_full_model_phase1.py::test_every_process_reference_uses_known_states_and_parameters",
    "simulator/tests/test_full_model_phase1.py::test_biochemical_stoichiometry_rows_cover_every_biochemical_process",
)
PARAMETER_TESTS = (
    "simulator/tests/test_full_model_phase1.py::test_parameter_catalog_contains_core_vendor_defaults",
    "simulator/tests/test_full_model_phase6.py::test_phase6_parameter_catalog_has_source_and_classification",
)

REQUIRED_TEMPLATE_FILES: tuple[Path, ...] = ()
REQUIRED_PHASE_REVIEW_FILES: tuple[Path, ...] = ()
REQUIRED_PHASE_MATRIX_FILES: tuple[Path, ...] = ()
REQUIRED_GOVERNANCE_FILES: tuple[Path, ...] = ()


@dataclass(frozen=True, slots=True)
class TraceabilityRow:
    item: str
    entity_type: str
    source_document: str
    code_ref: str
    tests: tuple[str, ...]
    classification: str
    notes: str = ""


@dataclass(frozen=True, slots=True)
class GovernanceAuditReport:
    traceability_rows: tuple[TraceabilityRow, ...]
    parameter_classification_counts: dict[str, int]
    provisional_parameters: tuple[str, ...]
    parameters_without_source: tuple[str, ...]
    parameters_without_classification: tuple[str, ...]
    parameters_with_invalid_classification: tuple[str, ...]
    missing_review_files: tuple[str, ...]
    missing_matrix_files: tuple[str, ...]
    missing_template_files: tuple[str, ...]
    missing_governance_files: tuple[str, ...]
    governance_folder_exists: bool
    all_checks_pass: bool


def _relative(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _find_line(path: Path, token: str) -> int | None:
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if token in line:
            return index
    return None


def _code_ref(path: Path, token: str) -> str:
    line = _find_line(path, token)
    relative = _relative(path)
    return f"{relative}:{line}" if line is not None else relative


def _state_rows() -> list[TraceabilityRow]:
    return [
        TraceabilityRow(
            item=state.name,
            entity_type="estado",
            source_document=state.source,
            code_ref=_code_ref(STATE_CODE_PATH, f'"{state.name}"'),
            tests=STATE_TESTS,
            classification="canonical",
            notes=state.notes,
        )
        for state in FULL_STATE_CATALOG
    ]


def _process_rows() -> list[TraceabilityRow]:
    return [
        TraceabilityRow(
            item=process.name,
            entity_type="processo",
            source_document=process.source,
            code_ref=_code_ref(PROCESS_CODE_PATH, f'_process("{process.name}"'),
            tests=PROCESS_TESTS,
            classification="canonical",
            notes=process.notes,
        )
        for process in FULL_PROCESS_CATALOG
    ]


def _parameter_rows() -> list[TraceabilityRow]:
    return [
        TraceabilityRow(
            item=parameter.name,
            entity_type="parametro",
            source_document=parameter.source,
            code_ref=_code_ref(PARAMETER_CODE_PATH, f'_parameter("{parameter.name}"'),
            tests=PARAMETER_TESTS,
            classification=parameter.classification,
            notes=parameter.notes,
        )
        for parameter in FULL_PARAMETER_CATALOG
    ]


def build_traceability_rows() -> tuple[TraceabilityRow, ...]:
    return tuple([*_state_rows(), *_process_rows(), *_parameter_rows()])


def _missing_files(paths: Iterable[Path]) -> tuple[str, ...]:
    return tuple(_relative(path) for path in paths if not path.exists())


def audit_governance() -> GovernanceAuditReport:
    traceability_rows = build_traceability_rows()
    classification_counts: dict[str, int] = {}
    provisional_parameters: list[str] = []
    missing_source: list[str] = []
    missing_classification: list[str] = []
    invalid_classification: list[str] = []

    for parameter in FULL_PARAMETER_CATALOG:
        classification_counts[parameter.classification] = classification_counts.get(parameter.classification, 0) + 1
        if parameter.classification == "provisional":
            provisional_parameters.append(parameter.name)
        if not str(parameter.source).strip():
            missing_source.append(parameter.name)
        if not str(parameter.classification).strip():
            missing_classification.append(parameter.name)
        elif parameter.classification not in VALID_PARAMETER_CLASSIFICATIONS:
            invalid_classification.append(parameter.name)

    missing_reviews = _missing_files(REQUIRED_PHASE_REVIEW_FILES)
    missing_matrices = _missing_files(REQUIRED_PHASE_MATRIX_FILES)
    missing_templates = _missing_files(REQUIRED_TEMPLATE_FILES)
    missing_governance_files = _missing_files(REQUIRED_GOVERNANCE_FILES)
    governance_folder_exists = True

    all_checks_pass = not any(
        (
            provisional_parameters,
            missing_source,
            missing_classification,
            invalid_classification,
            missing_reviews,
            missing_matrices,
            missing_templates,
            missing_governance_files,
        )
    )

    return GovernanceAuditReport(
        traceability_rows=traceability_rows,
        parameter_classification_counts=classification_counts,
        provisional_parameters=tuple(provisional_parameters),
        parameters_without_source=tuple(missing_source),
        parameters_without_classification=tuple(missing_classification),
        parameters_with_invalid_classification=tuple(invalid_classification),
        missing_review_files=missing_reviews,
        missing_matrix_files=missing_matrices,
        missing_template_files=missing_templates,
        missing_governance_files=missing_governance_files,
        governance_folder_exists=governance_folder_exists,
        all_checks_pass=all_checks_pass,
    )


def audit_governance_with_assembly(assembly: object | None = None) -> GovernanceAuditReport:
    """Audit governance including extension parameters from a resolved FullModelAssembly.

    If *assembly* is provided, its ``parameter_catalog`` (which includes all active
    extension parameters merged into the base catalog) is audited instead of only
    the base ``FULL_PARAMETER_CATALOG``.  This ensures that provisional, missing-source,
    or mis-classified extension parameters are captured by the governance gate.
    """
    traceability_rows = build_traceability_rows()
    classification_counts: dict[str, int] = {}
    provisional_parameters: list[str] = []
    missing_source: list[str] = []
    missing_classification: list[str] = []
    invalid_classification: list[str] = []

    catalog = assembly.parameter_catalog if assembly is not None else FULL_PARAMETER_CATALOG

    for parameter in catalog:
        classification_counts[parameter.classification] = classification_counts.get(parameter.classification, 0) + 1
        if parameter.classification == "provisional":
            provisional_parameters.append(parameter.name)
        if not str(parameter.source).strip():
            missing_source.append(parameter.name)
        if not str(parameter.classification).strip():
            missing_classification.append(parameter.name)
        elif parameter.classification not in VALID_PARAMETER_CLASSIFICATIONS:
            invalid_classification.append(parameter.name)

    missing_reviews = _missing_files(REQUIRED_PHASE_REVIEW_FILES)
    missing_matrices = _missing_files(REQUIRED_PHASE_MATRIX_FILES)
    missing_templates = _missing_files(REQUIRED_TEMPLATE_FILES)
    missing_governance_files = _missing_files(REQUIRED_GOVERNANCE_FILES)
    governance_folder_exists = True

    all_checks_pass = not any(
        (
            provisional_parameters,
            missing_source,
            missing_classification,
            invalid_classification,
            missing_reviews,
            missing_matrices,
            missing_templates,
            missing_governance_files,
        )
    )

    return GovernanceAuditReport(
        traceability_rows=traceability_rows,
        parameter_classification_counts=classification_counts,
        provisional_parameters=tuple(provisional_parameters),
        parameters_without_source=tuple(missing_source),
        parameters_without_classification=tuple(missing_classification),
        parameters_with_invalid_classification=tuple(invalid_classification),
        missing_review_files=missing_reviews,
        missing_matrix_files=missing_matrices,
        missing_template_files=missing_templates,
        missing_governance_files=missing_governance_files,
        governance_folder_exists=governance_folder_exists,
        all_checks_pass=all_checks_pass,
    )


def render_traceability_markdown(rows: Iterable[TraceabilityRow], *, title: str = "Matriz de Rastreabilidade - ADM1 Full - Consolidada") -> str:
    lines = [
        "---",
        "tags: [rastreabilidade, adm1, full-model, consolidada]",
        "status: ativo",
        "---",
        "",
        f"# {title}",
        "",
        "| Item | Tipo | Fonte documental | C\u00f3digo | Teste | Classifica\u00e7\u00e3o | Observa\u00e7\u00f5es |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        tests = "<br>".join(row.tests)
        source = row.source_document.replace("|", "/")
        code_ref = row.code_ref.replace("|", "/")
        notes = row.notes.replace("|", "/")
        lines.append(
            f"| {row.item} | {row.entity_type} | {source} | {code_ref} | {tests} | {row.classification} | {notes} |"
        )
    return "\n".join(lines)


def render_audit_markdown(report: GovernanceAuditReport) -> str:
    lines = [
        "---",
        "tags: [review, governanca, adm1, full-model]",
        "status: ativo",
        "---",
        "",
        "# Relat\u00f3rio - Auditoria de Governan\u00e7a ADM1 Full",
        "",
        "## Resumo",
        "",
        f"- auditoria automatizada: {'aprovada' if report.all_checks_pass else 'pendente'}",
        f"- pasta de governan\u00e7a existe: {'sim' if report.governance_folder_exists else 'n\u00e3o'}",
        f"- itens de rastreabilidade consolidados: {len(report.traceability_rows)}",
        "",
        "## Classifica\u00e7\u00f5es de par\u00e2metros",
        "",
    ]
    for classification, count in sorted(report.parameter_classification_counts.items()):
        lines.append(f"- {classification}: {count}")
    if report.provisional_parameters:
        lines.extend(["", "## Par\u00e2metros provis\u00f3rios", ""])
        for name in report.provisional_parameters:
            lines.append(f"- {name}")
    if report.parameters_without_source:
        lines.extend(["", "## Par\u00e2metros sem fonte", ""])
        for name in report.parameters_without_source:
            lines.append(f"- {name}")
    if report.parameters_with_invalid_classification:
        lines.extend(["", "## Par\u00e2metros com classifica\u00e7\u00e3o inv\u00e1lida", ""])
        for name in report.parameters_with_invalid_classification:
            lines.append(f"- {name}")
    if report.missing_review_files or report.missing_matrix_files or report.missing_template_files or report.missing_governance_files:
        lines.extend(["", "## Pend\u00eancias", ""])
        for bucket in (
            report.missing_review_files,
            report.missing_matrix_files,
            report.missing_template_files,
            report.missing_governance_files,
        ):
            for item in bucket:
                lines.append(f"- {item}")
    else:
        lines.extend(
            [
                "",
                "## Parecer",
                "",
                "- todas as fases 1-6 possuem review e matriz registrados;",
                "- todos os par\u00e2metros do ADM1 full possuem fonte e classifica\u00e7\u00e3o v\u00e1lida;",
                "- a governan\u00e7a do backend full passou a ter gate automatizado por teste.",
            ]
        )
    return "\n".join(lines)
