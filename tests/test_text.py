import unittest

from egdi.text import (
    build_page_record,
    classify_text_layer,
    normalize_whitespace,
    tokenize_for_bm25,
)


class NormalizeWhitespaceTests(unittest.TestCase):
    def test_collapses_spaces_newlines_and_tabs(self):
        raw = "POPIA defines\n\na child\t as anyone  under the age of 18."
        self.assertEqual(
            normalize_whitespace(raw),
            "POPIA defines a child as anyone under the age of 18.",
        )

    def test_preserves_numbers_case_and_punctuation(self):
        raw = "11\nPOPIA: a child is under 18; Section 3.2."
        self.assertEqual(
            normalize_whitespace(raw),
            "11 POPIA: a child is under 18; Section 3.2.",
        )

    def test_trims_outer_whitespace(self):
        self.assertEqual(normalize_whitespace("  evidence  "), "evidence")

    def test_empty_and_whitespace_only_text(self):
        self.assertEqual(normalize_whitespace(""), "")
        self.assertEqual(normalize_whitespace("\n\t  "), "")

    def test_rejects_non_string_input(self):
        with self.assertRaises(TypeError):
            normalize_whitespace(None)  # type: ignore[arg-type]


class PageRecordTests(unittest.TestCase):
    def test_status_threshold_boundaries(self):
        self.assertEqual(classify_text_layer(0), "text_layer_missing")
        self.assertEqual(classify_text_layer(19), "text_layer_missing")
        self.assertEqual(classify_text_layer(20), "low_text")
        self.assertEqual(classify_text_layer(99), "low_text")
        self.assertEqual(classify_text_layer(100), "ok")

    def test_builds_reversible_page_record(self):
        record = build_page_record("doc-001", 12, "POPIA\n defines  a child under 18.")
        self.assertEqual(record.doc_id, "doc-001")
        self.assertEqual(record.page, 12)
        self.assertEqual(record.text, "POPIA defines a child under 18.")
        self.assertEqual(record.non_whitespace_chars, 26)
        self.assertEqual(record.extraction_status, "low_text")

    def test_empty_scan_is_retained_and_flagged(self):
        record = build_page_record("scan-001", 14, "")
        self.assertEqual(record.text, "")
        self.assertEqual(record.non_whitespace_chars, 0)
        self.assertEqual(record.extraction_status, "text_layer_missing")

    def test_rejects_invalid_identity_and_counts(self):
        with self.assertRaises(ValueError):
            build_page_record("", 1, "text")
        with self.assertRaises(ValueError):
            build_page_record("doc", 0, "text")
        with self.assertRaises(ValueError):
            classify_text_layer(-1)
        with self.assertRaises(TypeError):
            classify_text_layer(True)


class Bm25TokenizerTests(unittest.TestCase):
    def test_casefolds_and_retains_stopwords_and_numbers(self):
        text = "POPIA defines a Child under the age of 18."
        self.assertEqual(
            tokenize_for_bm25(text),
            ["popia", "defines", "a", "child", "under", "the", "age", "of", "18"],
        )

    def test_punctuation_is_a_boundary_while_numbers_are_retained(self):
        text = "Revenue was $52,788,333; ratio: 6.0%."
        self.assertEqual(
            tokenize_for_bm25(text),
            ["revenue", "was", "52", "788", "333", "ratio", "6", "0"],
        )

    def test_repeated_terms_are_retained_for_term_frequency(self):
        self.assertEqual(tokenize_for_bm25("child CHILD child"), ["child", "child", "child"])

    def test_empty_text_has_no_tokens_and_invalid_input_is_rejected(self):
        self.assertEqual(tokenize_for_bm25(""), [])
        with self.assertRaises(TypeError):
            tokenize_for_bm25(None)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
