import json
import unittest

from egdi.reasoning_inputs import (
    CLOSED_BOOK,
    ORACLE_PAGE,
    PILOT_INSTRUCTIONS_V1,
    REAL_RETRIEVAL,
    build_reasoning_input,
    build_reasoning_pair,
    build_reasoning_triplet,
)
from egdi.text import build_page_record


class ReasoningInputTests(unittest.TestCase):
    def setUp(self):
        self.records = [
            build_page_record("doc-a", 1, "first page text " * 10),
            build_page_record("doc-a", 2, "gold evidence says eighteen " * 10),
            build_page_record("doc-a", 3, "third page text " * 10),
        ]
        self.question = {
            "id": "doc-a::q1",
            "question": "What is the age threshold?",
            "answer": {
                "answer_text": "18 years old SECRET_GOLD_ANSWER",
                "is_answerable": True,
            },
            "pdf": {"doc_id_str": "doc-a"},
            "evidences": [
                {"page": 2, "element_type": "text"},
                {"page": 2, "element_type": "paragraph_title"},
            ],
        }

    def test_real_retrieval_preserves_ranked_top_k_pages(self):
        built = build_reasoning_input(
            self.question,
            self.records,
            condition=REAL_RETRIEVAL,
            retrieved_pages=[3, 2, 1],
            top_k=2,
        )

        record = built.to_experiment_record()
        self.assertEqual(record["condition"], "real_retrieval")
        self.assertEqual(record["evidence_pages"], [3, 2])
        self.assertEqual(
            [item["page"] for item in record["model_input"]["evidence"]], [3, 2]
        )
        self.assertEqual(
            record["model_input"]["evidence"][1]["text"], self.records[1].text
        )

    def test_oracle_uses_unique_sorted_gold_pages_without_answer_leakage(self):
        built = build_reasoning_input(
            self.question,
            self.records,
            condition=ORACLE_PAGE,
        )
        record = built.to_experiment_record()
        serialized = json.dumps(record, ensure_ascii=False)

        self.assertEqual(record["evidence_pages"], [2])
        self.assertNotIn("SECRET_GOLD_ANSWER", serialized)
        self.assertNotIn("answer_text", serialized)
        self.assertNotIn("is_answerable", serialized)

    def test_pair_has_identical_contract_and_hides_condition_from_model(self):
        real, oracle = build_reasoning_pair(
            self.question, self.records, [3, 2, 1], top_k=2
        )
        real_input = real.model_input()
        oracle_input = oracle.model_input()

        self.assertEqual(real_input["instructions"], oracle_input["instructions"])
        self.assertEqual(real_input["question"], oracle_input["question"])
        self.assertEqual(real_input["response_schema"], oracle_input["response_schema"])
        self.assertNotIn("condition", real_input)
        self.assertNotIn("condition", oracle_input)
        self.assertNotEqual(real_input["evidence"], oracle_input["evidence"])

    def test_unanswerable_oracle_has_empty_context_without_label_leakage(self):
        question = dict(self.question)
        question["answer"] = {"answer_text": "", "is_answerable": False}
        question["evidences"] = [{"page": 1, "element_type": "text"}]

        built = build_reasoning_input(
            question, self.records, condition=ORACLE_PAGE
        ).to_experiment_record()

        self.assertEqual(built["evidence_pages"], [])
        self.assertEqual(built["model_input"]["evidence"], [])
        self.assertNotIn("is_answerable", json.dumps(built))

    def test_triplet_uses_one_prompt_and_closed_book_has_question_only(self):
        closed, real, oracle = build_reasoning_triplet(
            self.question, self.records, [3, 2, 1], top_k=2
        )
        inputs = [item.model_input() for item in (closed, real, oracle)]
        serialized_closed = json.dumps(closed.to_experiment_record())

        self.assertEqual(closed.condition, CLOSED_BOOK)
        self.assertEqual(closed.evidence, ())
        self.assertEqual(closed.to_experiment_record()["evidence_pages"], [])
        self.assertTrue(all(item["instructions"] == PILOT_INSTRUCTIONS_V1 for item in inputs))
        self.assertTrue(all(item["question"] == inputs[0]["question"] for item in inputs))
        self.assertTrue(all(item["response_schema"] == inputs[0]["response_schema"] for item in inputs))
        self.assertNotIn("SECRET_GOLD_ANSWER", serialized_closed)
        self.assertNotIn("is_answerable", serialized_closed)

    def test_closed_book_rejects_retrieval_parameters(self):
        with self.assertRaisesRegex(ValueError, "does not accept"):
            build_reasoning_input(
                self.question,
                (),
                condition=CLOSED_BOOK,
                retrieved_pages=[1],
                top_k=1,
                instructions=PILOT_INSTRUCTIONS_V1,
            )

    def test_rejects_invalid_pages_conditions_and_document_mismatch(self):
        with self.assertRaisesRegex(ValueError, "condition"):
            build_reasoning_input(
                self.question, self.records, condition="unknown"
            )
        with self.assertRaisesRegex(ValueError, "fewer pages"):
            build_reasoning_input(
                self.question,
                self.records,
                condition=REAL_RETRIEVAL,
                retrieved_pages=[1],
                top_k=2,
            )
        with self.assertRaisesRegex(ValueError, "duplicate"):
            build_reasoning_input(
                self.question,
                self.records,
                condition=REAL_RETRIEVAL,
                retrieved_pages=[1, 1],
                top_k=2,
            )
        wrong_records = [build_page_record("doc-b", 1, "wrong document")]
        with self.assertRaisesRegex(ValueError, "different document"):
            build_reasoning_input(
                self.question, wrong_records, condition=ORACLE_PAGE
            )


if __name__ == "__main__":
    unittest.main()
