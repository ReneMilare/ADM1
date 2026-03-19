from __future__ import annotations

import json
import unittest
from pathlib import Path

import numpy as np

from rag.chunking import ChunkConfig, chunk_document
from rag.repository import ADM1RAGRepository, _lexical_score
from rag.schemas import ExtractedBlock, ExtractedDocument
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

    def test_chunk_document_preserves_breaks_and_chunk_char_count(self) -> None:
        left_text = " ".join(f"alpha{i}" for i in range(18))
        right_text = " ".join(f"beta{i}" for i in range(18))
        document = ExtractedDocument(
            source="sample.pdf",
            source_path="C:/tmp/sample.pdf",
            file_sha256="abc",
            extracted_at="2026-03-19T00:00:00+00:00",
            extractor="unit-test",
            page_count=1,
            blocks=[
                ExtractedBlock(
                    block_id="b1",
                    source="sample.pdf",
                    page=1,
                    section="Secao",
                    content_type="text",
                    text=left_text,
                ),
                ExtractedBlock(
                    block_id="b2",
                    source="sample.pdf",
                    page=1,
                    section="Secao",
                    content_type="text",
                    text=right_text,
                ),
            ],
            metadata={},
        )

        joined_chunks = chunk_document(document, ChunkConfig(target_tokens=40, overlap_ratio=0.0))
        self.assertEqual(joined_chunks[0].text, f"{left_text}\n\n{right_text}")
        self.assertEqual(joined_chunks[0].metadata["char_count"], len(joined_chunks[0].text))

        split_chunks = chunk_document(document, ChunkConfig(target_tokens=32, overlap_ratio=0.0))
        self.assertGreaterEqual(len(split_chunks), 2)
        for chunk in split_chunks:
            self.assertEqual(chunk.metadata["char_count"], len(chunk.text))

    def test_repository_uses_manifest_chunk_config_and_precise_lexical_matching(self) -> None:
        manifest_path = WORKSPACE_ROOT / "index_manifest.json"
        manifest_path.write_text(
            json.dumps({"chunk_config": {"target_tokens": 128, "overlap_ratio": 0.1}}),
            encoding="utf-8",
        )
        try:
            repository = ADM1RAGRepository(extracted_dir=WORKSPACE_ROOT, db_dir=WORKSPACE_ROOT, embedding_model="test-model")
            self.assertEqual(repository._chunk_config.target_tokens, 128)
            self.assertAlmostEqual(repository._chunk_config.overlap_ratio, 0.1)
            self.assertEqual(_lexical_score("hrt", "throttle throughput"), 0.0)
            self.assertGreater(_lexical_score("estado estacionario", "Operando em estado estacionario."), 0.0)
        finally:
            manifest_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
