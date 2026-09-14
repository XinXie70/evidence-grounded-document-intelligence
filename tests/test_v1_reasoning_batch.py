import json
import tempfile
import unittest
from pathlib import Path

from egdi.io import sha256_file, write_json
from egdi.reasoning_inputs import RESPONSE_SCHEMA
from egdi.v1_reasoning_batch import build_v1_batch_plan


class V1ReasoningBatchTests(unittest.TestCase):
    def test_skips_r3_and_estimates_only_paid_inputs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            input_path = root / "input.json"
            write_json(
                input_path,
                {
                    "question_id": "doc::q1",
                    "doc_id": "doc",
                    "condition": "real_retrieval",
                    "evidence_pages": [1],
                    "model_input": {
                        "instructions": "Use only evidence.",
                        "question": "What is it?",
                        "evidence": [{"page": 1, "text": "It is safe."}],
                        "response_schema": RESPONSE_SCHEMA,
                    },
                },
            )
            manifest = {
                "split": "development_tune",
                "contains_gold_or_answer_labels": False,
                "case_count": 2,
                "cases": [
                    {
                        "pilot_id": "p1",
                        "question_id": "doc::q1",
                        "route": "r0_text",
                        "paid_request_required": True,
                        "reasoning_input": {"path": str(input_path), "sha256": sha256_file(input_path)},
                    },
                    {
                        "pilot_id": "p2",
                        "question_id": "global::q1",
                        "route": "r3_document_global",
                        "paid_request_required": False,
                        "evidence_pages": [],
                    },
                ],
            }
            config = {"model": "model", "reasoning_effort": "low", "max_output_tokens": 10, "store": False}
            pricing = {
                "input_usd_per_million": 1.0,
                "output_usd_per_million": 2.0,
                "cache_write_input_multiplier": 1.25,
            }
            plan = build_v1_batch_plan(manifest, config, pricing)
            self.assertEqual(len(plan), 1)
            self.assertEqual(plan[0]["pilot_id"], "p1")
            self.assertGreater(plan[0]["conservative_cost_usd"], 0)

    def test_rejects_labelled_or_misrouted_manifest(self):
        with self.assertRaisesRegex(ValueError, "exclude benchmark labels"):
            build_v1_batch_plan(
                {"split": "development_tune", "contains_gold_or_answer_labels": True}, {}, {}
            )
        with self.assertRaisesRegex(ValueError, "R3"):
            build_v1_batch_plan(
                {
                    "split": "development_tune",
                    "contains_gold_or_answer_labels": False,
                    "case_count": 1,
                    "cases": [{
                        "pilot_id": "p",
                        "question_id": "q",
                        "route": "r3_document_global",
                        "paid_request_required": True,
                        "evidence_pages": [],
                    }],
                },
                {},
                {},
            )


if __name__ == "__main__":
    unittest.main()
