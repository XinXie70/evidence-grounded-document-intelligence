import unittest

from egdi.comparison_intent import parse_comparison_intent


class ComparisonIntentTests(unittest.TestCase):
    def test_parses_directional_more_and_less(self):
        more = parse_comparison_intent("How many more students does A have compared to B?")
        less = parse_comparison_intent("How many millimeters less is A than B?")
        self.assertEqual(more.operation, "left_minus_right")
        self.assertEqual(more.direction_word, "more")
        self.assertEqual(less.direction_word, "less")

    def test_parses_absolute_difference_with_internal_and(self):
        question = (
            "What is the difference between full-time female Bachelor's and 1st "
            "Professional students and full-time male students?"
        )
        intent = parse_comparison_intent(question)
        self.assertEqual(intent.operation, "absolute_difference")
        self.assertEqual(intent.wording_family, "difference_between")

    def test_parses_trailing_difference_after_compared_to(self):
        question = (
            "How many pins does connector A have, compared to connector B? "
            "What is the difference?"
        )
        intent = parse_comparison_intent(question)
        self.assertEqual(intent.operation, "absolute_difference")

    def test_rejects_noncomparison(self):
        with self.assertRaisesRegex(ValueError, "supported comparison"):
            parse_comparison_intent("How many students enrolled?")


if __name__ == "__main__":
    unittest.main()
