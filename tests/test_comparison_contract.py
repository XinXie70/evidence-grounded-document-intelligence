import unittest

from egdi.comparison_contract import adapt_selection


class ComparisonContractTests(unittest.TestCase):
    def base(self, selector, facts):
        return {
            "question_id": "doc::q1",
            "doc_id": "doc",
            "question": "How many more units does A have than B?",
            "selector_version": selector,
            "selected_facts": facts,
            "uses_gold_answer": False,
            "uses_gold_evidence_pages": False,
        }

    def test_adapts_list_count_without_question_specific_logic(self):
        facts = [
            {"topic": "A", "value": "7", "unit": "steps", "pages": [2, 3],
             "marker_style": "numbered", "observed_numbers": [1, 2],
             "selection_basis": "topic_then_sequence"},
            {"topic": "B", "value": "2", "unit": "steps", "pages": [8],
             "marker_style": "step", "observed_numbers": [1, 2],
             "selection_basis": "topic_then_sequence"},
        ]
        result = adapt_selection(
            self.base("list_count_selector_v1_excludes_reference_sections", facts)
        )
        self.assertEqual(result["left"]["label"], "A")
        self.assertEqual(result["left"]["value"], "7")
        self.assertEqual(result["left"]["provenance"]["supporting_pages"], [2, 3])
        self.assertEqual(result["operation"], "left_minus_right")

    def test_absolute_difference_wording_sets_absolute_operation(self):
        facts = [
            {"topic": "A", "value": "7", "unit": "steps", "pages": [2],
             "marker_style": "numbered", "observed_numbers": [1],
             "selection_basis": "topic_then_sequence"},
            {"topic": "B", "value": "2", "unit": "steps", "pages": [8],
             "marker_style": "numbered", "observed_numbers": [1],
             "selection_basis": "topic_then_sequence"},
        ]
        selection = self.base("list_count_selector_v1_excludes_reference_sections", facts)
        selection["question"] = "What is the difference between A and B?"
        self.assertEqual(adapt_selection(selection)["operation"], "absolute_difference")

    def test_preserves_multistage_product_provenance(self):
        def fact(product, value, pages):
            return {"product_id": product, "dimension": "depth", "descriptor": "d",
                    "value": value, "unit": "millimeters", "identity_page": pages[0],
                    "dimension_anchor_page": pages[1], "value_page": pages[2],
                    "selection_basis": "identity_then_dimension"}
        result = adapt_selection(self.base("product_dimension_selector_v0", [
            fact("A", "30", [1, 2, 2]), fact("B", "40", [4, 4, 5])]))
        self.assertEqual(result["right"]["provenance"]["value_pages"], [5])
        self.assertEqual(result["right"]["provenance"]["supporting_pages"], [4, 5])

    def test_adapts_all_supported_structural_selector_types(self):
        cases = [
            ("continued_enrollment_table_v0", {"group": "Female", "status": "part-time",
             "program": "P", "value": "10", "unit": "students", "table_start_page": 1,
             "total_page": 2, "selection_basis": "continued table"}),
            ("interest_method_selector_v0", {"method": "Compound", "row": "Amount",
             "value": "521", "unit": "dollars", "page": 3, "selection_basis": "row"}),
            ("balance_sheet_selector_v0", {"entity": "Company", "row": "Assets",
             "value": "10.2", "unit": "billion yen", "page": 4,
             "as_of_date": "2020", "discriminator": "consolidated", "selection_basis": "row"}),
            ("qualified_metric_selector_v0", {"entity": "China", "metric": "stocks",
             "value": "30.4", "unit": "million bales", "page": 5,
             "statistic": "ending", "time_scope": "ten years", "selection_basis": "qualified"}),
        ]
        for selector, fact in cases:
            with self.subTest(selector=selector):
                result = adapt_selection(self.base(selector, [fact, dict(fact)]))
                self.assertEqual(result["left"]["value"], fact["value"])
                self.assertTrue(result["left"]["provenance"]["value_pages"])

    def test_adapts_layout_selection_using_experiment_type_fallback(self):
        fact = {"column_path": ["Male", "Weekday"], "row": "Personal care",
                "table_title": "Time use", "value": "10.8", "unit": "hours", "page": 21,
                "selection_basis": "header path and row"}
        selection = self.base("unused", [fact, dict(fact)])
        selection.pop("selector_version")
        selection["experiment_type"] = "oracle_page_question_guided_layout_fact_selection"
        result = adapt_selection(selection)
        self.assertEqual(result["left"]["label"], "Male / Weekday")
        self.assertEqual(result["left"]["metric"], "Personal care")

    def test_labels_oracle_pages_and_rejects_unknown_types_and_bad_values(self):
        fact = {"method": "A", "row": "Amount", "value": "1", "unit": "dollars",
                "page": 1, "selection_basis": "row"}
        selection = self.base("interest_method_selector_v0", [fact, dict(fact)])
        selection["uses_gold_evidence_pages"] = True
        oracle = adapt_selection(selection)
        self.assertEqual(
            oracle["evaluation_eligibility"]["evidence_retrieval"],
            "ineligible_gold_evidence_pages",
        )
        self.assertEqual(oracle["evaluation_eligibility"]["grounded_reasoning"], "eligible")
        selection["uses_gold_evidence_pages"] = False
        selection["selector_version"] = "question_q1_special_case"
        with self.assertRaisesRegex(ValueError, "unsupported selector type"):
            adapt_selection(selection)
        selection["selector_version"] = "interest_method_selector_v0"
        selection["selected_facts"][0]["value"] = "not-a-number"
        with self.assertRaisesRegex(ValueError, "decimal string"):
            adapt_selection(selection)

    def test_requires_explicit_gold_provenance(self):
        fact = {"method": "A", "row": "Amount", "value": "1", "unit": "dollars",
                "page": 1, "selection_basis": "row"}
        selection = self.base("interest_method_selector_v0", [fact, dict(fact)])
        selection.pop("uses_gold_evidence_pages")
        with self.assertRaisesRegex(ValueError, "gold evidence pages"):
            adapt_selection(selection)


if __name__ == "__main__":
    unittest.main()
