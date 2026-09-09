import unittest

from egdi.qualified_metric_selector import (
    parse_qualified_metric_requests,
    select_qualified_metric_facts,
)


QUESTION = (
    "According to the document, how many million bales higher is China's projected "
    "ending stocks at the end of the projection period compared to India's projected "
    "average annual cotton exports over the next ten years?"
)


class QualifiedMetricSelectorTests(unittest.TestCase):
    def test_parses_ordered_qualified_requests(self):
        self.assertEqual(
            parse_qualified_metric_requests(QUESTION),
            ("china_ending_stocks_end_period", "india_exports_average_ten_years"),
        )

    def test_selects_fully_qualified_values_and_ignores_distractors(self):
        pages = {
            11: (
                "From 2024 onward, stocks in China are anticipated to drop steadily "
                "and reach 30.4 million bales at the end of the projection period."
            ),
            12: (
                "Exports of cotton will be limited due to India's cotton mill use "
                "increases in the next 10 year, with an average of 2.6 million bales."
            ),
            19: (
                "India's cotton exports climb to 3.8 million bales by 2033/34. "
                "India's cotton imports maintain an average of 1.2 million bales."
            ),
        }
        facts = select_qualified_metric_facts(QUESTION, pages)
        self.assertEqual(
            [(fact.entity, fact.metric, fact.statistic, fact.page, fact.value) for fact in facts],
            [
                ("China", "cotton ending stocks", "end value", 11, "30.4"),
                ("India", "cotton exports", "average", 12, "2.6"),
            ],
        )

    def test_rejects_partial_metric_match(self):
        pages = {
            11: "China ending stocks are 30.4 million bales.",
            12: "India exports are 2.6 million bales.",
        }
        with self.assertRaisesRegex(ValueError, "fully qualified"):
            select_qualified_metric_facts(QUESTION, pages)

    def test_rejects_question_without_required_time_qualifiers(self):
        with self.assertRaisesRegex(ValueError, "end-period"):
            parse_qualified_metric_requests(
                "How much higher are China's stocks compared to India's average exports over the next ten years?"
            )

    def test_generalizes_to_average_mill_use_growth_difference(self):
        question = (
            "According to the document, what is the difference in the projected "
            "long-term average annual growth rate of cotton mill use between China "
            "and India over the next ten years?"
        )
        pages = {
            11: (
                "China’s mill use is estimated at 37.4 million bales. Its growth "
                "rate is projected to grow moderately at an average rate of 1.2% per year."
            ),
            12: (
                "Sustained growth in the cotton textile industry is projected to increase "
                "cotton mill use in India. It is expected to grow at an average of 1.1% "
                "over the next ten years."
            ),
        }
        facts = select_qualified_metric_facts(question, pages)
        self.assertEqual(
            [(fact.entity, fact.value, fact.unit) for fact in facts],
            [("China", "1.2", "percentage points"),
             ("India", "1.1", "percentage points")],
        )


if __name__ == "__main__":
    unittest.main()
