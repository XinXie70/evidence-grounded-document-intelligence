import unittest

from egdi.comparison_validation_select import select_validation_cases


class ComparisonValidationSelectTests(unittest.TestCase):
    def test_selects_distinct_unseen_docs_in_stable_id_order(self):
        questions = [
            {"question_id": "b::q", "question": "What is the difference B?"},
            {"question_id": "a::q", "question": "What is the difference A?"},
            {"question_id": "c::q", "question": "What is the difference C?"},
        ]
        scope = {"split": "development_tune", "categories": {
            "difference_wording": {"questions": questions}}}
        retrieval = {"configuration": {"selection_split": "development_tune"},
                     "per_question": [
            {"question_id": "a::q", "doc_id": "excluded", "question": questions[1]["question"],
             "retrieved_pages": list(range(1, 11)), "gold_pages": [99]},
            {"question_id": "b::q", "doc_id": "doc-b", "question": questions[0]["question"],
             "retrieved_pages": list(range(11, 21)), "gold_pages": [98]},
            {"question_id": "c::q", "doc_id": "doc-c", "question": questions[2]["question"],
             "retrieved_pages": list(range(21, 31)), "gold_pages": [97]},
        ]}
        protocol = {"validation_case_count": 2,
                    "method_development_doc_ids": ["excluded"]}
        output = select_validation_cases(scope, retrieval, protocol)
        self.assertEqual([case["question_id"] for case in output["cases"]], ["b::q", "c::q"])
        self.assertNotIn("gold_pages", output["cases"][0])
        self.assertFalse(output["leakage_controls"]["uses_gold_evidence_pages"])


if __name__ == "__main__":
    unittest.main()
