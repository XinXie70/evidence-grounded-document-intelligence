import unittest

from egdi.comparison_auto_route import route_case


HEADER = (
    "Program Bachelor's and 1st Professional Degree Master's Degree Doctoral Degree "
    "Full-Time Part-Time Full-Time Part-Time Full-Time Part-Time"
)


class ComparisonAutoRouteTests(unittest.TestCase):
    def test_selects_unique_enrollment_handler(self):
        case = {"question_id": "doc::q1", "doc_id": "doc", "question": (
            "What is the difference between full-time female Bachelor's and 1st "
            "Professional degree students and full-time male Bachelor's and 1st "
            "Professional degree students?")}
        pages = {
            4: f"Male Enrolment by Program, 2008 {HEADER}",
            5: f"{HEADER} Grand Total 1,957 564 98 147 42 7",
            6: f"Female Enrolment by Program, 2008 {HEADER}",
            7: f"{HEADER} Grand Total 3,685 1,503 151 206 42 7",
        }
        result = route_case(case, pages)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["selected_selector"], "continued_enrollment_table_v1")
        self.assertEqual(result["deterministic_comparison"]["magnitude"], "1728")

    def test_abstains_when_no_selector_supports_question(self):
        case = {"question_id": "doc::q2", "doc_id": "doc",
                "question": "What is the difference between red widgets and blue widgets?"}
        result = route_case(case, {1: "Red 10 Blue 5"})
        self.assertEqual(result["status"], "unsupported")
        self.assertEqual(len(result["selector_rejections"]), 6)


if __name__ == "__main__":
    unittest.main()
