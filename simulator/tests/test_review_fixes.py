from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from simulator.core.kinetics import reaction_vector
from simulator.core.models import InitialState, KineticParameters, ReactorConfig
from simulator.scenario_store import ScenarioStore

WORKSPACE_ROOT = Path("simulator") / "tests"


class ReviewFixesTest(unittest.TestCase):
    def test_reactor_config_normalizes_segments_and_allows_zero_capture(self) -> None:
        config = ReactorConfig(reactor_type="cstr", segments=6, gas_capture_efficiency=0.0)
        self.assertEqual(config.segments, 1)
        self.assertEqual(config.name, "CSTR")
        self.assertEqual(config.gas_capture_efficiency, 0.0)

    def test_scenario_store_rejects_path_traversal(self) -> None:
        store = ScenarioStore(WORKSPACE_ROOT)
        with self.assertRaises(ValueError):
            store.path_for(r"..\outside")

    def test_propionate_conversion_depends_on_propionate_biomass(self) -> None:
        params = KineticParameters()
        low_acidogens = np.asarray(
            InitialState(propionate=1.0, acidogens=0.1, propionate_biomass=0.5).to_vector(),
            dtype=float,
        )
        high_acidogens = np.asarray(
            InitialState(propionate=1.0, acidogens=5.0, propionate_biomass=0.5).to_vector(),
            dtype=float,
        )
        no_propionate_biomass = np.asarray(
            InitialState(propionate=1.0, acidogens=5.0, propionate_biomass=0.0).to_vector(),
            dtype=float,
        )

        _, low_diag = reaction_vector(
            low_acidogens,
            influent_ph=7.0,
            temperature_c=35.0,
            params=params,
            hydrolysis_multiplier=1.0,
            gas_capture_efficiency=1.0,
        )
        _, high_diag = reaction_vector(
            high_acidogens,
            influent_ph=7.0,
            temperature_c=35.0,
            params=params,
            hydrolysis_multiplier=1.0,
            gas_capture_efficiency=1.0,
        )
        _, zero_diag = reaction_vector(
            no_propionate_biomass,
            influent_ph=7.0,
            temperature_c=35.0,
            params=params,
            hydrolysis_multiplier=1.0,
            gas_capture_efficiency=1.0,
        )

        self.assertAlmostEqual(
            low_diag["propionate_conversion_rate"],
            high_diag["propionate_conversion_rate"],
            places=9,
        )
        self.assertAlmostEqual(zero_diag["propionate_conversion_rate"], 0.0, places=9)

if __name__ == "__main__":
    unittest.main()
