import unittest

from egdi.text import PageRecord
from egdi.text_quality import control_character_ratio, has_garbled_native_text


def record(doc_id: str, page: int, text: str) -> PageRecord:
    return PageRecord(
        doc_id=doc_id,
        page=page,
        text=text,
        non_whitespace_chars=sum(not character.isspace() for character in text),
        extraction_status="ok",
    )


class TextQualityTests(unittest.TestCase):
    def test_normal_text_has_no_control_character_signal(self):
        records = [record("doc", 1, "Oven probe and cooking guide")]
        self.assertEqual(control_character_ratio(records), 0.0)
        self.assertFalse(has_garbled_native_text(records))

    def test_observed_embedded_font_pattern_triggers_garbled_signal(self):
        records = [record("doc", 1, "2YHQ\x033UREH\x03&RRNLQJ\x03*XLGH")]
        self.assertGreater(control_character_ratio(records), 0.05)
        self.assertTrue(has_garbled_native_text(records))

    def test_threshold_is_strict(self):
        records = [record("doc", 1, "a" * 19 + "\x03")]
        self.assertEqual(control_character_ratio(records), 0.05)
        self.assertFalse(has_garbled_native_text(records, threshold=0.05))

    def test_empty_text_is_not_mislabeled_as_garbled(self):
        records = [record("doc", 1, "")]
        self.assertEqual(control_character_ratio(records), 0.0)
        self.assertFalse(has_garbled_native_text(records))

    def test_rejects_empty_mixed_document_and_invalid_threshold(self):
        with self.assertRaises(ValueError):
            control_character_ratio([])
        with self.assertRaises(ValueError):
            control_character_ratio([record("a", 1, "x"), record("b", 1, "y")])
        with self.assertRaises(ValueError):
            has_garbled_native_text([record("a", 1, "x")], threshold=1.1)
        with self.assertRaises(TypeError):
            has_garbled_native_text([record("a", 1, "x")], threshold=True)


if __name__ == "__main__":
    unittest.main()
