import json
import unittest

from egdi.confidence_features import (
    _contains_forbidden_key,
    build_tune_feature_artifact,
    extract_query_features,
)
from egdi.text import build_page_record


class ConfidenceFeatureTests(unittest.TestCase):
    def setUp(self):
        self.records = [
            build_page_record("doc-a", 1, "alpha beta " * 30),
            build_page_record("doc-a", 2, "alpha " * 30),
            build_page_record("doc-a", 3, "noise " * 30),
        ]

    def test_extracts_rank_scores_margins_and_statuses(self):
        result = extract_query_features(
            "doc-a::q1", "doc-a", "alpha beta", self.records
        )

        self.assertEqual(result["top3_pages"], [1, 2, 3])
        self.assertGreater(result["bm25_top1_score"], result["bm25_top2_score"])
        self.assertGreater(result["bm25_top2_score"], result["bm25_top3_score"])
        self.assertAlmostEqual(
            result["bm25_top1_top2_margin"],
            result["bm25_top1_score"] - result["bm25_top2_score"],
        )
        self.assertEqual(result["bm25_positive_page_count"], 2)
        self.assertEqual(result["query_token_count"], 2)
        self.assertEqual(result["query_unique_token_count"], 2)
        self.assertEqual(
            result["top3_extraction_status_counts"],
            {"ok": 3, "low_text": 0, "text_layer_missing": 0},
        )

    def test_feature_artifact_excludes_question_and_gold_fields(self):
        questions = [
            {
                "id": "doc-a::q1",
                "question": "alpha beta",
                "pdf": {"doc_id_str": "doc-a"},
                "answer": {"answer_text": "secret", "is_answerable": True},
                "evidences": [{"page": 1}],
                "facts": [{"text_description": "secret fact"}],
            }
        ]

        artifact = build_tune_feature_artifact(
            questions, {"doc-a": self.records}, k1=1.2, b=0.75
        )
        serialized = json.dumps(artifact)

        self.assertEqual(artifact["question_count"], 1)
        self.assertFalse(artifact["contains_gold_or_answer_labels"])
        self.assertNotIn("alpha beta", serialized)
        self.assertNotIn("secret", serialized)
        self.assertFalse(_contains_forbidden_key(artifact))

    def test_rejects_invalid_query_document_and_short_corpus(self):
        with self.assertRaisesRegex(ValueError, "BM25 token"):
            extract_query_features("q1", "doc-a", "___", self.records)
        with self.assertRaisesRegex(ValueError, "match doc_id"):
            extract_query_features("q1", "other", "alpha", self.records)
        with self.assertRaisesRegex(ValueError, "at least three"):
            extract_query_features("q1", "doc-a", "alpha", self.records[:2])


if __name__ == "__main__":
    unittest.main()
