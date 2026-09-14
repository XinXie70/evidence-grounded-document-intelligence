import json
import unittest

from egdi.confidence_features_v1 import (
    attach_postgeneration_confidence_features,
    contains_forbidden_confidence_key,
    extract_retrieval_confidence_features,
)
from egdi.text import build_page_record
from egdi.visual_routing import (
    ROUTE_DOCUMENT_GLOBAL,
    ROUTE_LOCAL_VISUAL,
    ROUTE_SCANNED_DOCUMENT,
    ROUTE_TEXT,
)


class ConfidenceFeaturesV1Tests(unittest.TestCase):
    def setUp(self):
        self.records = [
            build_page_record("doc", page, ("revenue chart 2024 " if page == 2 else f"page {page} text ") * 12)
            for page in range(1, 11)
        ]
        self.base = dict(
            question_id="doc::q1",
            doc_id="doc",
            query="Which chart reports revenue in 2024?",
            records=self.records,
            bm25_pages=[2, 1, 3, 4, 5, 6, 7, 8, 9, 10],
            bm25_scores=[10.0, 5.0, 4.0, 3.0, 2.0, 1.0, 0.9, 0.8, 0.7, 0.6],
            dense_pages=[1, 2, 4, 3, 5, 6, 7, 8, 10, 9],
            rrf_pages=[2, 1, 4, 3, 5, 6, 7, 8, 9, 10],
            rrf_scores=[0.04, 0.03, 0.025, 0.02, 0.018, 0.016, 0.014, 0.012, 0.01, 0.008],
            evidence_pages=[2, 1, 4],
            route=ROUTE_TEXT,
        )

    def test_extracts_agreement_coverage_margin_and_text_health(self):
        result = extract_retrieval_confidence_features(**self.base)
        self.assertEqual(result["bm25_dense_agreement_at_3"], 2 / 3)
        self.assertEqual(result["bm25_dense_agreement_at_5"], 1.0)
        self.assertEqual(result["final_top3_dual_support_rate"], 1.0)
        self.assertGreater(result["query_token_coverage_ratio"], 0)
        self.assertAlmostEqual(result["bm25_normalized_top1_top2_margin"], 0.5)
        self.assertEqual(result["evidence_extraction_status_counts"]["ok"], 3)
        self.assertIsNone(result["visual_normalized_top1_top2_margin"])
        self.assertFalse(contains_forbidden_confidence_key(result))
        self.assertNotIn("Which chart", json.dumps(result))

    def test_visual_route_records_margin_and_displacement(self):
        values = dict(self.base)
        values.update(
            route=ROUTE_LOCAL_VISUAL,
            evidence_pages=[4, 2, 1],
            visual_pages=[4, 2, 1, 3, 5, 6, 7, 8, 9, 10],
            visual_scores=[20.0, 10.0, 9.0, 8.0, 7.0, 6.0, 5.0, 4.0, 3.0, 2.0],
        )
        result = extract_retrieval_confidence_features(**values)
        self.assertEqual(result["visual_normalized_top1_top2_margin"], 0.5)
        self.assertEqual(result["visual_top3_rrf_retention_rate"], 1.0)
        self.assertGreater(result["visual_mean_absolute_rank_displacement"], 0)

    def test_postgeneration_features_hide_answer_and_apply_hard_gate(self):
        retrieval = extract_retrieval_confidence_features(**self.base)
        reasoning = {
            "question_id": "doc::q1",
            "output": {"answer": "secret answer", "cited_pages": [2], "status": "answerable"},
            "validation": {"valid": True, "citations_within_supplied_context": True},
        }
        result = attach_postgeneration_confidence_features(retrieval, reasoning)
        self.assertTrue(result["policy_eligible"])
        self.assertEqual(result["citation_to_evidence_ratio"], 1 / 3)
        self.assertNotIn("secret answer", json.dumps(result))
        reasoning["validation"]["valid"] = False
        self.assertFalse(attach_postgeneration_confidence_features(retrieval, reasoning)["policy_eligible"])

    def test_scanned_route_uses_ocr_bm25_without_fabricated_dense_signals(self):
        values = dict(self.base)
        values.update(
            route=ROUTE_SCANNED_DOCUMENT,
            evidence_pages=[1, 2, 3],
            dense_pages=None,
            rrf_pages=None,
            rrf_scores=None,
        )
        result = extract_retrieval_confidence_features(**values)
        self.assertIsNone(result["bm25_dense_agreement_at_10"])
        self.assertIsNone(result["rrf_top1_score"])
        self.assertEqual(result["evidence_page_count"], 3)

    def test_document_global_route_has_no_fake_ranking_or_evidence(self):
        values = dict(self.base)
        values.update(
            route=ROUTE_DOCUMENT_GLOBAL,
            evidence_pages=[],
            bm25_pages=None,
            bm25_scores=None,
            dense_pages=None,
            rrf_pages=None,
            rrf_scores=None,
        )
        result = extract_retrieval_confidence_features(**values)
        self.assertEqual(result["evidence_page_count"], 0)
        self.assertIsNone(result["bm25_top1_score"])
        self.assertEqual(result["query_token_coverage_ratio"], 0.0)

    def test_rejects_provenance_visual_drift_and_forbidden_fields(self):
        bad = dict(self.base, evidence_pages=[99])
        with self.assertRaisesRegex(ValueError, "document corpus"):
            extract_retrieval_confidence_features(**bad)
        bad = dict(self.base, route=ROUTE_LOCAL_VISUAL)
        with self.assertRaisesRegex(ValueError, "visual_pages"):
            extract_retrieval_confidence_features(**bad)
        bad = dict(self.base, rrf_scores=[0.01, 0.02] + self.base["rrf_scores"][2:])
        with self.assertRaisesRegex(ValueError, "descending"):
            extract_retrieval_confidence_features(**bad)
        self.assertTrue(contains_forbidden_confidence_key({"nested": {"gold_pages": [2]}}))


if __name__ == "__main__":
    unittest.main()
