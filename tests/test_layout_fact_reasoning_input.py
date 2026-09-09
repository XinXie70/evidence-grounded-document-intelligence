import unittest

from egdi.layout_fact_reasoning_input import build_layout_fact_reasoning_record


class LayoutFactReasoningInputTests(unittest.TestCase):
    def setUp(self):
        self.selection = {
            "question_id": "doc::q1",
            "doc_id": "doc",
            "uses_gold_answer_or_gold_facts": False,
            "selected_facts": [
                {
                    "page": 2,
                    "table_title": "Table 1",
                    "unit": "hours",
                    "row": "Personal care",
                    "column_path": ["Male"],
                    "value": "10.8",
                }
            ],
        }
        self.template = {
            "question_id": "doc::q1",
            "doc_id": "doc",
            "model_input": {
                "instructions": "Use evidence only.",
                "question": "How much?",
                "response_schema": {"type": "object"},
            },
        }

    def test_builds_condition_blind_input_with_structured_fact_text(self):
        result = build_layout_fact_reasoning_record(self.selection, self.template)
        self.assertEqual(result["condition"], "layout_facts")
        self.assertEqual(result["evidence_pages"], [2])
        text = result["model_input"]["evidence"][0]["text"]
        self.assertIn("Row: Personal care", text)
        self.assertIn("Column: Male", text)
        self.assertNotIn("answer", result["model_input"])

    def test_requires_no_gold_fact_provenance_and_matching_identity(self):
        self.selection["uses_gold_answer_or_gold_facts"] = True
        with self.assertRaisesRegex(ValueError, "exclude gold"):
            build_layout_fact_reasoning_record(self.selection, self.template)
        self.selection["uses_gold_answer_or_gold_facts"] = False
        self.template["question_id"] = "other"
        with self.assertRaisesRegex(ValueError, "question ids"):
            build_layout_fact_reasoning_record(self.selection, self.template)


if __name__ == "__main__":
    unittest.main()
