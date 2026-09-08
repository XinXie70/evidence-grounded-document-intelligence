import unittest

from egdi.text import PageRecord
from egdi.visual_routing import (
    ROUTE_DOCUMENT_GLOBAL,
    ROUTE_LOCAL_VISUAL,
    ROUTE_SCANNED_DOCUMENT,
    ROUTE_TEXT,
    choose_visual_route,
)
from egdi.visual_routing_v1 import choose_visual_route_v1


def page(doc_id: str, number: int, text: str) -> PageRecord:
    return PageRecord(
        doc_id=doc_id,
        page=number,
        text=text,
        non_whitespace_chars=sum(not character.isspace() for character in text),
        extraction_status="ok" if text else "text_layer_missing",
    )


class VisualRoutingV1Tests(unittest.TestCase):
    def test_observed_short_global_phrase_moves_r1_to_r3(self):
        records = [page("doc", 1, "assets table")]
        question = "Across the document, how many locations display the table?"
        self.assertEqual(choose_visual_route(question, records)["route"], ROUTE_LOCAL_VISUAL)
        result = choose_visual_route_v1(question, records)
        self.assertEqual(result["route"], ROUTE_DOCUMENT_GLOBAL)
        self.assertEqual(result["matched_signal"], "across the document")
        self.assertEqual(result["routing_policy_version"], "r0-r3-v1")

    def test_existing_routes_are_unchanged_without_new_phrase(self):
        normal = [page("doc", 1, "ordinary searchable text")]
        scanned = [page("scan", 1, "")]
        self.assertEqual(choose_visual_route_v1("What is the policy?", normal)["route"], ROUTE_TEXT)
        self.assertEqual(choose_visual_route_v1("What does the chart show?", normal)["route"], ROUTE_LOCAL_VISUAL)
        self.assertEqual(choose_visual_route_v1("What is the value?", scanned)["route"], ROUTE_SCANNED_DOCUMENT)
        self.assertEqual(
            choose_visual_route_v1("Across the entire document, how many?", normal)["route"],
            ROUTE_DOCUMENT_GLOBAL,
        )

    def test_new_global_signal_has_priority_over_zero_text(self):
        scanned = [page("scan", 1, "")]
        result = choose_visual_route_v1(
            "Across the document, how many figures are present?", scanned
        )
        self.assertEqual(result["route"], ROUTE_DOCUMENT_GLOBAL)

    def test_v0_validation_is_preserved(self):
        with self.assertRaises(ValueError):
            choose_visual_route_v1("Across the document, how many?", [])
        with self.assertRaises(ValueError):
            choose_visual_route_v1(" ", [page("doc", 1, "text")])


if __name__ == "__main__":
    unittest.main()
