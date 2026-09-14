import unittest

from egdi.selective_evaluation import evaluate_risk_coverage


class SelectiveEvaluationTests(unittest.TestCase):
    def test_curve_risk_and_grounded_risk_are_separate(self):
        result = evaluate_risk_coverage(
            [
                {"question_id": "q2", "confidence": 0.8, "policy_eligible": True,
                 "task_correct": True, "grounded_correct": False},
                {"question_id": "q1", "confidence": 0.9, "policy_eligible": True,
                 "task_correct": True, "grounded_correct": True},
                {"question_id": "q3", "confidence": 0.7, "policy_eligible": True,
                 "task_correct": False, "grounded_correct": False},
                {"question_id": "q4", "confidence": 0.1, "policy_eligible": False,
                 "task_correct": True, "grounded_correct": True},
            ],
            target_coverages=(1.0, 0.5),
        )
        self.assertEqual([item["question_id"] for item in result["curve"]], ["q1", "q2", "q3"])
        self.assertEqual(result["maximum_coverage"], 0.75)
        self.assertEqual(result["curve"][1]["selective_risk"], 0.0)
        self.assertEqual(result["curve"][1]["grounded_selective_risk"], 0.5)
        self.assertAlmostEqual(result["curve"][2]["selective_risk"], 1 / 3)
        self.assertAlmostEqual(result["aurc_over_eligible_prefixes"], 1 / 9)

    def test_operating_points_do_not_split_confidence_ties(self):
        result = evaluate_risk_coverage(
            [
                {"question_id": "q1", "confidence": 1.0, "policy_eligible": True,
                 "task_correct": True, "grounded_correct": True},
                {"question_id": "q3", "confidence": 0.5, "policy_eligible": True,
                 "task_correct": False, "grounded_correct": False},
                {"question_id": "q2", "confidence": 0.5, "policy_eligible": True,
                 "task_correct": True, "grounded_correct": True},
                {"question_id": "q4", "confidence": 0.2, "policy_eligible": True,
                 "task_correct": True, "grounded_correct": True},
            ],
            target_coverages=(1.0, 0.6, 0.2),
        )
        self.assertEqual(result["operating_points"]["0.6"]["answered_count"], 1)
        self.assertEqual(result["operating_points"]["0.6"]["confidence_threshold"], 1.0)
        self.assertEqual(result["operating_points"]["0.2"]["answered_count"], 0)
        self.assertEqual(
            result["answer_retention_operating_points"]["0.6"]["answered_count"], 1
        )
        self.assertEqual(
            result["answer_retention_operating_points"]["1.0"]["answered_count"], 4
        )
        self.assertEqual([x["question_id"] for x in result["curve"][1:3]], ["q2", "q3"])

    def test_rejects_invalid_records_targets_and_grounding(self):
        valid = [{"question_id": "q", "confidence": 1.0, "policy_eligible": True,
                  "task_correct": True, "grounded_correct": True}]
        with self.assertRaisesRegex(ValueError, "at least one"):
            evaluate_risk_coverage([])
        with self.assertRaisesRegex(ValueError, "unique, decreasing"):
            evaluate_risk_coverage(valid, target_coverages=(0.5, 0.9))
        invalid = [{**valid[0], "task_correct": False}]
        with self.assertRaisesRegex(ValueError, "cannot be true"):
            evaluate_risk_coverage(invalid)


if __name__ == "__main__":
    unittest.main()
