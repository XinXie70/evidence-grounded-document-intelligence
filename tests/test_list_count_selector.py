import unittest

from egdi.list_count_selector import (
    extract_article_topics,
    select_list_count_facts,
)


QUESTION = (
    "Comparing the article about building resilience that lists numbered practices "
    "and the article about keys to resilience that describes numbered mental health "
    "competencies, how many more steps does the former article have than the latter?"
)


class ListCountSelectorTests(unittest.TestCase):
    def test_extracts_two_article_topics(self):
        self.assertEqual(
            extract_article_topics(QUESTION),
            ("building resilience", "keys to resilience"),
        )

    def test_selects_topic_matched_lists_and_extends_continuation_page(self):
        pages = {
            10: "Other subject. 1. Alpha 2. Beta 3. Gamma",
            15: "Seven Steps to Build Resilience. 1. One 2. Two 3. Three 4. Four 5. Five",
            16: "6. Six 7. Seven",
            19: "Keys to Resilience. Step 1: Kindness Step 2: Balance",
            25: "Unrelated references. 1. One 2. Two 2. Duplicate 88. Citation",
        }
        facts = select_list_count_facts(QUESTION, pages)
        self.assertEqual(
            [(fact.pages, fact.observed_numbers, fact.value) for fact in facts],
            [
                ((15, 16), (1, 2, 3, 4, 5, 6, 7), "7"),
                ((19,), (1, 2), "2"),
            ],
        )

    def test_rejects_unmatched_topic_instead_of_using_arbitrary_numbered_page(self):
        with self.assertRaisesRegex(ValueError, "none matches topic"):
            select_list_count_facts(QUESTION, {4: "1. Alpha 2. Beta"})

    def test_does_not_treat_numbered_references_as_article_steps(self):
        pages = {
            15: "Build Resilience. 1. One 2. Two 3. Three 4. Four 5. Five",
            16: "6. Six 7. Seven",
            19: "Keys to Resilience. Step 1: Kindness Step 2: Balance",
            38: (
                "Building resilience supports mental health. Conclusion. References "
                "1. Author One 2. Author Two 3. Author Three 4. Author Four "
                "5. Author Five 6. Author Six"
            ),
        }
        facts = select_list_count_facts(QUESTION, pages)
        self.assertEqual([fact.value for fact in facts], ["7", "2"])
        self.assertEqual(facts[0].pages, (15, 16))

    def test_rejects_question_outside_narrow_supported_pattern(self):
        with self.assertRaisesRegex(ValueError, "two compared articles"):
            extract_article_topics("How many steps are listed?")


if __name__ == "__main__":
    unittest.main()
