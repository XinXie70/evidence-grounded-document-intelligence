import unittest

from egdi.comparison_generalization_score import score_probe


class ComparisonGeneralizationScoreTests(unittest.TestCase):
    def test_computes_gold_difference_when_answer_lists_two_operands(self):
        from egdi.comparison_generalization_score import _gold_number

        self.assertEqual(
            _gold_number("There are 100 pins on the target and 4 pins on the oscillator."),
            96,
        )

    def test_scores_answer_and_value_pages_posthoc(self):
        probe = {
            "leakage_controls": {"uses_gold_answer": False, "uses_gold_evidence_pages": False},
            "cases": [{"case_id": "x", "question_id": "doc::q1", "question": "Q",
                       "status": "success", "selected_facts": [
                           {"total_page": 7}, {"total_page": 5}],
                       "deterministic_comparison": {"magnitude": "1728"}}],
        }
        benchmark = [{"id": "doc::q1", "split": "dev", "question": "Q",
                      "answer": {"answer_text": "1,728"},
                      "evidences": [{"page": 5}, {"page": 7}]}]
        result = score_probe(probe, benchmark)
        self.assertEqual(result["summary"]["answer_exact_match_rate"], 1.0)
        self.assertEqual(result["summary"]["complete_evidence_match_rate"], 1.0)

    def test_rejects_label_leakage_and_question_drift(self):
        probe = {"leakage_controls": {"uses_gold_answer": True,
                                      "uses_gold_evidence_pages": False}, "cases": []}
        with self.assertRaisesRegex(ValueError, "label-free"):
            score_probe(probe, [])
        probe = {"leakage_controls": {"uses_gold_answer": False,
                                      "uses_gold_evidence_pages": False},
                 "cases": [{"case_id": "x", "question_id": "doc::q1",
                            "question": "changed", "status": "unsupported"}]}
        benchmark = [{"id": "doc::q1", "split": "dev", "question": "original",
                      "answer": {"answer_text": "1"}, "evidences": []}]
        with self.assertRaisesRegex(ValueError, "drifted"):
            score_probe(probe, benchmark)

    def test_accepts_model_fact_citation_lists(self):
        probe = {"leakage_controls": {"uses_gold_answer": False,
                                      "uses_gold_evidence_pages": False},
                 "cases": [{"case_id": "x", "question_id": "doc::q1", "question": "Q",
                            "status": "success", "selected_facts": [
                                {"cited_pages": [24]}, {"cited_pages": [20]}],
                            "deterministic_comparison": {"magnitude": "19200"}}]}
        benchmark = [{"id": "doc::q1", "split": "dev", "question": "Q",
                      "answer": {"answer_text": "19200"},
                      "evidences": [{"page": 20}, {"page": 24}]}]
        result = score_probe(probe, benchmark)
        self.assertEqual(result["summary"]["complete_evidence_match_rate"], 1.0)

    def test_extracts_explicit_difference_from_explanatory_gold_answer(self):
        probe = {"leakage_controls": {"uses_gold_answer": False,
                                      "uses_gold_evidence_pages": False},
                 "cases": [{"case_id": "x", "question_id": "doc::q1", "question": "Q",
                            "status": "success", "selected_facts": [
                                {"cited_pages": [24]}, {"cited_pages": [20]}],
                            "deterministic_comparison": {"magnitude": "19200"}}]}
        benchmark = [{"id": "doc::q1", "split": "dev", "question": "Q",
                      "answer": {"answer_text": (
                          "The rates are 38400 and 57600; the difference is calculated as 19200.")},
                      "evidences": [{"page": 20}, {"page": 24}]}]
        self.assertEqual(score_probe(probe, benchmark)["summary"]["answer_exact_match_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
