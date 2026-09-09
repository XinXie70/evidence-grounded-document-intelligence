import unittest

from egdi.layout_fact_selector import (
    LayoutFact,
    PositionedWord,
    group_words_into_lines,
    select_comparison_facts,
)


def fact(page, unit, row, column, value, title):
    return LayoutFact(page, title, unit, row, column, value, "test")


class LayoutFactSelectorTests(unittest.TestCase):
    def test_groups_words_by_position_without_changing_horizontal_order(self):
        words = [
            PositionedWord("value", 20, 30, 11),
            PositionedWord("row", 0, 10, 10),
            PositionedWord("next", 0, 10, 20),
        ]
        lines = group_words_into_lines(words, y_tolerance=2)
        self.assertEqual([[word.text for word in line] for line in lines], [["row", "value"], ["next"]])

    def test_selects_precise_consistent_fact_without_gold_answer(self):
        question = (
            "According to the weekday main-activity table by sex, how many more hours "
            "do males spend on personal care than females spend on housework and family care?"
        )
        facts = [
            fact(21, "hours", "Personal care", ("Male",), "10.8", "main activity"),
            fact(21, "hours", "Housework and family care", ("Female",), "4.8", "main activity"),
            fact(
                55,
                "minutes",
                "Total",
                ("Female", "Total"),
                "287.4",
                "housework and family care by sex and marital status",
            ),
        ]
        selected = select_comparison_facts(question, facts)
        self.assertEqual([(item.page, item.value) for item in selected], [(21, "10.8"), (55, "287.4")])

    def test_rejects_question_without_explicit_comparison(self):
        with self.assertRaisesRegex(ValueError, "explicit 'than'"):
            select_comparison_facts("What is the value?", [])


if __name__ == "__main__":
    unittest.main()
