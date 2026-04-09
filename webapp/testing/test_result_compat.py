"""Compatibilidade com SimulationResult legado em session_state.

Garante que resultados produzidos antes da introdução de ``sic_kmol_m3``
continuem renderizáveis mesmo quando o feed não expõe esse atributo.
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from types import SimpleNamespace

from webapp.services.simulation_service import simulation_input_rows


def test_simulation_input_rows_handles_legacy_result_without_sic() -> None:
    result = SimpleNamespace(
        reactor=SimpleNamespace(reactor_type="cstr", two_phase=None, tpad=None),
        operating_conditions=SimpleNamespace(volume_m3=3000.0, temperature_c=35.0, hrt_days=20.0),
        simulation=SimpleNamespace(duration_days=45.0, solver="BDF"),
        feed=SimpleNamespace(
            name="Legacy feed",
            particulate_cod=14.0,
            soluble_cod=5.5,
            acetate=0.6,
            propionate=0.25,
            alkalinity=4.8,
            ph=7.1,
        ),
        parameters=SimpleNamespace(ammonia_inhibition_mode="simple"),
        metadata={},
    )

    rows = simulation_input_rows(result)
    sic_row = next(row for row in rows if row["parameter"] == "S_IC real")

    assert sic_row["value"] == "derivado do proxy"
