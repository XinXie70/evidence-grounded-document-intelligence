import tempfile
import unittest
from pathlib import Path

from egdi.corpus import read_page_records_jsonl, write_page_records_jsonl
from egdi.text import build_page_record


class PageRecordJsonlTests(unittest.TestCase):
    def test_round_trip_preserves_order_content_and_identity(self):
        records = [
            build_page_record("doc-001", 1, "First  page"),
            build_page_record("doc-001", 2, ""),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pages.jsonl"
            count = write_page_records_jsonl(path, records)
            self.assertEqual(count, 2)
            self.assertEqual(read_page_records_jsonl(path), records)
            self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), 2)

    def test_blank_jsonl_line_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pages.jsonl"
            path.write_text("\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "blank JSONL line at 1"):
                read_page_records_jsonl(path)


if __name__ == "__main__":
    unittest.main()
