import unittest

from egdi.reliability import (
    aggregate_selective_metrics,
    classify_reliability_outcome,
)


class ReliabilityOutcomeTests(unittest.TestCase):
    def test_distinguishes_appropriate_and_over_abstention(self):
        appropriate = classify_reliability_outcome(
            {
                "question_id": "q1",
                "benchmark_is_answerable": True,
                "evidence_sufficient": False,
                "response_status": "insufficient_evidence",
                "answer": None,
            }
        )
        over = classify_reliability_outcome(
            {
                "question_id": "q2",
                "benchmark_is_answerable": True,
                "evidence_sufficient": True,
                "response_status": "insufficient_evidence",
                "answer": None,
            }
        )

        self.assertEqual(appropriate["outcome"], "appropriate_abstention_given_context")
        self.assertTrue(appropriate["contextual_reliability_correct"])
        self.assertFalse(appropriate["benchmark_task_correct"])
        self.assertEqual(over["outcome"], "over_abstention")
        self.assertFalse(over["contextual_reliability_correct"])

    def test_separates_answer_correctness_from_grounding(self):
        result = classify_reliability_outcome(
            {
                "question_id": "q1",
                "benchmark_is_answerable": True,
                "evidence_sufficient": True,
                "response_status": "answerable",
                "answer": "4",
                "answer_correct": True,
                "grounded_correct": False,
            }
        )

        self.assertEqual(result["outcome"], "correct_answer_incomplete_grounding")
        self.assertTrue(result["benchmark_task_correct"])
        self.assertFalse(result["strict_grounded_task_correct"])

    def test_unanswerable_answer_and_abstention(self):
        correct = classify_reliability_outcome(
            {
                "question_id": "q1",
                "benchmark_is_answerable": False,
                "response_status": "insufficient_evidence",
                "answer": None,
            }
        )
        false_answer = classify_reliability_outcome(
            {
                "question_id": "q2",
                "benchmark_is_answerable": False,
                "response_status": "answerable",
                "answer": "unsupported",
                "answer_correct": False,
                "grounded_correct": False,
            }
        )

        self.assertEqual(correct["outcome"], "correct_abstention")
        self.assertEqual(false_answer["outcome"], "false_answer_on_unanswerable")

    def test_rejects_inconsistent_records(self):
        with self.assertRaisesRegex(ValueError, "answer=null"):
            classify_reliability_outcome(
                {
                    "question_id": "q1",
                    "benchmark_is_answerable": True,
                    "evidence_sufficient": False,
                    "response_status": "insufficient_evidence",
                    "answer": "text",
                }
            )
        with self.assertRaisesRegex(ValueError, "cannot be true"):
            classify_reliability_outcome(
                {
                    "question_id": "q2",
                    "benchmark_is_answerable": True,
                    "response_status": "answerable",
                    "answer": "wrong",
                    "answer_correct": False,
                    "grounded_correct": True,
                }
            )


class SelectiveMetricTests(unittest.TestCase):
    def test_aggregates_policy_metrics_and_outcome_counts(self):
        records = [
            {
                "question_id": "grounded",
                "benchmark_is_answerable": True,
                "evidence_sufficient": True,
                "response_status": "answerable",
                "answer": "yes",
                "answer_correct": True,
                "grounded_correct": True,
            },
            {
                "question_id": "incomplete-grounding",
                "benchmark_is_answerable": True,
                "evidence_sufficient": True,
                "response_status": "answerable",
                "answer": "4",
                "answer_correct": True,
                "grounded_correct": False,
            },
            {
                "question_id": "wrong",
                "benchmark_is_answerable": True,
                "evidence_sufficient": True,
                "response_status": "answerable",
                "answer": "wrong",
                "answer_correct": False,
                "grounded_correct": False,
            },
            {
                "question_id": "appropriate-abstain",
                "benchmark_is_answerable": True,
                "evidence_sufficient": False,
                "response_status": "insufficient_evidence",
                "answer": None,
            },
            {
                "question_id": "over-abstain",
                "benchmark_is_answerable": True,
                "evidence_sufficient": True,
                "response_status": "insufficient_evidence",
                "answer": None,
            },
            {
                "question_id": "unanswerable",
                "benchmark_is_answerable": False,
                "response_status": "insufficient_evidence",
                "answer": None,
            },
        ]

        metrics = aggregate_selective_metrics(records)

        self.assertEqual(metrics["question_count"], 6)
        self.assertEqual(metrics["answered_count"], 3)
        self.assertEqual(metrics["coverage"], 0.5)
        self.assertAlmostEqual(metrics["selective_risk"], 1 / 3)
        self.assertAlmostEqual(metrics["grounded_selective_risk"], 2 / 3)
        self.assertAlmostEqual(metrics["benchmark_task_accuracy"], 3 / 6)
        self.assertAlmostEqual(metrics["strict_grounded_task_accuracy"], 2 / 6)
        self.assertAlmostEqual(metrics["contextual_reliability_accuracy"], 3 / 6)
        self.assertEqual(metrics["unanswerable_false_answer_rate"], 0.0)
        self.assertEqual(metrics["answerable_abstention_rate"], 2 / 5)
        self.assertEqual(metrics["over_abstention_rate_on_sufficient_answerable"], 1 / 4)
        self.assertEqual(
            metrics["appropriate_abstention_rate_on_insufficient_context"], 1.0
        )
        self.assertEqual(metrics["outcome_counts"]["grounded_success"], 1)

    def test_rejects_empty_and_duplicate_question_sets(self):
        with self.assertRaisesRegex(ValueError, "at least one"):
            aggregate_selective_metrics([])
        duplicate = {
            "question_id": "q1",
            "benchmark_is_answerable": False,
            "response_status": "insufficient_evidence",
            "answer": None,
        }
        with self.assertRaisesRegex(ValueError, "unique"):
            aggregate_selective_metrics([duplicate, duplicate])


if __name__ == "__main__":
    unittest.main()
