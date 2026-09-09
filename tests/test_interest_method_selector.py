import unittest

from egdi.interest_method_selector import (
    parse_interest_methods,
    select_interest_method_facts,
)


QUESTION = (
    "How much more total interest does the compound interest method accumulate "
    "compared to the simple interest method over the same period in the furniture "
    "purchase example used to explain borrowing costs?"
)


class InterestMethodSelectorTests(unittest.TestCase):
    def test_parses_ordered_methods(self):
        self.assertEqual(
            parse_interest_methods(QUESTION),
            ("Compound Interest", "Simple Interest"),
        )

    def test_uses_definition_heading_despite_misleading_table_label(self):
        pages = {
            49: (
                "Simple Interest Interest is charged only on the principal. "
                "You purchase a couch for $1,200. Total Interest 440"
            ),
            50: (
                "Compound Interest Interest Is charged on principal plus prior interest. "
                "You purchase a couch for $1,200. Simple Interest 3.33% table label. "
                "Total Interest 521"
            ),
            51: "Unrelated Total Interest 999",
        }
        facts = select_interest_method_facts(QUESTION, pages)
        self.assertEqual(
            [(fact.method, fact.page, fact.value) for fact in facts],
            [("Compound Interest", 50, "521"), ("Simple Interest", 49, "440")],
        )

    def test_rejects_missing_currency_context(self):
        pages = {
            49: "Simple Interest Interest is charged only. Total Interest 440",
            50: "Compound Interest Interest is charged on prior interest. Total Interest 521",
        }
        with self.assertRaisesRegex(ValueError, "exactly one"):
            select_interest_method_facts(QUESTION, pages)

    def test_rejects_question_without_directional_pair(self):
        with self.assertRaisesRegex(ValueError, "compared to"):
            parse_interest_methods("What is compound interest?")


if __name__ == "__main__":
    unittest.main()
