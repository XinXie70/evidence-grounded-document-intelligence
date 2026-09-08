import json
import tempfile
import unittest
from pathlib import Path

from egdi.io import sha256_file, write_json
from egdi.page_budget_batch import _load_valid_result, build_page_budget_plan
from egdi.reasoning_inputs import PILOT_INSTRUCTIONS_V1, RESPONSE_SCHEMA


class PageBudgetBatchTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "model": "gpt-test",
            "reasoning_effort": "low",
            "max_output_tokens": 512,
            "store": False,
        }
        self.pricing = {
            "input_usd_per_million": 2.0,
            "output_usd_per_million": 12.0,
            "cache_write_input_multiplier": 1.25,
        }

    def _record(self, question_id, budget):
        return {
            "schema_version": 1,
            "question_id": question_id,
            "doc_id": question_id.split("::")[0],
            "condition": "real_retrieval",
            "page_budget": budget,
            "evidence_pages": list(range(1, budget + 1)),
            "model_input": {
                "instructions": PILOT_INSTRUCTIONS_V1,
                "question": "What value is supported?",
                "evidence": [
                    {"page": page, "text": f"Evidence on page {page}."}
                    for page in range(1, budget + 1)
                ],
                "response_schema": RESPONSE_SCHEMA,
            },
        }

    def _manifest(self, root):
        entries = []
        for smoke_index in range(1, 4):
            smoke_id = f"smoke_{smoke_index:02d}"
            question_id = f"doc-{smoke_index}::q1"
            for budget in (3, 5, 10):
                path = root / smoke_id / f"k{budget}.json"
                write_json(path, self._record(question_id, budget))
                entries.append({
                    "smoke_id": smoke_id,
                    "question_id": question_id,
                    "page_budget": budget,
                    "path": str(path),
                    "sha256": sha256_file(path),
                })
        return {
            "case_count": 3,
            "request_count": 9,
            "page_budgets": [3, 5, 10],
            "entries": entries,
        }

    def test_builds_complete_deterministic_grid(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self._manifest(Path(directory))

            plan = build_page_budget_plan(manifest, self.config, self.pricing)

            self.assertEqual(len(plan), 9)
            self.assertEqual(plan[0]["smoke_id"], "smoke_01")
            self.assertEqual(plan[0]["page_budget"], 3)
            self.assertEqual(plan[-1]["page_budget"], 10)
            self.assertTrue(all(item["conservative_cost_usd"] > 0 for item in plan))

    def test_rejects_input_checksum_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self._manifest(root)
            first_path = Path(manifest["entries"][0]["path"])
            first_path.write_text("{}", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                build_page_budget_plan(manifest, self.config, self.pricing)

    def test_existing_result_must_match_frozen_request(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self._manifest(root)
            item = build_page_budget_plan(manifest, self.config, self.pricing)[0]
            result_path = root / "result.json"
            write_json(result_path, {
                "question_id": item["question_id"],
                "condition": "real_retrieval",
                "input_sha256": item["input_sha256"],
                "config_sha256": "wrong",
                "request_sha256": item["request_sha256"],
                "call_log": {"status": "ok"},
            })

            with self.assertRaisesRegex(ValueError, "config_sha256 mismatch"):
                _load_valid_result(result_path, item, config_sha256="expected")


if __name__ == "__main__":
    unittest.main()
