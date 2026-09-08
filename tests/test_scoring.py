import math
import unittest

from egdi.scoring import aggregate_page_scores, score_evidence_pages, scoring_eligibility


class EvidencePageScorerTests(unittest.TestCase):
    def test_perfect_multi_page_at_k(self):
        score = score_evidence_pages([2, 5], [5, 2, 9], 3)
        self.assertEqual(score.true_positive, 2)
        self.assertEqual(score.any_evidence_recall, 1.0)
        self.assertEqual(score.complete_evidence_recall, 1.0)
        self.assertEqual(score.recall, 1.0)
        self.assertEqual(score.precision, 2 / 3)
        self.assertEqual(score.reciprocal_rank, 1.0)
        self.assertEqual(score.ndcg, 1.0)

    def test_partial_and_rank_sensitive_metrics(self):
        score = score_evidence_pages([2, 5], [9, 2, 8, 5], 3)
        self.assertEqual(score.any_evidence_recall, 1.0)
        self.assertEqual(score.complete_evidence_recall, 0.0)
        self.assertEqual(score.recall, 0.5)
        self.assertEqual(score.precision, 1 / 3)
        self.assertEqual(score.reciprocal_rank, 0.5)
        self.assertAlmostEqual(score.ndcg, (1 / math.log2(3)) / (1 + 1 / math.log2(3)))

    def test_duplicates_are_deduplicated_before_cutoff(self):
        score = score_evidence_pages([2, 5], [2, 2, 5], 2)
        self.assertEqual(score.predicted_count, 2)
        self.assertEqual(score.complete_evidence_recall, 1.0)

    def test_precision_uses_requested_k_when_fewer_predictions(self):
        score = score_evidence_pages([2], [2], 3)
        self.assertEqual(score.precision, 1 / 3)

    def test_rejects_zero_gold_and_invalid_page_ids(self):
        with self.assertRaises(ValueError):
            score_evidence_pages([], [1], 1)
        with self.assertRaises(ValueError):
            score_evidence_pages([1], [0], 1)
        with self.assertRaises(ValueError):
            score_evidence_pages([True], [1], 1)

    def test_macro_and_micro_aggregation(self):
        scores = [
            score_evidence_pages([1, 2], [1], 1),
            score_evidence_pages([3], [4], 1),
        ]
        aggregate = aggregate_page_scores(scores)
        self.assertEqual(aggregate["question_count"], 2)
        self.assertEqual(aggregate["macro"]["recall"], 0.25)
        self.assertEqual(aggregate["micro"]["recall"], 1 / 3)
        self.assertEqual(aggregate["micro"]["precision"], 0.5)

    def test_protocol_eligibility_excludes_unanswerable_and_anomaly(self):
        eligible = {"id": "q", "answer": {"is_answerable": True}, "evidences": [{"page": 1}]}
        self.assertEqual(scoring_eligibility(eligible), (True, None))
        unanswerable = {"id": "u", "answer": {"is_answerable": False}, "evidences": []}
        self.assertEqual(scoring_eligibility(unanswerable), (False, "unanswerable"))
        anomaly = {
            "id": "urnuuidbf633ee6-28ba-460f-b6c6-fcd694f24284::q2",
            "answer": {"is_answerable": True},
            "evidences": [],
        }
        self.assertEqual(
            scoring_eligibility(anomaly), (False, "answerable_zero_evidence_anomaly")
        )


if __name__ == "__main__":
    unittest.main()
