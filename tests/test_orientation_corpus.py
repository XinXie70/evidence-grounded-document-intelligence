import tempfile
import unittest
from pathlib import Path

from egdi.corpus import read_page_records_jsonl, write_page_records_jsonl
from egdi.io import write_json
from egdi.orientation_corpus import build_orientation_recovered_corpus
from egdi.text import build_page_record


class OrientationCorpusTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.records = [
            build_page_record("doc-a", 1, "Original page one"),
            build_page_record("doc-a", 2, "Upside down noise"),
            build_page_record("doc-a", 3, "Original page three"),
        ]
        self.corpus = self.root / "baseline.jsonl"
        write_page_records_jsonl(self.corpus, self.records)
        self.text_dir = self.root / "baseline-text"
        self.text_dir.mkdir()
        for record in self.records:
            (self.text_dir / f"page-{record.page:02d}.txt").write_text(
                record.text + "\n", encoding="utf-8"
            )
        self.recovered_text = self.root / "recovered-page-2.txt"
        self.recovered_text.write_text(
            "Bloodline Relation Information\nExample father of 11 and 12\n",
            encoding="utf-8",
        )
        self.selection = self.root / "selection.json"
        write_json(
            self.selection,
            {
                "selected_rotation_degrees_clockwise": 180,
                "uses_gold_or_answer_labels": False,
            },
        )
        self.recoveries = [
            {
                "page": 2,
                "text_path": str(self.recovered_text),
                "selection_path": str(self.selection),
            }
        ]

    def tearDown(self):
        self.temporary.cleanup()

    def test_replaces_only_selected_page_and_preserves_layout_files(self):
        output = self.root / "derived"
        manifest = build_orientation_recovered_corpus(
            self.corpus, self.text_dir, self.recoveries, output
        )
        derived = read_page_records_jsonl(output / "page_records.jsonl")
        self.assertEqual(manifest["changed_pages"], [2])
        self.assertEqual(derived[0], self.records[0])
        self.assertIn("Bloodline Relation", derived[1].text)
        self.assertEqual(derived[2], self.records[2])
        self.assertEqual(
            (output / "text/page-0001.txt").read_text(encoding="utf-8"),
            "Original page one\n",
        )
        self.assertFalse(manifest["uses_gold_or_answer_labels"])

    def test_refuses_overwrite_and_duplicate_recovery(self):
        output = self.root / "existing"
        output.mkdir()
        with self.assertRaisesRegex(FileExistsError, "refusing to overwrite"):
            build_orientation_recovered_corpus(
                self.corpus, self.text_dir, self.recoveries, output
            )
        with self.assertRaisesRegex(ValueError, "duplicate"):
            build_orientation_recovered_corpus(
                self.corpus,
                self.text_dir,
                self.recoveries * 2,
                self.root / "duplicate",
            )

    def test_rejects_selection_that_is_not_explicitly_label_free(self):
        write_json(
            self.selection,
            {"selected_rotation_degrees_clockwise": 180},
        )
        with self.assertRaisesRegex(ValueError, "label-free"):
            build_orientation_recovered_corpus(
                self.corpus,
                self.text_dir,
                self.recoveries,
                self.root / "invalid",
            )


if __name__ == "__main__":
    unittest.main()
