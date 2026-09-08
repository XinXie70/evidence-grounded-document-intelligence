import unittest

from egdi.page_window import (
    select_anchor_centered_windows,
    select_non_overlapping_windows,
)


class PageWindowTests(unittest.TestCase):
    def test_selects_highest_sum_non_overlapping_windows(self):
        scores = {page: 0.0 for page in range(1, 10)}
        scores.update({2: 3.0, 3: 4.0, 7: 5.0, 8: 5.0})
        selected = select_non_overlapping_windows(
            scores, page_count=9, window_width=3, window_count=2
        )
        self.assertEqual(selected[0]["pages"], [6, 7, 8])
        self.assertEqual(selected[1]["pages"], [1, 2, 3])

    def test_ties_use_lower_start_page(self):
        selected = select_non_overlapping_windows(
            {page: 1.0 for page in range(1, 7)},
            page_count=6,
            window_width=3,
            window_count=1,
        )
        self.assertEqual(selected[0]["start_page"], 1)

    def test_rejects_incomplete_scores_and_invalid_width(self):
        with self.assertRaisesRegex(ValueError, "cover every"):
            select_non_overlapping_windows(
                {1: 1.0}, page_count=2, window_width=1, window_count=1
            )
        with self.assertRaisesRegex(ValueError, "cannot exceed"):
            select_non_overlapping_windows(
                {1: 1.0, 2: 1.0}, page_count=2, window_width=3, window_count=1
            )

    def test_anchor_centered_window_expands_both_sides(self):
        scores = {page: 0.0 for page in range(1, 16)}
        scores[13] = 10.0
        scores[5] = 5.0
        selected = select_anchor_centered_windows(
            scores,
            [13, 5, 9],
            page_count=15,
            seed_top_k=3,
            window_width=3,
            window_count=2,
        )
        self.assertEqual(selected[0]["pages"], [12, 13, 14])
        self.assertEqual(selected[0]["anchor_pages"], [13])

    def test_anchor_centered_requires_odd_width(self):
        with self.assertRaisesRegex(ValueError, "must be odd"):
            select_anchor_centered_windows(
                {page: 1.0 for page in range(1, 7)},
                [1, 2, 3],
                page_count=6,
                seed_top_k=3,
                window_width=2,
                window_count=1,
            )


if __name__ == "__main__":
    unittest.main()
