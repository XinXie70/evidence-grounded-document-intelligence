import unittest

from egdi.comparison_fact_finalize import finalize_fact_result


class ComparisonFactFinalizeTests(unittest.TestCase):
    def setUp(self):
        self.input = {"question_id": "d::q", "doc_id": "d", "evidence_pages": [1, 2, 3],
                      "model_input": {"question": "What is the difference between A and B?"}}
        self.result = {"question_id": "d::q", "doc_id": "d", "evidence_pages": [1, 2, 3],
                       "response_id": "r", "model": "m", "validation": {"valid": True},
                       "call_log": {"estimated_cost": 0.01}, "output": {"status": "extracted",
                       "facts": [
                           {"label": "A", "metric": "rate", "value": "57600",
                            "unit": "baud", "cited_pages": [2]},
                           {"label": "B", "metric": "rate", "value": "38400",
                            "unit": "baud", "cited_pages": [1]}]}}

    def test_finalizes_ordered_facts_with_local_arithmetic(self):
        output = finalize_fact_result(self.input, self.result, case_id="x")
        case = output["cases"][0]
        self.assertEqual(case["operation"], "absolute_difference")
        self.assertEqual(case["deterministic_comparison"]["magnitude"], "19200")
        self.assertEqual(case["selected_facts"][0]["cited_pages"], [2])

    def test_finalizes_properly_grouped_thousands_values(self):
        self.result["output"]["facts"][0]["value"] = "157,472"
        self.result["output"]["facts"][1]["value"] = "144,042"
        output = finalize_fact_result(self.input, self.result, case_id="x")
        comparison = output["cases"][0]["deterministic_comparison"]
        self.assertEqual(comparison["magnitude"], "13430")

    def test_finalizes_accounting_parentheses_as_negative_values(self):
        self.result["output"]["facts"][0]["value"] = "(39.0)"
        self.result["output"]["facts"][1]["value"] = "(3.5)"
        output = finalize_fact_result(self.input, self.result, case_id="x")
        comparison = output["cases"][0]["deterministic_comparison"]
        self.assertEqual(comparison["left_operand"], "-39")
        self.assertEqual(comparison["magnitude"], "35.5")

    def test_rejects_mismatch_and_invalid_result(self):
        self.result["doc_id"] = "other"
        with self.assertRaisesRegex(ValueError, "doc_id mismatch"):
            finalize_fact_result(self.input, self.result, case_id="x")
        self.result["doc_id"] = "d"
        self.result["validation"]["valid"] = False
        self.result["output"]["facts"][0]["value"] = "not-a-number"
        with self.assertRaisesRegex(ValueError, "local validation"):
            finalize_fact_result(self.input, self.result, case_id="x")

    def test_preserves_insufficient_evidence_as_unsupported(self):
        self.result["output"] = {"status": "insufficient_evidence", "facts": []}
        output = finalize_fact_result(self.input, self.result, case_id="x")
        case = output["cases"][0]
        self.assertEqual(case["status"], "unsupported")
        self.assertEqual(case["selected_facts"], [])
        self.assertIsNone(case["deterministic_comparison"])


if __name__ == "__main__":
    unittest.main()
