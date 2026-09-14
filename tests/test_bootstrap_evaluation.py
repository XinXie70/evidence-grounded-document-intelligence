import unittest

from egdi.bootstrap_evaluation import bootstrap_evaluation, evaluation_metrics


def row(doc, *, task, grounded, answered, eligible=True, any_hit=True, complete=False):
    return {
        "doc_id": doc,
        "task_correct": task,
        "grounded_correct": grounded,
        "prediction_status": "answerable" if answered else "insufficient_evidence",
        "page_diagnostics": {
            "retrieval_scoring_eligible": eligible,
            "any_evidence_recall": any_hit if eligible else None,
            "complete_evidence_recall": complete if eligible else None,
        },
    }


class BootstrapEvaluationTests(unittest.TestCase):
    def test_point_metrics_keep_answer_and_retrieval_denominators_separate(self):
        rows = [
            row("a", task=True, grounded=True, answered=True, complete=True),
            row("a", task=False, grounded=False, answered=False, any_hit=False),
            row("b", task=True, grounded=True, answered=False, eligible=False),
        ]
        metrics = evaluation_metrics(rows)
        self.assertEqual(metrics["task_accuracy"], 2 / 3)
        self.assertEqual(metrics["coverage"], 1 / 3)
        self.assertEqual(metrics["selective_task_accuracy"], 1.0)
        self.assertEqual(metrics["any_evidence_recall"], 0.5)
        self.assertEqual(metrics["complete_evidence_recall"], 0.5)

    def test_bootstrap_is_deterministic_and_reports_cluster_sensitivity(self):
        rows = [
            row("a", task=True, grounded=True, answered=True, complete=True),
            row("a", task=True, grounded=False, answered=True, complete=False),
            row("b", task=False, grounded=False, answered=False, any_hit=False),
        ]
        first = bootstrap_evaluation(rows, replicates=200, seed=7)
        second = bootstrap_evaluation(rows, replicates=200, seed=7)
        self.assertEqual(first, second)
        self.assertEqual(first["document_count"], 2)
        interval = first["document_clustered_bootstrap_95_ci"]["task_accuracy"]
        self.assertLessEqual(interval["lower"], first["point_estimates"]["task_accuracy"])
        self.assertGreaterEqual(interval["upper"], first["point_estimates"]["task_accuracy"])

    def test_rejects_invalid_input(self):
        with self.assertRaises(ValueError):
            bootstrap_evaluation([], replicates=10)
        with self.assertRaises(ValueError):
            bootstrap_evaluation([row("a", task=True, grounded=True, answered=True)], replicates=0)


if __name__ == "__main__":
    unittest.main()
