import unittest

from egdi.text import build_page_record
from egdi.visual_routing import (
    ROUTE_DOCUMENT_GLOBAL,
    ROUTE_LOCAL_VISUAL,
    ROUTE_SCANNED_DOCUMENT,
    ROUTE_TEXT,
    choose_visual_route,
)


class VisualRoutingTests(unittest.TestCase):
    def _records(self, texts):
        return [
            build_page_record("doc-a", page, text)
            for page, text in enumerate(texts, start=1)
        ]

    def test_pilot06_chart_question_uses_local_visual_route(self):
        result = choose_visual_route(
            "In the bar chart, what percentage had not visited at all?",
            self._records(["usable native document text " * 10]),
        )

        self.assertEqual(result["route"], ROUTE_LOCAL_VISUAL)
        self.assertEqual(result["matched_signal"], "bar chart")

    def test_pilot16_and_pilot17_zero_text_documents_use_scanned_route(self):
        for question, page_count in (
            ("What is the difference in depth between the two dates?", 37),
            ("How many specific items are listed in the section?", 51),
        ):
            with self.subTest(page_count=page_count):
                result = choose_visual_route(question, self._records([""] * page_count))
                self.assertEqual(result["route"], ROUTE_SCANNED_DOCUMENT)
                self.assertEqual(result["nonempty_page_count"], 0)

    def test_pilot18_global_phrase_requires_document_complete_route(self):
        result = choose_visual_route(
            "How many distinct stacked bar charts appear across the entire document?",
            self._records(["usable native document text " * 10] * 42),
        )

        self.assertEqual(result["route"], ROUTE_DOCUMENT_GLOBAL)
        self.assertEqual(result["document_page_count"], 42)

    def test_ordinary_text_question_keeps_text_route(self):
        result = choose_visual_route(
            "What age threshold distinguishes a child from an adult?",
            self._records(["The age threshold is described in this paragraph. " * 5]),
        )

        self.assertEqual(result["route"], ROUTE_TEXT)
        self.assertIsNone(result["matched_signal"])
        self.assertFalse(result["uses_gold_or_answer_labels"])

    def test_global_requirement_has_priority_over_other_signals(self):
        result = choose_visual_route(
            "How many charts appear throughout the document?",
            self._records([""] * 4),
        )

        self.assertEqual(result["route"], ROUTE_DOCUMENT_GLOBAL)

    def test_rejects_invalid_question_empty_records_and_mixed_documents(self):
        with self.assertRaisesRegex(ValueError, "question"):
            choose_visual_route(" ", self._records(["text"]))
        with self.assertRaisesRegex(ValueError, "at least one"):
            choose_visual_route("question", [])
        mixed = [build_page_record("doc-a", 1, "a"), build_page_record("doc-b", 2, "b")]
        with self.assertRaisesRegex(ValueError, "one document"):
            choose_visual_route("question", mixed)


if __name__ == "__main__":
    unittest.main()
