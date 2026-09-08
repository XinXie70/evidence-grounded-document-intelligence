import json
import unittest

from egdi.reasoning_smoke import build_smoke_cases, build_smoke_triplet_cases
from egdi.text import build_page_record


class ReasoningSmokeTests(unittest.TestCase):
    def setUp(self):
        self.questions = {
            "doc-a::q1": {
                "id": "doc-a::q1",
                "question": "What is the rare threshold?",
                "answer": {"answer_text": "18 SECRET", "is_answerable": True},
                "pdf": {"doc_id_str": "doc-a"},
                "evidences": [{"page": 2, "element_type": "text"}],
            },
            "doc-b::q1": {
                "id": "doc-b::q1",
                "question": "What unsupported tax rate is discussed?",
                "answer": {"answer_text": "", "is_answerable": False},
                "pdf": {"doc_id_str": "doc-b"},
                "evidences": [{"page": 1, "element_type": "text"}],
            },
        }
        self.records = {
            "doc-a": [
                build_page_record("doc-a", 1, "ordinary material"),
                build_page_record("doc-a", 2, "rare threshold is eighteen"),
            ],
            "doc-b": [
                build_page_record("doc-b", 1, "unsupported tax rate discussion"),
                build_page_record("doc-b", 2, "other material"),
            ],
        }
        self.selection = {
            "status": "frozen_for_smoke_v1",
            "split": "development_tune",
            "top_k": 1,
            "question_count": 2,
            "questions": [
                {
                    "case_id": "smoke_01",
                    "question_id": "doc-a::q1",
                    "doc_id": "doc-a",
                    "question": "What is the rare threshold?",
                    "answerability": "answerable",
                    "gold_pages": [2],
                    "real_retrieval_top3_pages": [2],
                },
                {
                    "case_id": "smoke_02",
                    "question_id": "doc-b::q1",
                    "doc_id": "doc-b",
                    "question": "What unsupported tax rate is discussed?",
                    "answerability": "unanswerable",
                    "gold_pages": [],
                    "real_retrieval_top3_pages": [1],
                },
            ],
        }

    def test_builds_answerable_and_unanswerable_pairs_without_answer_leakage(self):
        cases = build_smoke_cases(
            self.selection,
            self.questions,
            self.records,
            tune_question_ids=set(self.questions),
            k1=1.2,
            b=0.75,
        )

        self.assertEqual([case[0] for case in cases], ["smoke_01", "smoke_02"])
        self.assertEqual([page.page for page in cases[0][1].evidence], [2])
        self.assertEqual([page.page for page in cases[0][2].evidence], [2])
        self.assertEqual([page.page for page in cases[1][1].evidence], [1])
        self.assertEqual(cases[1][2].evidence, ())
        serialized = json.dumps(
            [item.to_experiment_record() for case in cases for item in case[1:]]
        )
        self.assertNotIn("SECRET", serialized)
        self.assertNotIn("answer_text", serialized)

    def test_rejects_retrieval_or_split_drift(self):
        self.selection["questions"][0]["real_retrieval_top3_pages"] = [1]
        with self.assertRaisesRegex(ValueError, "recomputed retrieval mismatch"):
            build_smoke_cases(
                self.selection,
                self.questions,
                self.records,
                tune_question_ids=set(self.questions),
                k1=1.2,
                b=0.75,
            )

        self.selection["questions"][0]["real_retrieval_top3_pages"] = [2]
        with self.assertRaisesRegex(ValueError, "not in development_tune"):
            build_smoke_cases(
                self.selection,
                self.questions,
                self.records,
                tune_question_ids={"doc-b::q1"},
                k1=1.2,
                b=0.75,
            )

    def test_builds_prompt_matched_triplets_without_gold_answer_leakage(self):
        cases = build_smoke_triplet_cases(
            self.selection,
            self.questions,
            self.records,
            tune_question_ids=set(self.questions),
            k1=1.2,
            b=0.75,
        )

        self.assertEqual(len(cases), 2)
        for _case_id, closed, real, oracle in cases:
            model_inputs = [item.model_input() for item in (closed, real, oracle)]
            self.assertEqual(closed.evidence, ())
            self.assertEqual(len({item["instructions"] for item in model_inputs}), 1)
            self.assertEqual(len({item["question"] for item in model_inputs}), 1)
            self.assertEqual(
                model_inputs[0]["response_schema"], model_inputs[1]["response_schema"]
            )
            self.assertEqual(
                model_inputs[1]["response_schema"], model_inputs[2]["response_schema"]
            )
        serialized = json.dumps(
            [item.to_experiment_record() for case in cases for item in case[1:]]
        )
        self.assertNotIn("SECRET", serialized)
        self.assertNotIn("answer_text", serialized)

if __name__ == "__main__":
    unittest.main()
