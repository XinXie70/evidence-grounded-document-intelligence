import unittest

from egdi.confidence_policy_v1 import evaluate_artifacts, score_features, validate_policy


def policy():
    return {
        "weights": {
            "route_prior": 0.65,
            "query_token_coverage_ratio": 0.15,
            "citation_to_evidence_ratio": 0.15,
            "bm25_dense_agreement_at_10": 0.05,
        },
        "route_priors": {
            "r0_text": 1 / 3,
            "r1_local_visual": 5 / 6,
            "r2_scanned_document": 3 / 4,
            "r3_document_global": 1 / 2,
        },
        "missing_values": {"bm25_dense_agreement_at_10": 0.5},
    }


def features(question_id="q1"):
    return {
        "question_id": question_id,
        "route": "r2_scanned_document",
        "query_token_coverage_ratio": 0.8,
        "citation_to_evidence_ratio": 0.25,
        "bm25_dense_agreement_at_10": None,
        "policy_eligible": True,
    }


class ConfidencePolicyV1Tests(unittest.TestCase):
    def test_score_uses_frozen_missing_value(self):
        expected = 0.65 * 0.75 + 0.15 * 0.8 + 0.15 * 0.25 + 0.05 * 0.5
        self.assertAlmostEqual(score_features(features(), policy()), expected)

    def test_rejects_forbidden_label_and_invalid_weights(self):
        with self.assertRaisesRegex(ValueError, "forbidden"):
            score_features({**features(), "task_correct": True}, policy())
        bad = policy()
        bad["weights"]["route_prior"] = 0.5
        with self.assertRaisesRegex(ValueError, "sum to one"):
            validate_policy(bad)

    def test_joins_by_question_id_not_list_order(self):
        f1, f2 = features("q1"), {**features("q2"), "route": "r0_text"}
        artifact = {
            "split": "development_calibration",
            "contains_gold_or_answer_labels": False,
            "cases": [
                {"pilot_id": "p1", "question_id": "q1", "features": f1},
                {"pilot_id": "p2", "question_id": "q2", "features": f2},
            ],
        }
        audit = {"split": "development_calibration", "cases": [
            {"question_id": "q2", "task_correct": False, "grounded_correct": False},
            {"question_id": "q1", "task_correct": True, "grounded_correct": True},
        ]}
        result = evaluate_artifacts(artifact, audit, policy())
        self.assertEqual(result["task_correct_count"], 1)
        self.assertEqual(result["split"], "development_calibration")
        self.assertEqual(result["policy_eligible_count"], 2)
        self.assertEqual(result["risk_coverage"]["curve"][0]["question_id"], "q1")


if __name__ == "__main__":
    unittest.main()
