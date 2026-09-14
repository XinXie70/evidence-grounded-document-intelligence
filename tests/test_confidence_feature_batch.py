import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from egdi.constants import LOCKED_TEST_ACK, LOCKED_TEST_ENV
from egdi.confidence_feature_batch import (
    apply_case_corrections,
    build_confidence_feature_manifest,
)
from egdi.io import write_json


class ConfidenceFeatureBatchTests(unittest.TestCase):
    def test_freezes_hashes_and_hides_answer_text(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            result_path = root / "p1" / "real_retrieval.json"
            write_json(
                result_path,
                {
                    "question_id": "doc::q1",
                    "doc_id": "doc",
                    "evidence_pages": [1],
                    "output": {
                        "answer": "a secret answer",
                        "cited_pages": [1],
                        "status": "answerable",
                    },
                    "validation": {
                        "valid": True,
                        "citations_within_supplied_context": True,
                    },
                },
            )
            manifest = {
                "split": "development_calibration",
                "contains_gold_or_answer_labels": False,
                "case_count": 1,
                "cases": [{
                    "pilot_id": "p1",
                    "question_id": "doc::q1",
                    "doc_id": "doc",
                    "route": "r0_text",
                    "evidence_pages": [1],
                    "confidence_features": {
                        "question_id": "doc::q1",
                        "doc_id": "doc",
                        "evidence_page_count": 1,
                    },
                }],
            }
            output = build_confidence_feature_manifest(manifest, result_dir=root)
            self.assertEqual(output["split"], "development_calibration")
            self.assertTrue(output["cases"][0]["features"]["policy_eligible"])
            self.assertNotIn("a secret answer", str(output))
            self.assertEqual(len(output["cases"][0]["reasoning_result"]["sha256"]), 64)

    def test_rejects_evidence_drift(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_json(
                root / "p1" / "real_retrieval.json",
                {
                    "question_id": "q",
                    "doc_id": "d",
                    "evidence_pages": [2],
                },
            )
            manifest = {
                "split": "development_tune",
                "contains_gold_or_answer_labels": False,
                "case_count": 1,
                "cases": [{
                    "pilot_id": "p1",
                    "question_id": "q",
                    "doc_id": "d",
                    "route": "r0_text",
                    "evidence_pages": [1],
                    "confidence_features": {"question_id": "q"},
                }],
            }
            with self.assertRaisesRegex(ValueError, "evidence drift"):
                build_confidence_feature_manifest(manifest, result_dir=root)

    def test_correction_cannot_change_retrieval_or_identity(self):
        case = {
            "pilot_id": "p1",
            "question_id": "q1",
            "doc_id": "d1",
            "route": "r2_scanned_document",
            "evidence_pages": [1, 2, 3],
            "confidence_features": {"question_id": "q1"},
            "reasoning_input": {"sha256": "old"},
        }
        base = {"split": "development_tune", "contains_gold_or_answer_labels": False, "cases": [case]}
        replacement = {**case, "reasoning_input": {"sha256": "new"}}
        correction = {
            "split": "development_tune",
            "contains_gold_or_answer_labels": False,
            "cases": [replacement],
        }
        merged, ids = apply_case_corrections(base, correction)
        self.assertEqual(ids, ["p1"])
        self.assertEqual(merged["cases"][0]["reasoning_input"]["sha256"], "new")
        correction["cases"][0] = {**replacement, "evidence_pages": [9]}
        with self.assertRaisesRegex(ValueError, "evidence_pages"):
            apply_case_corrections(base, correction)

    def test_locked_test_feature_generation_requires_guard(self):
        manifest = {
            "split": "locked_test",
            "contains_gold_or_answer_labels": False,
            "case_count": 0,
            "cases": [],
        }
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ, {}, clear=True), self.assertRaises(RuntimeError):
                build_confidence_feature_manifest(manifest, result_dir=Path(folder))


if __name__ == "__main__":
    unittest.main()
