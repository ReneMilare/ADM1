from __future__ import annotations

from simulator.full_model import (
    FULL_PARAMETER_CATALOG,
    FULL_PROCESS_CATALOG,
    FULL_STATE_CATALOG,
    audit_governance,
    build_traceability_rows,
    render_audit_markdown,
    render_traceability_markdown,
)


def test_phase6_traceability_rows_cover_full_catalog() -> None:
    rows = build_traceability_rows()
    expected_total = len(FULL_STATE_CATALOG) + len(FULL_PROCESS_CATALOG) + len(FULL_PARAMETER_CATALOG)

    assert len(rows) == expected_total
    assert {row.item for row in rows if row.entity_type == "estado"} == {state.name for state in FULL_STATE_CATALOG}
    assert {row.item for row in rows if row.entity_type == "processo"} == {process.name for process in FULL_PROCESS_CATALOG}
    assert {row.item for row in rows if row.entity_type == "parametro"} == {parameter.name for parameter in FULL_PARAMETER_CATALOG}
    assert all(row.code_ref.startswith("simulator/full_model/") for row in rows)
    assert all(row.tests for row in rows)



def test_phase6_parameter_catalog_has_source_and_classification() -> None:
    report = audit_governance()

    assert report.parameters_without_source == ()
    assert report.parameters_without_classification == ()
    assert report.parameters_with_invalid_classification == ()



def test_phase6_governance_audit_passes() -> None:
    report = audit_governance()

    assert report.provisional_parameters == ()
    assert report.missing_review_files == ()
    assert report.missing_matrix_files == ()
    assert report.missing_template_files == ()
    assert report.missing_governance_files == ()
    assert report.governance_folder_exists is True
    assert report.all_checks_pass is True



def test_phase6_markdown_renderers_include_key_sections() -> None:
    report = audit_governance()

    audit_markdown = render_audit_markdown(report)
    traceability_markdown = render_traceability_markdown(report.traceability_rows[:3], title="Teste")

    assert "Classifica\u00e7\u00f5es de par\u00e2metros" in audit_markdown
    assert "| Item | Tipo | Fonte documental | C\u00f3digo | Teste | Classifica\u00e7\u00e3o | Observa\u00e7\u00f5es |" in traceability_markdown
