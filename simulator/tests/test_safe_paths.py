from __future__ import annotations

import json
from pathlib import Path

from simulator.paths import PROJECT_ROOT, _safe_project_path
from webapp.services.health import load_latest_report
from webapp.services.validation_service import artifact_bytes


def test_safe_project_path_hides_external_paths(tmp_path: Path) -> None:
    assert _safe_project_path(PROJECT_ROOT / "simulator" / "runs") == "simulator/runs"
    assert _safe_project_path(tmp_path / "secret" / "report.json") == "report.json"
    link = tmp_path / "link"
    link.symlink_to(PROJECT_ROOT / "simulator", target_is_directory=True)
    assert _safe_project_path(link / "runs") == "simulator/runs"


def test_health_reports_do_not_expose_local_paths(tmp_path: Path) -> None:
    report_dir = tmp_path / "run"
    report_dir.mkdir()
    report = report_dir / "phase3_validation.json"
    report.write_text(json.dumps({"status": "ok"}), encoding="utf-8")
    result = load_latest_report(tmp_path, report.name)
    assert result is not None
    assert result["path"] == report.name
    report.write_text("invalid", encoding="utf-8")
    result = load_latest_report(tmp_path, report.name)
    assert result is not None
    assert str(tmp_path) not in str(result)


def test_artifact_bytes_resolves_relative_to_project(monkeypatch, tmp_path: Path) -> None:
    from webapp.services import validation_service

    monkeypatch.setattr(validation_service, "PROJECT_ROOT", tmp_path)
    (tmp_path / "report.json").write_bytes(b"{}")
    assert artifact_bytes("report.json") == b"{}"
