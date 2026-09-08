import json
import unittest

from egdi.bm25 import PageBm25Index
from egdi.reliability_pilot_inputs import build_pilot_triplets
from egdi.text import build_page_record


class ReliabilityPilotInputTests(unittest.TestCase):
    def setUp(self):
        self.questions = {
            "doc-a::q1": {
                "id": "doc-a::q1",
                "question": "What is the rare threshold?",
                "pdf": {"doc_id_str": "doc-a"},
                "answer": {"is_answerable": True, "answer_text": "SECRET 18"},
                "evidences": [{"page": 2}],
                "facts": [{"text_description": "SECRET FACT"}],
            },
            "doc-b::q1": {
                "id": "doc-b::q1",
                "question": "What unsupported tax rate is discussed?",
                "pdf": {"doc_id_str": "doc-b"},
                "answer": {"is_answerable": False, "answer_text": ""},
                "evidences": [],
            },
        }
        self.records = {
            "doc-a": [
                build_page_record("doc-a", 1, "ordinary material"),
                build_page_record("doc-a", 2, "rare threshold is eighteen"),
                build_page_record("doc-a", 3, "appendix"),
            ],
            "doc-b": [
                build_page_record("doc-b", 1, "unsupported tax discussion"),
                build_page_record("doc-b", 2, "ordinary material"),
                build_page_record("doc-b", 3, "appendix"),
            ],
        }
        selected = []
        for index, (question_id, question) in enumerate(self.questions.items(), start=1):
            doc_id = question["pdf"]["doc_id_str"]
            pages = [
                hit.page
                for hit in PageBm25Index(self.records[doc_id], k1=1.2, b=0.75).search(
                    question["question"], 3
                )
            ]
            selected.append({
                "pilot_id": f"pilot_{index:02d}",
                "question_id": question_id,
                "doc_id": doc_id,
                "question": question["question"],
                "kind": "answerable" if index == 1 else "unanswerable",
                "bm25_top3_pages": pages,
                "oracle_pages": [2] if index == 1 else [],
            })
        self.selection = {
            "status": "frozen_for_reliability_pilot_v0",
            "split": "development_tune",
            "question_count": 2,
            "questions": selected,
        }

    def test_builds_three_prompt_matched_inputs_without_answer_leakage(self):
        triplets = build_pilot_triplets(
            self.selection,
            self.questions,
            self.records,
            tune_question_ids=set(self.questions),
            k1=1.2,
            b=0.75,
        )

        self.assertEqual(len(triplets), 2)
        self.assertEqual(triplets[0][0], "pilot_01")
        self.assertEqual(triplets[0][1].evidence, ())
        self.assertEqual([page.page for page in triplets[0][3].evidence], [2])
        self.assertEqual(triplets[1][3].evidence, ())
        for _pilot_id, closed, real, oracle in triplets:
            inputs = [item.model_input() for item in (closed, real, oracle)]
            self.assertEqual(len({item["instructions"] for item in inputs}), 1)
            self.assertEqual(len({item["question"] for item in inputs}), 1)
        serialized = json.dumps(
            [item.to_experiment_record() for case in triplets for item in case[1:]]
        )
        self.assertNotIn("SECRET", serialized)
        self.assertNotIn("answer_text", serialized)
        self.assertNotIn('"facts"', serialized)

    def test_rejects_retrieval_and_oracle_drift(self):
        original = self.selection["questions"][0]["bm25_top3_pages"]
        self.selection["questions"][0]["bm25_top3_pages"] = list(reversed(original))
        with self.assertRaisesRegex(ValueError, "recomputed retrieval mismatch"):
            build_pilot_triplets(
                self.selection,
                self.questions,
                self.records,
                tune_question_ids=set(self.questions),
                k1=1.2,
                b=0.75,
            )

        self.selection["questions"][0]["bm25_top3_pages"] = original
        self.selection["questions"][0]["oracle_pages"] = [1]
        with self.assertRaisesRegex(ValueError, "Oracle-page mismatch"):
            build_pilot_triplets(
                self.selection,
                self.questions,
                self.records,
                tune_question_ids=set(self.questions),
                k1=1.2,
                b=0.75,
            )


if __name__ == "__main__":
    unittest.main()
