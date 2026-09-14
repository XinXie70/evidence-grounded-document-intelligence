import unittest

from egdi.v1_calibration_freeze import build_threshold_freeze


class V1CalibrationFreezeTests(unittest.TestCase):
    def test_selects_predeclared_total_question_coverage_point(self):
        evaluation = {
            "split": "development_calibration",
            "status": "development_calibration_confidence_gate_evaluated",
            "risk_coverage": {
                "maximum_coverage": 0.55,
                "operating_points": {
                    "1.0": {"confidence_threshold": 0.1, "coverage": 0.55},
                    "0.9": {"confidence_threshold": 0.1, "coverage": 0.55},
                    "0.8": {"confidence_threshold": 0.1, "coverage": 0.55},
                    "0.6": {"confidence_threshold": 0.1, "coverage": 0.55},
                },
            },
        }
        human = {"status": "complete", "case_count": 50}
        result = build_threshold_freeze(evaluation, human, target_coverage=0.6)
        self.assertEqual(result["confidence_threshold"], 0.1)
        self.assertEqual(result["selected_target_coverage"], 0.6)
        self.assertFalse(result["diagnostic"]["requested_target_attainable"])
        self.assertFalse(result["locked_test_accessed"])

    def test_rejects_invalid_target_or_incomplete_audit(self):
        evaluation = {
            "split": "development_calibration",
            "status": "development_calibration_confidence_gate_evaluated",
            "risk_coverage": {
                "maximum_coverage": 0.8,
                "operating_points": {
                    "1.0": {"confidence_threshold": 0.1},
                    "0.9": {"confidence_threshold": 0.2},
                    "0.8": {"confidence_threshold": 0.3},
                    "0.6": {"confidence_threshold": 0.4},
                },
            },
        }
        with self.assertRaises(ValueError):
            build_threshold_freeze(evaluation, {"status": "complete", "case_count": 50}, target_coverage=0.7)
        with self.assertRaises(ValueError):
            build_threshold_freeze(evaluation, {"status": "complete", "case_count": 49}, target_coverage=1.0)


if __name__ == "__main__":
    unittest.main()
