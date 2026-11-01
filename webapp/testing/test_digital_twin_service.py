from __future__ import annotations

from io import BytesIO

import pandas as pd
import pytest
from pydantic import ValidationError

from webapp.services.digital_twin_service import run_scenario
from webapp.components.status_cards import _PAGE_LINKS


def test_run_returns_series_metrics_and_memory_csv():
    result = run_scenario("steady_noisy", "observed", seed=5, duration_days=2)
    assert set(result["series"]) == {"plant", "twin", "measurements"}
    assert len(result["metrics"]) == 6
    assert {"n", "mape", "rmse", "bias"} <= result["metrics"]["ph"].keys()
    for key, frame in result["series"].items():
        pd.testing.assert_frame_equal(pd.read_csv(BytesIO(result["csv"][key])), frame, check_dtype=False)


def test_input_validation_and_ukf_reservation():
    with pytest.raises(ValidationError):
        run_scenario("unknown", duration_days=1)
    with pytest.raises(ValidationError):
        run_scenario("steady_noisy", influent="invalid")
    with pytest.raises(ValidationError):
        run_scenario("steady_noisy", duration_days=0)
    with pytest.raises(ValueError, match="UKF"):
        run_scenario("steady_noisy", estimator="ukf")


def test_page_is_in_custom_navigation():
    assert any(item["path"] == "pages/07_Gemeo_Digital.py" for item in _PAGE_LINKS)


def test_page_runs_and_shows_results(monkeypatch):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "pages/07_Gemeo_Digital.py", default_timeout=60).run()
    assert not app.exception
    app.number_input[0].set_value(2)
    app.button[0].click().run(timeout=60)
    assert not app.exception
    assert not app.error
    assert len(app.get("plotly_chart")) == 6
    assert len(app.get("download_button")) == 3
