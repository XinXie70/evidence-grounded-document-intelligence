import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from egdi.constants import LOCKED_TEST_ACK, LOCKED_TEST_ENV
from egdi.corpus import write_page_records_jsonl
from egdi.text import build_page_record
from egdi.visual_runtime_manifest import (
    _contains_forbidden_key,
    build_visual_runtime_manifest,
)


class VisualRuntimeManifestTests(unittest.TestCase):
    def test_keeps_only_r1_questions_and_strips_all_evaluation_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_page_records_jsonl(
                root / "doc-a.jsonl",
                [build_page_record("doc-a", page, "native text") for page in range(1, 13)],
            )
            run = {
                "split": "development_tune",
                "per_question": [
                    {
                        "question_id": "q-visual",
                        "question": "Which value is shown in the table?",
                        "doc_id": "doc-a",
                        "retrieved_pages": list(range(1, 11)),
                        "gold_pages": [7],
                        "scores": {"10": {"complete_evidence_recall": 1}},
                        "slices": {"evidence_type": "table"},
                    },
                    {
                        "question_id": "q-text",
                        "question": "What is the stated policy?",
                        "doc_id": "doc-a",
                        "retrieved_pages": list(range(2, 12)),
                        "gold_pages": [4],
                    },
                ],
            }
            manifest = build_visual_runtime_manifest(run, page_records_dir=root)

        self.assertEqual(manifest["question_count"], 1)
        self.assertEqual(manifest["document_count"], 1)
        self.assertEqual(manifest["unique_candidate_page_count"], 10)
        self.assertEqual(manifest["questions"][0]["question_id"], "q-visual")
        self.assertEqual(manifest["questions"][0]["candidate_pages"], list(range(1, 11)))
        self.assertFalse(_contains_forbidden_key(manifest))
        serialized = str(manifest)
        self.assertNotIn("gold_pages", serialized)
        self.assertNotIn("scores", serialized)
        self.assertNotIn("slices", serialized)

    def test_rejects_wrong_split_short_rankings_and_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_page_records_jsonl(
                root / "doc-a.jsonl",
                [build_page_record("doc-a", page, "native text") for page in range(1, 11)],
            )
            item = {
                "question_id": "q",
                "question": "What is shown in the chart?",
                "doc_id": "doc-a",
                "retrieved_pages": list(range(1, 11)),
            }
            with self.assertRaisesRegex(ValueError, "unknown evaluation split"):
                build_visual_runtime_manifest(
                    {"split": "test", "per_question": [item]}, page_records_dir=root
                )
            with self.assertRaisesRegex(ValueError, "shorter"):
                build_visual_runtime_manifest(
                    {
                        "split": "development_tune",
                        "per_question": [{**item, "retrieved_pages": [1, 2]}],
                    },
                    page_records_dir=root,
                )
            with self.assertRaisesRegex(ValueError, "duplicate question_id"):
                build_visual_runtime_manifest(
                    {"split": "development_tune", "per_question": [item, item]},
                    page_records_dir=root,
                )

    def test_accepts_development_calibration_without_opening_locked_test(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_page_records_jsonl(
                root / "doc-a.jsonl",
                [build_page_record("doc-a", page, "native text") for page in range(1, 11)],
            )
            run = {
                "split": "development_calibration",
                "per_question": [
                    {
                        "question_id": "q-visual",
                        "question": "Which value is shown in the table?",
                        "doc_id": "doc-a",
                        "retrieved_pages": list(range(1, 11)),
                    }
                ],
            }
            manifest = build_visual_runtime_manifest(run, page_records_dir=root)

        self.assertEqual(manifest["split"], "development_calibration")
        self.assertFalse(manifest["contains_gold_or_answer_labels"])

    def test_locked_test_requires_guard_and_stays_label_free(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_page_records_jsonl(
                root / "doc-a.jsonl",
                [build_page_record("doc-a", page, "native text") for page in range(1, 11)],
            )
            run = {
                "split": "locked_test",
                "per_question": [{
                    "question_id": "q-visual",
                    "question": "Which value is shown in the table?",
                    "doc_id": "doc-a",
                    "retrieved_pages": list(range(1, 11)),
                }],
            }
            with patch.dict(os.environ, {}, clear=True), self.assertRaises(RuntimeError):
                build_visual_runtime_manifest(run, page_records_dir=root)
            with patch.dict(os.environ, {LOCKED_TEST_ENV: LOCKED_TEST_ACK}, clear=True):
                manifest = build_visual_runtime_manifest(run, page_records_dir=root)
        self.assertEqual(manifest["split"], "locked_test")
        self.assertFalse(manifest["contains_gold_or_answer_labels"])


if __name__ == "__main__":
    unittest.main()
