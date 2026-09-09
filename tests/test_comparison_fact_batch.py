import json
import tempfile
import unittest
from pathlib import Path

from egdi.comparison_fact_batch import build_batch_plan
from egdi.io import sha256_file, write_json
from egdi.comparison_fact_input import RESPONSE_SCHEMA


class ComparisonFactBatchTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "model": "gpt-test",
            "reasoning_effort": "low",
            "max_output_tokens": 384,
            "store": False,
        }
        self.pricing = {
            "input_usd_per_million": 2.0,
            "output_usd_per_million": 12.0,
            "cache_write_input_multiplier": 1.25,
        }

    def _write_input(self, root: Path) -> Path:
        path = root / "input.json"
        write_json(path, {
            "schema_version": 1,
            "question_id": "doc-a::q1",
            "doc_id": "doc-a",
            "condition": "real_retrieval_fact_extraction",
            "evidence_pages": [1],
            "model_input": {
                "instructions": "Extract exactly two numeric facts.",
                "question": "What is the difference?",
                "evidence": [{"page": 1, "text": "A 10 B 4"}],
                "response_schema": RESPONSE_SCHEMA,
            },
        })
        return path

    def test_builds_checksum_pinned_costed_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_input(Path(directory))
            manifest = {
                "case_count": 1,
                "cases": [{
                    "case_id": "case_01",
                    "question_id": "doc-a::q1",
                    "input_path": str(path),
                    "input_sha256": sha256_file(path),
                }],
            }
            plan = build_batch_plan(manifest, self.config, self.pricing)
            self.assertEqual(len(plan), 1)
            self.assertEqual(plan[0]["case_id"], "case_01")
            self.assertGreater(plan[0]["conservative_cost_usd"], 0)
            self.assertEqual(len(plan[0]["request_sha256"]), 64)

    def test_rejects_changed_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_input(Path(directory))
            manifest = {
                "case_count": 1,
                "cases": [{
                    "case_id": "case_01",
                    "question_id": "doc-a::q1",
                    "input_path": str(path),
                    "input_sha256": "0" * 64,
                }],
            }
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                build_batch_plan(manifest, self.config, self.pricing)


if __name__ == "__main__":
    unittest.main()
