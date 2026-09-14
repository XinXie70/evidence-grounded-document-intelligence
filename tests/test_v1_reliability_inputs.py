import unittest

import numpy as np

from egdi.text import build_page_record
from egdi.v1_reliability_inputs import (
    build_v1_reliability_cases,
    load_layout_text_directory,
)


class FakeEncoder:
    def split_text(self, text, chunk_tokens, overlap_tokens):
        return [text]

    def encode_passages(self, texts):
        return np.asarray([[float("needle" in text), 1.0] for text in texts])

    def encode_query(self, query):
        return np.asarray([1.0, 1.0])


class V1ReliabilityInputsTests(unittest.TestCase):
    def records(self, doc_id, *, empty=False):
        return [
            build_page_record(
                doc_id,
                page,
                "" if empty else ("needle chart evidence" if page == 4 else f"page {page} filler"),
            )
            for page in range(1, 13)
        ]

    def test_builds_text_and_visual_cases_without_selection_labels(self):
        text = {
            "pilot_id": "p1",
            "question_id": "text::q1",
            "doc_id": "text",
            "question": "Where is the needle evidence?",
            "oracle_pages": [99],
            "kind": "answerable",
        }
        visual = {
            "pilot_id": "p2",
            "question_id": "visual::q1",
            "doc_id": "visual",
            "question": "Which chart shows needle evidence?",
            "oracle_pages": [99],
            "kind": "answerable",
        }
        native = {"text": self.records("text"), "visual": self.records("visual")}

        # Obtain the deterministic candidate list first, then supply a label-free visual order.
        first = build_v1_reliability_cases(
            [text], native, FakeEncoder(), visual_rankings={}, ocr_corpora={}
        )[0]
        candidates = first["retrieval"]["rrf_pages"]
        visual_ranking = {
            "visual::q1": {
                "original_rrf_pages": candidates,
                "visual_reranked_pages": list(reversed(candidates)),
                "visual_scores": [float(value) for value in range(10, 0, -1)],
            }
        }
        cases = build_v1_reliability_cases(
            [text, visual],
            native,
            FakeEncoder(),
            visual_rankings=visual_ranking,
            ocr_corpora={},
        )
        self.assertEqual(cases[0]["route"], "r0_text")
        self.assertEqual(cases[1]["route"], "r1_local_visual")
        self.assertEqual(cases[1]["evidence_pages"], list(reversed(candidates))[:3])
        self.assertNotIn("oracle_pages", cases[0])
        self.assertNotIn("kind", cases[0])

    def test_builds_scanned_windows_and_global_abstention(self):
        scanned = {
            "pilot_id": "p3",
            "question_id": "scan::q1",
            "doc_id": "scan",
            "question": "needle — second clause",
        }
        global_question = {
            "pilot_id": "p4",
            "question_id": "global::q1",
            "doc_id": "global",
            "question": "How many examples appear across the entire document?",
        }
        native = {
            "scan": self.records("scan", empty=True),
            "global": self.records("global"),
        }
        cases = build_v1_reliability_cases(
            [scanned, global_question],
            native,
            FakeEncoder(),
            visual_rankings={},
            ocr_corpora={"scan": self.records("scan")},
            ocr_layout_text={
                "scan": {page: f"page {page}\nlayout line" for page in range(1, 13)}
            },
        )
        self.assertEqual(cases[0]["route"], "r2_scanned_document")
        self.assertIn(len(cases[0]["evidence_pages"]), {9, 12})
        self.assertIsNone(cases[0]["retrieval"]["dense_pages"])
        self.assertIn("\n", cases[0]["reasoning_input"]["model_input"]["evidence"][0]["text"])
        self.assertEqual(cases[1]["route"], "r3_document_global")
        self.assertEqual(cases[1]["evidence_pages"], [])
        self.assertFalse(cases[1]["paid_request_required"])

    def test_layout_directory_must_cover_every_page(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "page-01.txt").write_text("first\nline", encoding="utf-8")
            (root / "page-02.txt").write_text("second", encoding="utf-8")
            loaded = load_layout_text_directory(root, expected_pages=2)
            self.assertEqual(loaded[1], "first\nline")
            with self.assertRaisesRegex(ValueError, "every physical page"):
                load_layout_text_directory(root, expected_pages=3)


if __name__ == "__main__":
    unittest.main()
