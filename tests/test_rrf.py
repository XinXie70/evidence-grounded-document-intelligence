import unittest

from egdi.rrf import evaluate_rrf_runs, reciprocal_rank_fusion


def question(question_id, gold, retrieved):
    return {
        "question_id": question_id,
        "question": "Which page contains the evidence?",
        "doc_id": "doc-a",
        "gold_pages": gold,
        "retrieved_pages": retrieved,
        "slices": {
            "page_span": "multi" if len(gold) > 1 else "single",
            "gold_text_status": "ok",
            "evidence_type": "text",
            "extract_class": "class-test",
        },
    }


class ReciprocalRankFusionTests(unittest.TestCase):
    def test_shared_page_rises_and_ties_use_page_id(self):
        fused = reciprocal_rank_fusion([[5, 2, 9], [7, 2, 9]], rank_constant=60, top_k=5)
        self.assertEqual([page for page, _ in fused], [2, 9, 5, 7])
        self.assertGreater(fused[0][1], fused[2][1])

    def test_evaluates_fused_ranking_without_using_gold_for_fusion(self):
        left = {
            "split": "development_tune",
            "excluded_question_count": 0,
            "exclusion_reasons": {},
            "per_question": [question("q1", [2], [5, 2, 9])],
        }
        right = {
            "split": "development_tune",
            "per_question": [question("q1", [2], [7, 2, 9])],
        }
        result = evaluate_rrf_runs(left, right, input_depth=3, ks=(1, 3))
        self.assertEqual(result["per_question"][0]["retrieved_pages"][0], 2)
        self.assertEqual(result["aggregate"]["1"]["macro"]["complete_evidence_recall"], 1.0)

    def test_rejects_non_tune_drift_and_short_rankings(self):
        left = {"split": "development_tune", "per_question": [question("q1", [1], [1])]}
        with self.assertRaisesRegex(ValueError, "development_tune"):
            evaluate_rrf_runs({**left, "split": "locked_test"}, left, input_depth=1, ks=(1,))
        drifted = {
            "split": "development_tune",
            "per_question": [question("q1", [2], [1])],
        }
        with self.assertRaisesRegex(ValueError, "metadata drift"):
            evaluate_rrf_runs(left, drifted, input_depth=1, ks=(1,))
        with self.assertRaisesRegex(ValueError, "shorter than input_depth"):
            evaluate_rrf_runs(left, left, input_depth=2, ks=(1,))


if __name__ == "__main__":
    unittest.main()
