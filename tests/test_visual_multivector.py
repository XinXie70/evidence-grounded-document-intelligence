import unittest
from pathlib import Path

import numpy as np

from egdi.visual_multivector import (
    build_candidate_page_render_command,
    late_interaction_score,
    rerank_visual_pages,
)


class VisualMultivectorTests(unittest.TestCase):
    def test_late_interaction_matches_each_query_vector_to_best_patch(self):
        query = np.array([[1.0, 0.0], [0.0, 1.0]])
        page = np.array([[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]])
        self.assertEqual(late_interaction_score(query, page), 2.0)

    def test_late_interaction_normalizes_vectors(self):
        query = np.array([[10.0, 0.0]])
        page = np.array([[2.0, 0.0], [0.0, 5.0]])
        self.assertEqual(late_interaction_score(query, page), 1.0)

    def test_rerank_uses_question_conditioned_page_scores(self):
        query = np.array([[1.0, 0.0], [0.0, 1.0]])
        pages = {
            8: np.array([[1.0, 0.0], [1.0, 0.0]]),
            2: np.array([[1.0, 0.0], [0.0, 1.0]]),
            7: np.array([[-1.0, 0.0], [0.0, -1.0]]),
        }
        ranked = rerank_visual_pages([8, 2, 7], query, pages)
        self.assertEqual([item.page for item in ranked], [2, 8, 7])
        self.assertGreater(ranked[0].score, ranked[1].score)

    def test_exact_score_ties_preserve_original_rrf_order(self):
        query = np.array([[1.0, 0.0]])
        same = np.array([[1.0, 0.0]])
        ranked = rerank_visual_pages([9, 3, 5], query, {9: same, 3: same, 5: same})
        self.assertEqual([item.page for item in ranked], [9, 3, 5])
        self.assertEqual([item.original_rank for item in ranked], [1, 2, 3])

    def test_rejects_bad_embeddings_and_candidate_mismatch(self):
        with self.assertRaisesRegex(ValueError, "non-empty 2D"):
            late_interaction_score(np.array([]), np.ones((1, 2)))
        with self.assertRaisesRegex(ValueError, "finite"):
            late_interaction_score(np.array([[np.nan, 0.0]]), np.ones((1, 2)))
        with self.assertRaisesRegex(ValueError, "dimensions"):
            late_interaction_score(np.ones((1, 2)), np.ones((1, 3)))
        with self.assertRaisesRegex(ValueError, "exactly"):
            rerank_visual_pages([1, 2], np.ones((1, 2)), {1: np.ones((1, 2))})

    def test_builds_single_physical_page_render_command(self):
        command = build_candidate_page_render_command(
            "/tools/pdftoppm",
            Path("source.pdf"),
            Path("page-0014"),
            14,
            dpi=150,
        )
        self.assertEqual(
            command,
            [
                "/tools/pdftoppm",
                "-png",
                "-singlefile",
                "-f",
                "14",
                "-l",
                "14",
                "-r",
                "150",
                "source.pdf",
                "page-0014",
            ],
        )

    def test_rejects_invalid_render_parameters(self):
        with self.assertRaisesRegex(ValueError, "physical_page"):
            build_candidate_page_render_command("pdftoppm", Path("a.pdf"), Path("out"), 0)
        with self.assertRaisesRegex(ValueError, "dpi"):
            build_candidate_page_render_command(
                "pdftoppm", Path("a.pdf"), Path("out"), 1, dpi=0
            )


if __name__ == "__main__":
    unittest.main()
