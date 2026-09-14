import tempfile
import unittest
from pathlib import Path

import numpy as np

from egdi.visual_retrieval_batch import (
    build_blind_rankings,
    embedding_cache_path,
    image_cache_path,
    load_cached_embedding,
    save_embedding_atomic,
    unique_candidate_pages,
)


class VisualRetrievalBatchTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {
            "contains_gold_or_answer_labels": False,
            "questions": [
                {
                    "question_id": "q1",
                    "question": "Which page contains the revenue chart?",
                    "doc_id": "doc-b",
                    "candidate_pages": [3, 1],
                },
                {
                    "question_id": "q2",
                    "question": "Which table reports costs?",
                    "doc_id": "doc-a",
                    "candidate_pages": [2, 1],
                },
            ],
        }

    def test_unique_pages_are_sorted_and_deduplicated(self):
        self.assertEqual(
            unique_candidate_pages(self.manifest),
            [("doc-a", 1), ("doc-a", 2), ("doc-b", 1), ("doc-b", 3)],
        )

    def test_blind_rankings_keep_only_runtime_outputs(self):
        query = np.array([[1.0, 0.0]])
        embeddings = {
            ("doc-b", 3): np.array([[0.0, 1.0]]),
            ("doc-b", 1): np.array([[1.0, 0.0]]),
            ("doc-a", 2): np.array([[1.0, 0.0]]),
            ("doc-a", 1): np.array([[0.0, 1.0]]),
        }
        rankings = build_blind_rankings(
            self.manifest,
            encode_query=lambda question: query,
            load_page_embedding=lambda doc_id, page: embeddings[(doc_id, page)],
        )
        self.assertEqual(rankings[0]["visual_reranked_pages"], [1, 3])
        self.assertEqual(rankings[1]["visual_reranked_pages"], [2, 1])
        self.assertNotIn("gold_pages", str(rankings))

    def test_embedding_cache_round_trip_is_float32_and_atomic(self):
        with tempfile.TemporaryDirectory() as directory:
            path = embedding_cache_path(Path(directory), "doc", 7)
            values = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float64)
            save_embedding_atomic(path, values)
            loaded = load_cached_embedding(path)
            self.assertEqual(loaded.dtype, np.float32)
            np.testing.assert_array_equal(loaded, values.astype(np.float32))
            self.assertFalse(path.with_suffix(".npy.partial").exists())

    def test_cache_paths_preserve_document_and_physical_page(self):
        root = Path("cache")
        self.assertEqual(
            image_cache_path(root, "doc-id", 14),
            Path("cache/pages/doc-id/page-0014.png"),
        )
        self.assertEqual(
            embedding_cache_path(root, "doc-id", 14),
            Path("cache/embeddings/doc-id/page-0014.npy"),
        )

    def test_rejects_labels_corrupt_cache_and_duplicate_pages(self):
        with self.assertRaisesRegex(ValueError, "forbidden"):
            unique_candidate_pages({**self.manifest, "gold_pages": [1]})
        with self.assertRaisesRegex(ValueError, "unique"):
            unique_candidate_pages(
                {
                    "contains_gold_or_answer_labels": False,
                    "questions": [
                        {
                            "question_id": "q",
                            "doc_id": "doc",
                            "candidate_pages": [1, 1],
                        }
                    ],
                }
            )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.npy"
            np.save(path, np.array([1.0, 2.0]))
            with self.assertRaisesRegex(ValueError, "2D"):
                load_cached_embedding(path)


if __name__ == "__main__":
    unittest.main()
