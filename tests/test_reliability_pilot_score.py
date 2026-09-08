import copy
import tempfile
import unittest
from pathlib import Path

from egdi.io import write_json
from egdi.reliability_pilot_score import CONDITIONS, score_completed_audit


class ReliabilityPilotScoreTests(unittest.TestCase):
    def setUp(self):
        answerable_conditions = {
            "closed_book": {
                "response_status": "insufficient_evidence",
                "answer": None,
                "evidence_sufficient": False,
                "answer_correct": None,
                "grounded_correct": None,
                "outcome": "appropriate_abstention_given_context",
            },
            "real_retrieval": {
                "response_status": "answerable",
                "answer": "18",
                "evidence_sufficient": True,
                "answer_correct": True,
                "grounded_correct": True,
                "outcome": "grounded_success",
            },
            "oracle_page": {
                "response_status": "answerable",
                "answer": "18",
                "evidence_sufficient": True,
                "answer_correct": True,
                "grounded_correct": True,
                "outcome": "grounded_success",
            },
        }
        unanswerable_conditions = {
            condition: {
                "response_status": "insufficient_evidence",
                "answer": None,
                "evidence_sufficient": None,
                "answer_correct": None,
                "grounded_correct": None,
                "outcome": "correct_abstention",
            }
            for condition in CONDITIONS
        }
        unanswerable_conditions["real_retrieval"]["response_contract_valid"] = False
        self.audit = {
            "status": "complete",
            "completed_pilot_count": 2,
            "pending_pilot_count": 0,
            "pilots": [
                {
                    "pilot_id": "pilot_01",
                    "question_id": "doc-a::q1",
                    "benchmark_is_answerable": True,
                    "user_confirmed": True,
                    "conditions": answerable_conditions,
                },
                {
                    "pilot_id": "pilot_02",
                    "question_id": "doc-b::q1",
                    "benchmark_is_answerable": False,
                    "user_confirmed": True,
                    "conditions": unanswerable_conditions,
                },
            ],
        }

    def _write_results(self, root: Path):
        for pilot in self.audit["pilots"]:
            for condition, reviewed in pilot["conditions"].items():
                valid = not (
                    pilot["pilot_id"] == "pilot_02" and condition == "real_retrieval"
                )
                write_json(
                    root / pilot["pilot_id"] / f"{condition}.json",
                    {
                        "question_id": pilot["question_id"],
                        "condition": condition,
                        "output": {
                            "status": reviewed["response_status"],
                            "answer": reviewed["answer"],
                        },
                        "validation": {"valid": valid},
                    },
                )

    def test_scores_semantics_and_contract_compliance_separately(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_results(root)

            scored = score_completed_audit(self.audit, root)

            c1 = scored["conditions"]["real_retrieval"]
            self.assertEqual(c1["semantic_metrics"]["benchmark_task_accuracy"], 1.0)
            self.assertEqual(c1["response_contract"]["valid_rate"], 0.5)
            self.assertEqual(c1["response_contract"]["invalid_pilot_ids"], ["pilot_02"])
            self.assertEqual(
                c1["supplemental_contract_adjusted_metrics"]["benchmark_task_accuracy"],
                0.5,
            )

    def test_rejects_transcription_and_outcome_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_results(root)
            changed = copy.deepcopy(self.audit)
            changed["pilots"][0]["conditions"]["real_retrieval"]["answer"] = "19"
            with self.assertRaisesRegex(ValueError, "audited answer differs"):
                score_completed_audit(changed, root)

            changed = copy.deepcopy(self.audit)
            changed["pilots"][0]["conditions"]["real_retrieval"]["outcome"] = "incorrect_answer"
            with self.assertRaisesRegex(ValueError, "audited outcome is inconsistent"):
                score_completed_audit(changed, root)


if __name__ == "__main__":
    unittest.main()
