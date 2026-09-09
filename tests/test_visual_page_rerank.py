import unittest

from egdi.visual_page_rerank import (
    page_matches_visual_cue,
    rerank_visual_candidates,
)


def signal(*, images=0, tables=0, vectors=0):
    return {
        "raster_image_count": images,
        "detected_table_count": tables,
        "vector_object_count": vectors,
    }


class VisualPageRerankTests(unittest.TestCase):
    def test_table_cue_uses_table_detection_not_generic_images(self):
        self.assertTrue(page_matches_visual_cue("table", signal(tables=1)))
        self.assertFalse(page_matches_visual_cue("table", signal(images=2, vectors=9)))

    def test_image_cue_uses_raster_images(self):
        self.assertTrue(page_matches_visual_cue("image", signal(images=1)))
        self.assertFalse(page_matches_visual_cue("illustration", signal(vectors=20)))

    def test_chart_family_accepts_raster_or_vector_content(self):
        self.assertTrue(page_matches_visual_cue("chart", signal(vectors=1)))
        self.assertTrue(page_matches_visual_cue("map", signal(images=1)))
        self.assertFalse(page_matches_visual_cue("graph", signal()))

    def test_moves_preferred_pages_first_and_preserves_rrf_order(self):
        candidates = [8, 2, 7, 4, 9]
        signals = {
            8: signal(),
            2: signal(tables=1),
            7: signal(tables=2),
            4: signal(),
            9: signal(tables=1),
        }
        self.assertEqual(
            rerank_visual_candidates(candidates, "table", signals),
            [2, 7, 9, 8, 4],
        )

    def test_rejects_missing_pages_bad_counts_and_unknown_cues(self):
        with self.assertRaisesRegex(ValueError, "exactly"):
            rerank_visual_candidates([1, 2], "table", {1: signal()})
        with self.assertRaisesRegex(ValueError, "non-negative"):
            page_matches_visual_cue("table", signal(tables=-1))
        with self.assertRaisesRegex(ValueError, "unsupported"):
            page_matches_visual_cue("photo", signal(images=1))


if __name__ == "__main__":
    unittest.main()
