import unittest

from egdi.multihop_windows import (
    add_non_overlapping_clause_windows,
    split_explicit_clauses,
)


def window(start: int) -> dict:
    return {"pages": [start, start + 1, start + 2], "score": float(start)}


class MultihopWindowTests(unittest.TestCase):
    def test_split_uses_only_explicit_em_dash(self):
        self.assertEqual(
            split_explicit_clauses("Compare the table — locate it on the map?"),
            ["Compare the table", "locate it on the map?"],
        )
        self.assertEqual(
            split_explicit_clauses("A normal question with a comma, but no dash?"),
            ["A normal question with a comma, but no dash?"],
        )

    def test_adds_first_fully_non_overlapping_clause_window(self):
        base = [window(3), window(6), window(18)]
        clause_sets = [
            [window(3), window(6), window(12)],
            [window(4), window(1), window(18)],
        ]
        selected = add_non_overlapping_clause_windows(
            base, clause_sets, maximum_supplemental_windows=1
        )
        self.assertEqual([item["pages"] for item in selected][-1], [12, 13, 14])
        self.assertEqual(selected[-1]["clause_index"], 1)
        self.assertEqual(len(selected), 4)

    def test_no_clause_or_zero_cap_preserves_base_windows(self):
        base = [window(3), window(6)]
        self.assertEqual(add_non_overlapping_clause_windows(base, []), base)
        self.assertEqual(
            add_non_overlapping_clause_windows(
                base, [[window(12)]], maximum_supplemental_windows=0
            ),
            base,
        )

    def test_rejects_empty_clause_and_invalid_cap(self):
        with self.assertRaisesRegex(ValueError, "empty clause"):
            split_explicit_clauses("first — ")
        with self.assertRaisesRegex(ValueError, "non-negative"):
            add_non_overlapping_clause_windows([], [], maximum_supplemental_windows=-1)


if __name__ == "__main__":
    unittest.main()
