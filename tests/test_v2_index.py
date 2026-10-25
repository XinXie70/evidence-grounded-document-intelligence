import hashlib
import unittest

import numpy as np

from egdi.text import build_page_record
from egdi.v2.index import DocumentIndex


class FakeEncoder:
    """Hashed bag-of-words embeddings; enough to exercise the index plumbing."""

    def split_text(self, text, chunk_tokens, overlap_tokens):
        words = text.split()
        return [" ".join(words[i : i + 8]) for i in range(0, len(words), 8)] or [""]

    def _embed(self, text):
        vector = np.zeros(32)
        for word in text.lower().split():
            vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % 32] += 1
        return vector

    def encode_passages(self, texts):
        return np.array([self._embed(t) for t in texts])

    def encode_query(self, query):
        return self._embed(query)


PAGES = {
    1: "Cover page of the annual report " * 5,
    2: "Total revenue grew strongly this year driven by cloud subscriptions " * 5,
    3: "Employee headcount and diversity statistics by region " * 5,
    4: "Risk factors include currency exposure and supply chain delays " * 5,
}


class DocumentIndexTests(unittest.TestCase):
    def setUp(self):
        records = [build_page_record("doc", page, text) for page, text in PAGES.items()]
        self.index = DocumentIndex(records, FakeEncoder())

    def test_relevant_page_ranks_first_with_snippet(self):
        results = self.index.search("total revenue cloud subscriptions", 3)
        self.assertEqual(results[0]["page"], 2)
        self.assertLessEqual(len(results), 3)
        for item in results:
            self.assertEqual(set(item), {"page", "score", "snippet"})
            self.assertTrue(0 < len(item["snippet"]) <= 300)

    def test_deterministic_and_page_metadata(self):
        self.assertEqual(self.index.search("headcount", 4), self.index.search("headcount", 4))
        self.assertEqual(self.index.page_count, 4)
        self.assertEqual(sorted(self.index.page_text), [1, 2, 3, 4])

    def test_rejects_mixed_documents(self):
        mixed = [build_page_record("a", 1, "x y z"), build_page_record("b", 1, "x y z")]
        with self.assertRaises(ValueError):
            DocumentIndex(mixed, FakeEncoder())


if __name__ == "__main__":
    unittest.main()
