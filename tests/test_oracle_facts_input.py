import json
import unittest

from egdi.oracle_facts_input import build_oracle_facts_record


class OracleFactsInputTests(unittest.TestCase):
    def setUp(self):
        self.oracle_page = {
            "schema_version": 1,
            "question_id": "doc-a::q1",
            "doc_id": "doc-a",
            "condition": "oracle_page",
            "model_input": {
                "instructions": "Use only supplied evidence.",
                "question": "What is the difference?",
                "evidence": [{"page": 2, "text": "whole page"}],
                "response_schema": {"type": "object"},
            },
        }
        self.benchmark = {
            "id": "doc-a::q1",
            "answer": {"answer_text": "MUST NOT LEAK", "is_answerable": True},
            "evidences": [
                {"local_id": "e1", "page": 2},
                {"local_id": "e2", "page": 7},
            ],
            "facts": [
                {
                    "local_id": "f1",
                    "text_description": "First measured value is 10 hours.",
                    "evidence_local_id": "e1",
                },
                {
                    "local_id": "f2",
                    "text_description": "Second measured value is 120 minutes.",
                    "evidence_local_id": "e2",
                },
            ],
        }

    def test_builds_fact_input_without_answer_leakage(self):
        record = build_oracle_facts_record(self.oracle_page, self.benchmark)
        serialized = json.dumps(record["model_input"])

        self.assertEqual(record["condition"], "oracle_facts")
        self.assertEqual(record["evidence_pages"], [2, 7])
        self.assertEqual(
            record["model_input"]["evidence"],
            [
                {"page": 2, "text": "First measured value is 10 hours."},
                {"page": 7, "text": "Second measured value is 120 minutes."},
            ],
        )
        self.assertNotIn("MUST NOT LEAK", serialized)
        self.assertNotIn("answer_text", serialized)
        self.assertNotIn("facts", serialized)

    def test_rejects_mismatched_question_and_unknown_evidence(self):
        self.benchmark["id"] = "other::q1"
        with self.assertRaisesRegex(ValueError, "question id"):
            build_oracle_facts_record(self.oracle_page, self.benchmark)

        self.benchmark["id"] = "doc-a::q1"
        self.benchmark["facts"][0]["evidence_local_id"] = "missing"
        with self.assertRaisesRegex(ValueError, "unknown evidence"):
            build_oracle_facts_record(self.oracle_page, self.benchmark)


if __name__ == "__main__":
    unittest.main()
