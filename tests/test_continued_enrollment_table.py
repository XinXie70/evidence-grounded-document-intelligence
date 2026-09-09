import unittest

from egdi.continued_enrollment_table import (
    parse_enrollment_comparison,
    select_continued_enrollment_facts,
)


QUESTION = (
    "How many more part-time female students are enrolled in bachelor's and first "
    "professional degree programs compared to part-time male students, according "
    "to the gender-specific enrolment tables for Fall 2008?"
)
HEADER = (
    "Program Bachelor's and 1st Professional Degree Master's Degree Doctoral Degree "
    "Full-Time Part-Time Full-Time Part-Time Full-Time Part-Time"
)


class ContinuedEnrollmentTableTests(unittest.TestCase):
    def test_parses_ordered_comparison_groups(self):
        self.assertEqual(parse_enrollment_comparison(QUESTION), ("Female", "Male"))

    def test_links_each_title_page_to_repeated_header_continuation(self):
        pages = {
            4: f"Male Enrolment by Program, 2008 {HEADER} rows",
            5: f"{HEADER} Grand Total 1,957 564 98 147 42 7",
            6: f"Female Enrolment by Program, 2008 {HEADER} rows",
            7: f"{HEADER} Grand Total 3,685 1,503 151 206 42 7",
            9: "Grand Total 999 888 777 666 555 444",
        }
        facts = select_continued_enrollment_facts(QUESTION, pages)
        self.assertEqual(
            [(fact.group, fact.table_start_page, fact.total_page, fact.value) for fact in facts],
            [("Female", 6, 7, "1503"), ("Male", 4, 5, "564")],
        )

    def test_generalizes_to_full_time_difference_wording(self):
        question = (
            "What is the difference between the grand total of full-time female "
            "Bachelor's and 1st Professional degree students and the grand total "
            "of full-time male Bachelor's and 1st Professional degree students?"
        )
        pages = {
            4: f"Male Enrolment by Program, 2008 {HEADER} rows",
            5: f"{HEADER} Grand Total 1,957 564 98 147 42 7",
            6: f"Female Enrolment by Program, 2008 {HEADER} rows",
            7: f"{HEADER} Grand Total 3,685 1,503 151 206 42 7",
        }
        facts = select_continued_enrollment_facts(question, pages)
        self.assertEqual([(fact.group, fact.status, fact.value) for fact in facts], [
            ("Female", "Full-Time", "3685"), ("Male", "Full-Time", "1957")])

    def test_rejects_continuation_without_repeated_header(self):
        pages = {
            4: f"Male Enrolment by Program, 2008 {HEADER}",
            5: "Grand Total 1,957 564 98 147 42 7",
            6: f"Female Enrolment by Program, 2008 {HEADER}",
            7: f"{HEADER} Grand Total 3,685 1,503 151 206 42 7",
        }
        with self.assertRaisesRegex(ValueError, "repeated table header"):
            select_continued_enrollment_facts(QUESTION, pages)

    def test_rejects_question_outside_narrow_pattern(self):
        with self.assertRaisesRegex(ValueError, "supported comparison"):
            parse_enrollment_comparison("How many students enrolled?")


if __name__ == "__main__":
    unittest.main()
