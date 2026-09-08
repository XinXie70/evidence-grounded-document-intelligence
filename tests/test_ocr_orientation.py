import unittest

from egdi.ocr_orientation import (
    needs_orientation_retry,
    select_best_orientation,
    summarize_tesseract_tsv,
)


HEADER = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"


def tsv(*rows: tuple[str, str]) -> str:
    body = "".join(
        f"5\t1\t1\t1\t1\t{index}\t0\t0\t1\t1\t{confidence}\t{text}\n"
        for index, (confidence, text) in enumerate(rows, start=1)
    )
    return HEADER + body


class OcrOrientationTests(unittest.TestCase):
    def test_summary_ignores_empty_and_negative_confidence_rows(self):
        text = tsv(("-1", "structure"), ("90", "clear"), ("70", "word"), ("99", ""))
        summary = summarize_tesseract_tsv(text)
        self.assertEqual(summary["word_count"], 2)
        self.assertEqual(summary["mean_confidence"], 80.0)
        self.assertEqual(summary["confidence_mass"], 160.0)
        self.assertEqual(summary["high_confidence_word_count"], 1)

    def test_selects_orientation_with_greater_confidence_mass(self):
        result = select_best_orientation(
            {
                0: tsv(("20", "noise"), ("30", "text")),
                180: tsv(("90", "bloodline"), ("95", "relation")),
            },
            allowed_rotations=(0, 180),
        )
        self.assertEqual(result["selected_rotation_degrees_clockwise"], 180)
        self.assertFalse(result["uses_gold_or_answer_labels"])

    def test_tie_prefers_configured_rotation_order(self):
        result = select_best_orientation(
            {0: tsv(("90", "word")), 180: tsv(("90", "word"))},
            allowed_rotations=(0, 180),
        )
        self.assertEqual(result["selected_rotation_degrees_clockwise"], 0)

    def test_retry_trigger_uses_strict_frozen_threshold(self):
        self.assertTrue(
            needs_orientation_retry({"mean_confidence": 35.73})
        )
        self.assertFalse(
            needs_orientation_retry({"mean_confidence": 40.0})
        )
        self.assertFalse(
            needs_orientation_retry({"mean_confidence": 84.2})
        )

    def test_retry_trigger_validates_threshold_and_summary(self):
        with self.assertRaisesRegex(ValueError, "between 0 and 100"):
            needs_orientation_retry(
                {"mean_confidence": 35.0}, mean_confidence_threshold=101
            )
        with self.assertRaisesRegex(ValueError, "numeric mean_confidence"):
            needs_orientation_retry({"word_count": 10})

    def test_rejects_missing_candidate_and_invalid_tsv(self):
        with self.assertRaisesRegex(ValueError, "exactly match"):
            select_best_orientation(
                {0: tsv(("90", "word"))}, allowed_rotations=(0, 180)
            )
        with self.assertRaisesRegex(ValueError, "text and conf"):
            summarize_tesseract_tsv("other\nvalue\n")


if __name__ == "__main__":
    unittest.main()
