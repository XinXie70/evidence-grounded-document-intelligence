import unittest

from egdi.selective_decision import apply_selective_decision


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


def threshold(value=0.5):
    return {
        "status": "protocol_corrected_and_frozen_before_locked_test",
        "split_used_for_threshold_selection": "development_calibration",
        "locked_test_accessed": False,
        "confidence_threshold": value,
    }


def result(status="answerable"):
    answered = status == "answerable"
    return {
        "question_id": "q1",
        "evidence_pages": [2, 3],
        "output": {
            "answer": "supported answer" if answered else None,
            "cited_pages": [2] if answered else [],
            "status": status,
        },
        "validation": {
            "valid": True,
            "citations_within_supplied_context": True,
            "errors": [],
        },
    }


def features(*, eligible=True, coverage=1.0):
    return {
        "question_id": "q1",
        "route": "r2_scanned_document",
        "query_token_coverage_ratio": coverage,
        "citation_to_evidence_ratio": 0.5 if eligible else 0.0,
        "bm25_dense_agreement_at_10": None,
        "policy_eligible": eligible,
    }


class SelectiveDecisionTests(unittest.TestCase):
    def test_retains_eligible_answer_at_threshold(self):
        output = apply_selective_decision(result(), features(), policy(), threshold(0.5))
        self.assertEqual(output["output"]["answer"], "supported answer")
        self.assertEqual(output["selective_decision"]["action"], "retain_answer")

    def test_converts_low_confidence_answer_to_abstention(self):
        output = apply_selective_decision(result(), features(coverage=0.0), policy(), threshold(0.9))
        self.assertEqual(
            output["output"],
            {"answer": None, "cited_pages": [], "status": "insufficient_evidence"},
        )
        self.assertTrue(output["validation"]["valid"])
        self.assertEqual(output["selective_decision"]["reason"], "below_confidence_threshold")

    def test_preserves_existing_abstention_as_ineligible(self):
        output = apply_selective_decision(
            result("insufficient_evidence"), features(eligible=False), policy(), threshold()
        )
        self.assertEqual(output["selective_decision"]["reason"], "ineligible")
        self.assertEqual(output["output"]["status"], "insufficient_evidence")

    def test_rejects_identity_or_eligibility_drift(self):
        with self.assertRaisesRegex(ValueError, "do not match"):
            apply_selective_decision(result(), {**features(), "question_id": "q2"}, policy(), threshold())
        with self.assertRaisesRegex(ValueError, "eligibility"):
            apply_selective_decision(result(), features(eligible=False), policy(), threshold())

    def test_rejects_threshold_created_after_locked_test_access(self):
        bad = {**threshold(), "locked_test_accessed": True}
        with self.assertRaisesRegex(ValueError, "predate"):
            apply_selective_decision(result(), features(), policy(), bad)


if __name__ == "__main__":
    unittest.main()
