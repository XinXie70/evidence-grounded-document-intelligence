import tempfile
import unittest
from pathlib import Path

from egdi.calibration_score import _page_diagnostics, build_calibration_audit
from egdi.io import sha256_file, write_json


class CalibrationScoreTests(unittest.TestCase):
    def test_joins_local_and_judged_labels_and_scores_pages(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            semantic_input = root / "semantic-input.json"
            support_input = root / "support-input.json"
            write_json(semantic_input, {"x": 1})
            write_json(support_input, {"x": 2})
            write_json(root / "semantic" / "p1" / "semantic.json", {
                "question_id": "d::q1", "judge_type": "semantic",
                "input_sha256": sha256_file(semantic_input), "response_id": "rs",
                "judgment": {"consistent": True, "reason": "same meaning"},
            })
            write_json(root / "support" / "p1" / "support.json", {
                "question_id": "d::q1", "judge_type": "support",
                "input_sha256": sha256_file(support_input), "response_id": "rp",
                "judgment": {"supported": False, "reason": "missing support"},
            })
            cases = [{
                "pilot_id": "p1", "question_id": "d::q1", "doc_id": "d", "route": "r0_text",
                "gold_is_answerable": True, "gold_pages": [1, 2],
                "prediction": {"status": "answerable", "cited_pages": [2, 3]},
                "semantic": {"mode": "judge"},
                "semantic_input": {"sha256": sha256_file(semantic_input)},
                "support": {"mode": "judge"},
                "support_input": {"sha256": sha256_file(support_input)},
            }, {
                "pilot_id": "p2", "question_id": "d::q2", "doc_id": "d", "route": "r0_text",
                "gold_is_answerable": False, "gold_pages": [4],
                "prediction": {"status": "insufficient_evidence", "cited_pages": []},
                "semantic": {"mode": "local", "task_correct": True, "rule": "abstained"},
                "support": {"mode": "local", "evidence_supported": True, "rule": "no claim"},
            }]
            result = build_calibration_audit(
                {"split": "development_calibration", "case_count": 2, "cases": cases},
                semantic_dir=root / "semantic", support_dir=root / "support",
            )
            self.assertEqual(result["task_correct_count"], 2)
            self.assertEqual(result["grounded_correct_count"], 1)
            self.assertEqual(result["invalid_prediction_count"], 0)
            self.assertEqual(result["operational_failure_count"], 0)
            self.assertEqual(result["cases"][0]["page_diagnostics"]["page_f1"], 0.5)
            self.assertIsNone(result["cases"][1]["page_diagnostics"]["page_recall"])

    def test_answerable_zero_evidence_anomaly_is_excluded_only_from_retrieval(self):
        diagnostics = _page_diagnostics({
            "question_id": "urnuuidbf633ee6-28ba-460f-b6c6-fcd694f24284::q2",
            "gold_is_answerable": True,
            "gold_pages": [],
            "prediction": {"cited_pages": []},
        })
        self.assertFalse(diagnostics["retrieval_scoring_eligible"])
        self.assertEqual(
            diagnostics["retrieval_exclusion_reason"],
            "answerable_zero_evidence_anomaly",
        )


if __name__ == "__main__":
    unittest.main()
