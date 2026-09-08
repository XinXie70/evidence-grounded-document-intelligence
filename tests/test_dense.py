import unittest

import numpy as np

from egdi.dense import PageDenseIndex
from egdi.text import build_page_record


class FakeDenseEncoder:
    def split_text(self, text, chunk_tokens, overlap_tokens):
        tokens = text.split()
        if not tokens:
            return [""]
        step = chunk_tokens - overlap_tokens
        return [
            " ".join(tokens[start : start + chunk_tokens])
            for start in range(0, len(tokens), step)
        ]

    def _vector(self, text):
        lowered = text.casefold()
        return np.array(
            [
                float("investment" in lowered or "holdings" in lowered),
                float("emergency" in lowered or "evacuation" in lowered),
                float("other" in lowered),
            ]
        )

    def encode_passages(self, texts):
        return np.stack([self._vector(text) for text in texts])

    def encode_query(self, query):
        return self._vector(query)


class PageDenseIndexTests(unittest.TestCase):
    def setUp(self):
        self.records = [
            build_page_record("doc", 1, "Schedule of Investments and portfolio assets"),
            build_page_record("doc", 2, "Emergency evacuation procedures"),
            build_page_record("doc", 3, "other material"),
            build_page_record("doc", 4, ""),
        ]
        self.index = PageDenseIndex(self.records, FakeDenseEncoder(), chunk_tokens=3)

    def test_semantically_related_page_ranks_first(self):
        results = self.index.search("investment holdings", top_k=4)
        self.assertEqual(results[0].page, 1)
        self.assertGreater(results[0].score, results[1].score)

    def test_chunks_never_cross_pages_and_page_uses_best_chunk(self):
        page_one_chunks = [chunk for chunk in self.index.chunks if chunk.page == 1]
        self.assertEqual([chunk.chunk_index for chunk in page_one_chunks], [0, 1])
        result = self.index.search("investment", top_k=1)[0]
        self.assertEqual(result.page, 1)
        self.assertEqual(result.best_chunk_index, 0)

    def test_empty_page_is_retained(self):
        results = self.index.search("unknown", top_k=4)
        page_four = next(result for result in results if result.page == 4)
        self.assertEqual(page_four.extraction_status, "text_layer_missing")

    def test_ties_are_deterministic_by_page(self):
        results = self.index.search("unknown", top_k=4)
        self.assertEqual([result.page for result in results], [1, 2, 3, 4])

    def test_empty_query_returns_no_results(self):
        self.assertEqual(self.index.search("  ", top_k=3), [])

    def test_rejects_invalid_inputs_and_embedding_shapes(self):
        with self.assertRaises(ValueError):
            PageDenseIndex([], FakeDenseEncoder())
        with self.assertRaises(ValueError):
            PageDenseIndex(self.records, FakeDenseEncoder(), chunk_tokens=0)
        with self.assertRaises(ValueError):
            PageDenseIndex(self.records, FakeDenseEncoder(), chunk_tokens=3, overlap_tokens=3)
        with self.assertRaises(ValueError):
            self.index.search("query", top_k=0)
        with self.assertRaises(TypeError):
            self.index.search(None, top_k=1)


if __name__ == "__main__":
    unittest.main()
