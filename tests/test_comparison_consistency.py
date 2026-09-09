import unittest
from decimal import Decimal

from egdi.comparison_consistency import check_comparison_consistency


class ComparisonConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.question = "How many more hours do males spend on A than females spend on B?"
        self.facts = [
            {"value": "10.8", "unit": "hours"},
            {"value": "287.4", "unit": "minutes"},
        ]

    def test_rejects_correct_magnitude_with_reversed_direction(self):
        audit = check_comparison_consistency(
            self.question,
            self.facts,
            {"status": "answerable", "answer": "Males spend 6.01 fewer hours."},
        )
        self.assertFalse(audit["accepted"])
        self.assertTrue(audit["numeric_magnitude_correct"])
        self.assertFalse(audit["comparative_direction_correct"])
        self.assertEqual(audit["reason"], "comparative_polarity_mismatch")

    def test_accepts_correct_magnitude_and_direction(self):
        audit = check_comparison_consistency(
            self.question,
            self.facts,
            {"status": "answerable", "answer": "Males spend 6.01 more hours."},
        )
        self.assertTrue(audit["accepted"])
        self.assertEqual(audit["signed_difference_hours"], "6.01")

    def test_rejects_wrong_magnitude_and_unavailable_answer(self):
        wrong = check_comparison_consistency(
            self.question,
            self.facts,
            {"status": "answerable", "answer": "Males spend 5 more hours."},
        )
        self.assertFalse(wrong["accepted"])
        self.assertIn("numeric_magnitude_mismatch", wrong["reason"])
        missing = check_comparison_consistency(
            self.question,
            self.facts,
            {"status": "insufficient_evidence", "answer": None},
        )
        self.assertFalse(missing["accepted"])

    def test_validates_scope_and_tolerance(self):
        with self.assertRaisesRegex(ValueError, "explicit"):
            check_comparison_consistency("What is A?", self.facts, {})
        with self.assertRaisesRegex(ValueError, "exactly two"):
            check_comparison_consistency(self.question, self.facts[:1], {})
        with self.assertRaisesRegex(ValueError, "cannot be negative"):
            check_comparison_consistency(
                self.question, self.facts, {}, numeric_tolerance=Decimal("-0.1")
            )

    def test_accepts_same_unit_step_count_comparison(self):
        audit = check_comparison_consistency(
            "How many more steps does the former article have than the latter?",
            [{"value": "7", "unit": "steps"}, {"value": "2", "unit": "steps"}],
            {"status": "answerable", "answer": "The former has 5 more steps."},
        )
        self.assertTrue(audit["accepted"])
        self.assertEqual(audit["signed_difference"], "5")
        self.assertEqual(audit["normalized_unit"], "steps")

    def test_rejects_reversed_step_count_direction_and_mismatched_units(self):
        facts = [{"value": "7", "unit": "steps"}, {"value": "2", "unit": "steps"}]
        audit = check_comparison_consistency(
            "How many more steps does the former article have than the latter?",
            facts,
            {"status": "answerable", "answer": "The former has 5 fewer steps."},
        )
        self.assertFalse(audit["accepted"])
        self.assertEqual(audit["reason"], "comparative_polarity_mismatch")
        with self.assertRaisesRegex(ValueError, "same count unit"):
            check_comparison_consistency(
                "How many more steps does A have than B?",
                [{"value": "7", "unit": "steps"}, {"value": "2", "unit": "items"}],
                {"status": "answerable", "answer": "5 more"},
            )

    def test_accepts_directional_compared_to_wording(self):
        audit = check_comparison_consistency(
            "How many more part-time female students enrolled compared to part-time male students?",
            [
                {"value": "1503", "unit": "students"},
                {"value": "564", "unit": "students"},
            ],
            {"status": "answerable", "answer": "There are 939 more female students."},
        )
        self.assertTrue(audit["accepted"])
        self.assertEqual(audit["signed_difference"], "939")

    def test_preserves_shared_multiword_unit_without_naive_pluralization(self):
        audit = check_comparison_consistency(
            "How much larger is A compared to B?",
            [
                {"value": "336.3", "unit": "billion yen"},
                {"value": "82.7", "unit": "billion yen"},
            ],
            {"status": "answerable", "answer": "A is 253.6 billion yen larger."},
        )
        self.assertTrue(audit["accepted"])
        self.assertEqual(audit["normalized_unit"], "billion yen")

    def test_accepts_explicit_less_than_question_when_answer_direction_matches(self):
        audit = check_comparison_consistency(
            "How many millimeters less is A than B?",
            [{"value": "20", "unit": "millimeters"}, {"value": "35", "unit": "millimeters"}],
            {"status": "answerable", "answer": "A is 15 millimeters less than B."},
        )
        self.assertTrue(audit["accepted"])
        self.assertEqual(audit["expected_direction"], "fewer")
        self.assertEqual(audit["left_operand"], "20")
        self.assertEqual(audit["right_operand"], "35")
        self.assertEqual(audit["signed_difference"], "-15")
        self.assertEqual(audit["expected_magnitude"], "15")


if __name__ == "__main__":
    unittest.main()
