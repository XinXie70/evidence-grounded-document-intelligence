import os
import unittest
from unittest.mock import patch

import numpy as np

from egdi.constants import LOCKED_TEST_ACK, LOCKED_TEST_ENV
from egdi.text import build_page_record
from egdi.v1_retrieval_candidates import build_retrieval_candidates


class FakeEncoder:
    def split_text(self, text, chunk_tokens, overlap_tokens):
        return [text]

    def encode_passages(self, texts):
        return np.asarray([[float("needle" in text), 1.0] for text in texts])

    def encode_query(self, query):
        return np.asarray([1.0, 1.0])


class V1RetrievalCandidatesTests(unittest.TestCase):
    def test_builds_label_free_candidates_for_text_and_visual_routes(self):
        records = [
            build_page_record("doc-a", page, "needle" if page == 4 else f"page {page}")
            for page in range(1, 11)
        ]
        rows = [
            {"pilot_id": "p1", "question_id": "q1", "doc_id": "doc-a", "question": "What mentions needle?"},
            {"pilot_id": "p2", "question_id": "q2", "doc_id": "doc-a", "question": "Which value is shown in the table?"},
        ]
        result = build_retrieval_candidates(
            rows, {"doc-a": records}, FakeEncoder(), split="development_calibration"
        )

        self.assertEqual(result["split"], "development_calibration")
        self.assertEqual(result["eligible_question_count"], 2)
        self.assertFalse(result["contains_gold_or_answer_labels"])
        self.assertEqual(len(result["per_question"][0]["retrieved_pages"]), 10)
        self.assertNotIn("gold_pages", str(result))

    def test_rejects_unguarded_locked_test_and_duplicate_question_ids(self):
        records = [build_page_record("doc-a", page, "text") for page in range(1, 11)]
        row = {"pilot_id": "p1", "question_id": "q1", "doc_id": "doc-a", "question": "What text?"}
        with self.assertRaises(RuntimeError):
            build_retrieval_candidates([row], {"doc-a": records}, FakeEncoder(), split="locked_test")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            build_retrieval_candidates([row, row], {"doc-a": records}, FakeEncoder(), split="development_tune")

    def test_locked_test_is_allowed_only_with_exact_guard(self):
        records = [build_page_record("doc-a", page, "text") for page in range(1, 11)]
        row = {"pilot_id": "p1", "question_id": "q1", "doc_id": "doc-a", "question": "What text?"}
        with patch.dict(os.environ, {LOCKED_TEST_ENV: LOCKED_TEST_ACK}, clear=True):
            result = build_retrieval_candidates(
                [row], {"doc-a": records}, FakeEncoder(), split="locked_test"
            )
        self.assertEqual(result["split"], "locked_test")
        self.assertFalse(result["contains_gold_or_answer_labels"])


if __name__ == "__main__":
    unittest.main()
