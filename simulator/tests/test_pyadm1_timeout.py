from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from simulator.core.pyadm1_backend import _run_pyadm1


@pytest.mark.parametrize("configured, expected", [(None, 600.0), ("12.5", 12.5)])
def test_pyadm1_timeout_is_configurable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, configured: str | None, expected: float
) -> None:
    if configured is None:
        monkeypatch.delenv("ADM1_PYADM1_TIMEOUT_S", raising=False)
    else:
        monkeypatch.setenv("ADM1_PYADM1_TIMEOUT_S", configured)

    def run(*args: object, **kwargs: object) -> None:
        assert kwargs["timeout"] == expected
        raise subprocess.TimeoutExpired(cmd="PyADM1_runtime.py", timeout=expected)

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(RuntimeError, match=rf"timed out after {expected:g} seconds"):
        _run_pyadm1(script_path=tmp_path / "PyADM1_runtime.py", runtime_dir=tmp_path)


@pytest.mark.parametrize("configured", ["0", "-1", "nan", "inf", "invalid"])
def test_pyadm1_rejects_invalid_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, configured: str) -> None:
    monkeypatch.setenv("ADM1_PYADM1_TIMEOUT_S", configured)
    with pytest.raises(RuntimeError, match="positive finite number"):
        _run_pyadm1(script_path=tmp_path / "PyADM1_runtime.py", runtime_dir=tmp_path)
