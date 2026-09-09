import unittest

import numpy as np

from egdi.dense import DenseChunk
from egdi.evidence_window import (
    build_page_localization_diagnostic,
    select_chunk_window,
)


class FakeEncoder:
    def split_text(self, text, chunk_tokens, overlap_tokens):
        return text.split("|")

    def encode_passages(self, texts):
        return np.array([[float("target" in text), 1.0] for text in texts])

    def encode_query(self, query):
        return np.array([1.0, 0.0])


def chunk(page, index, text):
    return DenseChunk("doc", page, index, text, "ok")


class EvidenceWindowTests(unittest.TestCase):
    def test_selects_neighbors_without_crossing_pages(self):
        chunks = [
            chunk(1, 0, "a"),
            chunk(1, 1, "b"),
            chunk(1, 2, "target"),
            chunk(2, 0, "other page"),
        ]
        selected = select_chunk_window(
            chunks,
            page=1,
            best_chunk_index=2,
            before_chunks=2,
            after_chunks=1,
        )
        self.assertEqual([(item.page, item.chunk_index) for item in selected], [(1, 0), (1, 1), (1, 2)])

    def test_rejects_missing_best_chunk(self):
        with self.assertRaisesRegex(ValueError, "absent"):
            select_chunk_window(
                [chunk(1, 0, "a")],
                page=1,
                best_chunk_index=2,
                before_chunks=1,
                after_chunks=1,
            )

    def test_diagnostic_keeps_pages_and_expands_around_best_chunk(self):
        source = {
            "question_id": "doc::q1",
            "doc_id": "doc",
            "evidence_pages": [1, 2],
            "model_input": {
                "question": "find target",
                "evidence": [
                    {"page": 1, "text": "header|value|target label"},
                    {"page": 2, "text": "target second|tail"},
                ],
            },
        }
        result = build_page_localization_diagnostic(
            source,
            FakeEncoder(),
            before_chunks=2,
            after_chunks=1,
        )
        self.assertEqual(result["pages"], [1, 2])
        self.assertEqual(
            result["localized_evidence"][0]["expanded_chunk_indexes"],
            [0, 1, 2],
        )
        self.assertIn("header value target label", result["localized_evidence"][0]["expanded_text"])
        self.assertTrue(result["configuration"]["uses_gold_pages_to_isolate_within_page_localization"])


if __name__ == "__main__":
    unittest.main()
