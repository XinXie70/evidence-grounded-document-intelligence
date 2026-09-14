import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from egdi.calibration_judge_inputs import build_inputs


class CalibrationJudgeInputTests(unittest.TestCase):
    def test_local_and_paid_routes_are_separated(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            prediction_dir = root / "predictions"
            input_path = root / "reasoning.json"
            input_path.write_text(json.dumps({"model_input": {"evidence": [{"page": 2, "text": "proof"}]}}))
            cases = []
            benchmark = []
            selection_questions = []
            for index, (gold_answerable, answer, citations) in enumerate(((True, "yes", [2]), (False, None, [])), 1):
                qid, pilot = f"d::q{index}", f"c{index}"
                path = prediction_dir / pilot / "real_retrieval.json"
                path.parent.mkdir(parents=True)
                path.write_text(json.dumps({"question_id": qid, "validation": {"valid": True}, "output": {"answer": answer, "status": "answerable" if answer else "insufficient_evidence", "cited_pages": citations}}))
                selection_questions.append({"question_id": qid, "pilot_id": pilot, "doc_id": "d"})
                benchmark.append({"id": qid, "question": "Q", "answer": {"is_answerable": gold_answerable, "answer_text": "yes"}, "evidences": [{"page": 2}] if gold_answerable else []})
                cases.append({"question_id": qid, "route": "r0_text", "reasoning_input": {"path": str(input_path)}})
            result = build_inputs({"split": "development_calibration", "questions": selection_questions}, benchmark, {"split": "development_calibration", "cases": cases}, prediction_dir, root / "out")
            self.assertEqual(result["semantic_judge_request_count"], 1)
            self.assertEqual(result["support_judge_request_count"], 1)
            self.assertTrue(result["cases"][1]["semantic"]["task_correct"])


if __name__ == "__main__":
    unittest.main()
