import unittest

from egdi.visual_retrieval_score import score_visual_rankings


def source_item(number, gold, original, page_span="single"):
    return {
        "question_id": f"q{number}",
        "question": f"question {number}",
        "doc_id": "doc",
        "gold_pages": gold,
        "retrieved_pages": original,
        "slices": {"page_span": page_span},
    }


def blind_item(number, original, visual):
    return {
        "question_id": f"q{number}",
        "doc_id": "doc",
        "original_rrf_pages": original,
        "visual_reranked_pages": visual,
        "visual_scores": list(range(len(visual), 0, -1)),
        "original_rrf_ranks": list(range(1, len(visual) + 1)),
    }


class VisualRetrievalScoreTests(unittest.TestCase):
    def setUp(self):
        original = list(range(1, 11))
        self.rrf = {
            "split": "development_tune",
            "per_question": [source_item(i, [5], original) for i in range(1, 64)],
        }
        self.blind = {
            "split": "development_tune",
            "status": "blind_visual_rankings_frozen_before_scoring",
            "contains_gold_or_answer_labels": False,
            "question_count": 63,
            "rankings": [blind_item(i, original, [5, 1, 2, 3, 4, 6, 7, 8, 9, 10]) for i in range(1, 64)],
        }

    def test_scores_frozen_rankings_and_applies_preregistered_gate(self):
        result = score_visual_rankings(self.blind, self.rrf)
        self.assertEqual(result["question_count"], 63)
        self.assertEqual(
            result["paired_success_counts"]["3"]["complete_evidence_recall"]["net_change_questions"],
            63,
        )
        self.assertTrue(result["keep_drop_gate"]["passed"])
        self.assertEqual(result["keep_drop_gate"]["decision"], "keep_visual_reranker")
        self.assertEqual(
            result["paired_success_counts"]["3"]["complete_evidence_recall"]
            ["paired_outcomes"]["visual_gain"],
            63,
        )
        self.assertEqual(
            result["per_question"][0]["scores"]["3"]["paired_outcome"]
            ["complete_evidence_recall"],
            "visual_gain",
        )

    def test_reports_multi_page_slice_and_rejects_candidate_set_drift(self):
        self.rrf["per_question"][0]["gold_pages"] = [4, 5]
        self.rrf["per_question"][0]["slices"]["page_span"] = "multi"
        result = score_visual_rankings(self.blind, self.rrf)
        self.assertEqual(result["page_span_slices"]["multi"]["question_count"], 1)
        self.blind["rankings"][0]["visual_reranked_pages"][-1] = 99
        with self.assertRaisesRegex(ValueError, "candidate-page set"):
            score_visual_rankings(self.blind, self.rrf)

    def test_rejects_unfrozen_or_mismatched_provenance(self):
        self.blind["status"] = "draft"
        with self.assertRaisesRegex(ValueError, "not marked frozen"):
            score_visual_rankings(self.blind, self.rrf)
        self.blind["status"] = "blind_visual_rankings_frozen_before_scoring"
        self.blind["rankings"][0]["doc_id"] = "wrong"
        with self.assertRaisesRegex(ValueError, "provenance drift"):
            score_visual_rankings(self.blind, self.rrf)


if __name__ == "__main__":
    unittest.main()
