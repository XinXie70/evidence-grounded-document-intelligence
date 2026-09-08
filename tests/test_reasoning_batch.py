import json
import tempfile
import unittest
from pathlib import Path

from egdi.io import sha256_file, write_json
from egdi.reasoning_batch import _write_reused_result, build_batch_plan
from egdi.reasoning_inputs import PILOT_INSTRUCTIONS_V1, RESPONSE_SCHEMA


class ReasoningBatchTests(unittest.TestCase):
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

    def _record(self, condition):
        return {
            "schema_version": 1,
            "question_id": "doc-a::q1",
            "doc_id": "doc-a",
            "condition": condition,
            "evidence_pages": [],
            "model_input": {
                "instructions": PILOT_INSTRUCTIONS_V1,
                "question": "What unsupported value is requested?",
                "evidence": [],
                "response_schema": RESPONSE_SCHEMA,
            },
        }

    def test_groups_identical_c0_and_c2_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {}
            for condition in ("closed_book", "real_retrieval", "oracle_page"):
                path = root / f"{condition}.json"
                record = self._record(condition)
                if condition == "real_retrieval":
                    record["evidence_pages"] = [1]
                    record["model_input"]["evidence"] = [{"page": 1, "text": "context"}]
                write_json(path, record)
                paths[condition] = {
                    "path": str(path),
                    "sha256": sha256_file(path),
                }
            manifest = {
                "case_count": 1,
                "conditions": ["closed_book", "real_retrieval", "oracle_page"],
                "cases": [{
                    "pilot_id": "pilot_01",
                    "question_id": "doc-a::q1",
                    **paths,
                }],
            }

            plan = build_batch_plan(manifest, self.config, self.pricing)

            self.assertEqual(len(plan), 2)
            self.assertEqual(sum(len(group["items"]) for group in plan), 3)
            duplicate = next(group for group in plan if len(group["items"]) == 2)
            self.assertEqual(
                {item["condition"] for item in duplicate["items"]},
                {"closed_book", "oracle_page"},
            )
            self.assertGreater(duplicate["conservative_cost_usd"], 0)

    def test_reused_result_has_zero_incremental_cost_and_target_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target_input = root / "oracle_page.json"
            write_json(target_input, self._record("oracle_page"))
            target = {
                "question_id": "doc-a::q1",
                "condition": "oracle_page",
                "input_path": str(target_input),
                "input_sha256": sha256_file(target_input),
            }
            source = {
                "question_id": "doc-a::q1",
                "doc_id": "doc-a",
                "condition": "closed_book",
                "evidence_pages": [],
                "output": {
                    "answer": "guessed",
                    "cited_pages": [],
                    "status": "answerable",
                },
                "validation": {"valid": True},
                "call_log": {"status": "ok", "estimated_cost": 0.01},
            }
            output = root / "reused.json"

            reused = _write_reused_result(source, root / "closed_book.json", target, output)

            self.assertEqual(reused["condition"], "oracle_page")
            self.assertEqual(reused["call_log"]["estimated_cost"], 0.0)
            self.assertFalse(reused["validation"]["valid"])
            self.assertTrue(reused["deduplication"]["paid_request_reused"])
            self.assertEqual(reused["deduplication"]["incremental_cost_usd"], 0.0)


if __name__ == "__main__":
    unittest.main()
