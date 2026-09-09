import json
import tempfile
import unittest
from pathlib import Path

from egdi.comparison_fact_batch_finalize import finalize_batch
from egdi.io import sha256_file, write_json


class ComparisonFactBatchFinalizeTests(unittest.TestCase):
    def test_finalizes_every_manifest_case_without_benchmark(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "input.json"
            write_json(input_path, {
                "question_id": "d::q", "doc_id": "d", "evidence_pages": [2],
                "model_input": {"question": "What is the difference between A and B?"},
            })
            results_dir = root / "results"
            result_path = results_dir / "case_01" / "result.json"
            write_json(result_path, {
                "question_id": "d::q", "doc_id": "d", "evidence_pages": [2],
                "input_sha256": sha256_file(input_path), "response_id": "r", "model": "m",
                "validation": {"valid": False}, "call_log": {"estimated_cost": 0.01},
                "output": {"status": "extracted", "facts": [
                    {"label": "A", "metric": "count", "value": "10,000",
                     "unit": "items", "cited_pages": [2]},
                    {"label": "B", "metric": "count", "value": "4,000",
                     "unit": "items", "cited_pages": [2]},
                ]},
            })
            manifest = {"case_count": 1, "cases": [{
                "case_id": "case_01", "question_id": "d::q",
                "input_path": str(input_path), "input_sha256": sha256_file(input_path),
            }]}

            output = finalize_batch(manifest, results_dir=results_dir)

            self.assertEqual(output["cases"][0]["deterministic_comparison"]["magnitude"], "6000")
            self.assertFalse(output["leakage_controls"]["benchmark_loaded_during_finalization"])
            self.assertEqual(output["source_estimated_cost_usd"], 0.01)


if __name__ == "__main__":
    unittest.main()
