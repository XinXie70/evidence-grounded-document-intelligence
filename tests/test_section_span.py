import unittest

from egdi.section_span import extract_top_level_sections, select_query_linked_section
from egdi.text import PageRecord


def records(texts: list[str], doc_id: str = "doc") -> list[PageRecord]:
    return [
        PageRecord(doc_id, index, text, len(text.replace(" ", "")), "ok")
        for index, text in enumerate(texts, start=1)
    ]


class SectionSpanTests(unittest.TestCase):
    def test_extracts_span_until_next_numbered_section(self):
        pages = records(
            [
                "Manual 1 5 Cable Diagram The diagrams follow",
                "Manual 2 Cable Diagram 2",
                "Manual 3 continuation",
                "Manual 4 6 Supported Device The table follows",
                "Manual 5 continuation",
            ]
        )
        sections = extract_top_level_sections(pages)
        self.assertEqual(sections[0]["start_page"], 1)
        self.assertEqual(sections[0]["end_page"], 3)
        self.assertEqual(sections[0]["pages"], [1, 2, 3])
        self.assertEqual(sections[1]["pages"], [4, 5])

    def test_selects_query_linked_chapter(self):
        pages = records(
            [
                "Manual 1 5 Cable Diagram The diagrams follow",
                "Manual 2 continuation",
                "Manual 3 6 Supported Device The table follows",
            ]
        )
        selected = select_query_linked_section(
            "How many cable diagram sections are in the chapter?", pages
        )
        self.assertIsNotNone(selected)
        self.assertEqual(selected["pages"], [1, 2])
        self.assertEqual(selected["title_overlap_tokens"], ["cable", "diagram"])

    def test_selects_across_all_listed_section(self):
        pages = records(
            [
                "Manual 1 6 Supported Device The range follows",
                "Manual 2 continuation",
                "Manual 3 7 Address Code The codes follow",
            ]
        )
        selected = select_query_linked_section(
            "Compare supported device tables across all listed series", pages
        )
        self.assertIsNotNone(selected)
        self.assertEqual(selected["pages"], [1, 2])

    def test_requires_scope_signal_and_two_title_tokens(self):
        pages = records(["Manual 1 5 Cable Diagram The diagrams follow"])
        self.assertIsNone(select_query_linked_section("What is the cable diagram?", pages))
        self.assertIsNone(select_query_linked_section("What is in this chapter?", pages))

    def test_rejects_invalid_records_and_overlap(self):
        with self.assertRaises(ValueError):
            extract_top_level_sections([])
        mixed = records(["Manual 1 5 Cable Diagram"], "a") + records(
            ["Manual 2 6 Supported Device"], "b"
        )
        with self.assertRaises(ValueError):
            extract_top_level_sections(mixed)
        with self.assertRaises(ValueError):
            select_query_linked_section("chapter", records(["text"]), minimum_title_token_overlap=0)


if __name__ == "__main__":
    unittest.main()
