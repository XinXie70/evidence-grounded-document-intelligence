import hashlib
import os
import unittest
from unittest.mock import patch

from egdi.constants import LOCKED_TEST_ACK, LOCKED_TEST_ENV
from egdi.evaluation_selection import build_label_free_selection


class EvaluationSelectionTests(unittest.TestCase):
    def setUp(self):
        self.benchmark = [
            {
                "id": "d1::q1",
                "question": "What is shown?",
                "pdf": {"doc_id_str": "d1"},
                "answer": {"answer_text": "secret", "is_answerable": True},
                "evidences": [{"page": 9}],
            }
        ]
        self.splits = {
            "development_calibration": {
                "question_count": 1,
                "question_ids": ["d1::q1"],
                "document_ids": ["d1"],
            }
        }

    def test_projects_only_inference_fields(self):
        result = build_label_free_selection(
            self.benchmark, self.splits, split_name="development_calibration"
        )
        self.assertEqual(result, [{
            "pilot_id": "calibration_001",
            "question_id": "d1::q1",
            "doc_id": "d1",
            "question": "What is shown?",
        }])
        self.assertNotIn("secret", str(result))

    def test_locked_split_requires_guard_and_projects_only_safe_fields(self):
        locked = [{**self.benchmark[0], "id": "locked::q1", "split": "test"}]
        splits = {"locked_test": {
            "question_count": 1,
            "document_count": 1,
            "document_ids": ["d1"],
            "question_ids_omitted": True,
            "question_ids_sha256": hashlib.sha256(b"locked::q1").hexdigest(),
        }}
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(RuntimeError):
            build_label_free_selection(locked, splits, split_name="locked_test")
        with patch.dict(os.environ, {LOCKED_TEST_ENV: LOCKED_TEST_ACK}, clear=True):
            result = build_label_free_selection(locked, splits, split_name="locked_test")
        self.assertEqual(result[0]["pilot_id"], "locked_test_001")
        self.assertNotIn("secret", str(result))

    def test_rejects_cross_split_document(self):
        self.splits["development_calibration"]["document_ids"] = ["other"]
        with self.assertRaisesRegex(ValueError, "outside"):
            build_label_free_selection(
                self.benchmark, self.splits, split_name="development_calibration"
            )


if __name__ == "__main__":
    unittest.main()
