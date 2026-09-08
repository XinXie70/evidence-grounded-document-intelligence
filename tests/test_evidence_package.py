import tempfile
import unittest
from pathlib import Path

from egdi.corpus import write_page_records_jsonl
from egdi.evidence_package import (
    LAYOUT_TEXT_REPRESENTATION,
    build_evidence_package,
    build_real_retrieval_record,
    load_layout_texts,
    write_evidence_outputs,
)
from egdi.text import build_page_record


class EvidencePackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.records = [
            build_page_record("doc-a", 1, "ordinary unrelated material " * 5),
            build_page_record("doc-a", 2, "rare evidence answer material " * 5),
            build_page_record("doc-a", 3, "other material " * 5),
        ]
        self.corpus = self.root / "page_records.jsonl"
        write_page_records_jsonl(self.corpus, self.records)

    def tearDown(self):
        self.temporary.cleanup()

    def test_package_preserves_rank_score_text_and_label_free_metadata(self):
        package = build_evidence_package(
            "doc-a::q1",
            "Which page contains rare evidence?",
            self.records,
            corpus_path=self.corpus,
            corpus_kind="ocr_text",
            top_k=2,
        )
        self.assertEqual(package["evidence_pages"][0], 2)
        self.assertEqual(package["evidence"][0]["rank"], 1)
        self.assertGreater(package["evidence"][0]["score"], 0)
        self.assertEqual(package["evidence"][0]["text"], self.records[1].text)
        self.assertFalse(package["uses_gold_or_answer_labels"])
        self.assertNotIn("gold_pages", package)
        self.assertNotIn("answer", package)
        self.assertNotIn("evidences", package)

    def test_reasoning_adapter_uses_same_order_and_hides_scores(self):
        package = build_evidence_package(
            "doc-a::q1",
            "Which page contains rare evidence?",
            self.records,
            corpus_path=self.corpus,
            corpus_kind="native_text",
            top_k=2,
        )
        reasoning = build_real_retrieval_record(package, self.records)
        self.assertEqual(reasoning["evidence_pages"], package["evidence_pages"])
        evidence = reasoning["model_input"]["evidence"]
        self.assertEqual([item["page"] for item in evidence], package["evidence_pages"])
        self.assertTrue(all(set(item) == {"page", "text"} for item in evidence))

    def test_reasoning_adapter_can_preserve_ocr_line_structure(self):
        package = build_evidence_package(
            "doc-a::q1",
            "Which page contains rare evidence?",
            self.records,
            corpus_path=self.corpus,
            corpus_kind="ocr_text",
            top_k=2,
        )
        layout_text = {
            package["evidence_pages"][0]: "Item one\nItem two\nItem three",
            package["evidence_pages"][1]: "Other\nmaterial",
        }
        reasoning = build_real_retrieval_record(
            package, self.records, evidence_text_by_page=layout_text
        )
        self.assertEqual(
            reasoning["evidence_text_representation"], LAYOUT_TEXT_REPRESENTATION
        )
        self.assertEqual(
            reasoning["model_input"]["evidence"][0]["text"],
            "Item one\nItem two\nItem three",
        )

    def test_load_layout_texts_preserves_newlines_and_records_hashes(self):
        text_dir = self.root / "text"
        text_dir.mkdir()
        page_path = text_dir / "page-02.txt"
        page_path.write_text("Item one\nItem two\n", encoding="utf-8")
        texts, audit = load_layout_texts(text_dir, [2])
        self.assertEqual(texts[2], "Item one\nItem two")
        self.assertEqual(audit[0]["page"], 2)
        self.assertEqual(len(audit[0]["sha256"]), 64)

        with self.assertRaisesRegex(FileNotFoundError, "physical page 3"):
            load_layout_texts(text_dir, [3])

        (text_dir / "page-0002.txt").write_text("duplicate", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate.*page 2"):
            load_layout_texts(text_dir, [2])

    def test_atomic_writer_publishes_both_files_and_refuses_overwrite(self):
        package = build_evidence_package(
            "doc-a::q1",
            "Which page contains rare evidence?",
            self.records,
            corpus_path=self.corpus,
            corpus_kind="native_text",
            top_k=1,
        )
        reasoning = build_real_retrieval_record(package, self.records)
        output = self.root / "output"
        summary = write_evidence_outputs(output, package, reasoning)
        self.assertTrue((output / "evidence_package.json").is_file())
        self.assertTrue((output / "real_retrieval.json").is_file())
        self.assertTrue((output / "manifest.json").is_file())
        self.assertEqual(summary["evidence_pages"], package["evidence_pages"])
        with self.assertRaisesRegex(FileExistsError, "refusing to overwrite"):
            write_evidence_outputs(output, package, reasoning)

    def test_rejects_invalid_document_page_and_top_k_boundaries(self):
        mixed = [self.records[0], build_page_record("doc-b", 2, "text")]
        with self.assertRaisesRegex(ValueError, "one document"):
            build_evidence_package(
                "q1", "question", mixed, corpus_path=self.corpus, corpus_kind="native_text"
            )
        out_of_order = [self.records[1], self.records[0]]
        with self.assertRaisesRegex(ValueError, "sequential"):
            build_evidence_package(
                "q1",
                "question",
                out_of_order,
                corpus_path=self.corpus,
                corpus_kind="native_text",
            )
        with self.assertRaisesRegex(ValueError, "top_k"):
            build_evidence_package(
                "q1",
                "question",
                self.records,
                corpus_path=self.corpus,
                corpus_kind="native_text",
                top_k=4,
            )


if __name__ == "__main__":
    unittest.main()
