import unittest

from egdi.calibration_human_agreement import build_agreement_report


class CalibrationHumanAgreementTests(unittest.TestCase):
    def test_preserves_independent_uncertainty_and_counts_assisted_labels(self):
        worksheet = {
            "split": "development_calibration",
            "assisted_adjudication": {
                "evidence_support_by_audit_number": {"2": False},
            },
            "cases": [
                {"audit_number": 1, "pilot_id": "p1", "question_id": "q1",
                 "human_task_correct": True, "human_evidence_supported": True,
                 "user_confirmed": True},
                {"audit_number": 2, "pilot_id": "p2", "question_id": "q2",
                 "human_task_correct": False, "human_evidence_supported": None,
                 "user_confirmed": True},
                {"audit_number": 3, "pilot_id": "p3", "question_id": "q3",
                 "human_task_correct": True, "human_evidence_supported": False,
                 "user_confirmed": True},
            ],
        }
        automatic = {"cases": [
            {"pilot_id": "p1", "question_id": "q1", "task_correct": True,
             "evidence_supported": True},
            {"pilot_id": "p2", "question_id": "q2", "task_correct": False,
             "evidence_supported": False},
            {"pilot_id": "p3", "question_id": "q3", "task_correct": True,
             "evidence_supported": True},
        ]}
        report = build_agreement_report(worksheet, automatic)
        self.assertEqual(report["independent_human_review"]["task_judge_agreement"]["rate"], 1.0)
        self.assertEqual(report["independent_human_review"]["support_label_coverage"]["total"], 3)
        self.assertEqual(report["independent_human_review"]["support_label_coverage"]["agree"], 2)
        self.assertEqual(report["independent_human_review"]["support_judge_agreement"]["rate"], 0.5)
        self.assertEqual(report["after_user_accepted_assisted_adjudication"]["support_judge_agreement"]["rate"], 2 / 3)
        self.assertEqual(report["assisted_audit_numbers"], [2])


if __name__ == "__main__":
    unittest.main()
