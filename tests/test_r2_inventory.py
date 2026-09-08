import tempfile
import unittest
import hashlib
from pathlib import Path

from egdi.r2_inventory import build_r2_inventory, verify_registered_ocr_artifacts


class R2InventoryTests(unittest.TestCase):
    def setUp(self):
        self.benchmark = [
            {"id": "scan::q1", "question": "scan question", "pdf": {"doc_id_str": "scan"}, "answer": {"secret": "ignored"}},
            {"id": "text::q1", "question": "text question", "pdf": {"doc_id_str": "text"}},
        ]
        self.split = {
            "development_tune": {
                "document_ids": ["scan", "text"],
                "question_ids": ["scan::q1", "text::q1"],
            }
        }
        self.pages = {
            "documents": [
                {"doc_id": "scan", "page_count": 3, "status_counts": {"ok": 0, "low_text": 0, "text_layer_missing": 3}},
                {"doc_id": "text", "page_count": 2, "status_counts": {"ok": 2, "low_text": 0, "text_layer_missing": 0}},
            ]
        }
        self.registry = {
            "documents": [
                {"doc_id": "scan", "page_count": 3, "corpus_path": "corpus.jsonl", "corpus_sha256": hashlib.sha256(b"record").hexdigest(), "layout_text_dir": "text", "verification_artifact": "manifest.json"}
            ]
        }

    def test_selects_only_zero_native_text_tune_documents(self):
        result = build_r2_inventory(
            self.benchmark, self.split, self.pages, self.registry
        )
        self.assertEqual(result["document_count"], 1)
        self.assertEqual(result["question_count"], 1)
        self.assertEqual(result["page_count"], 3)
        self.assertEqual(result["ocr_available_document_count"], 1)
        self.assertEqual(result["documents"][0]["doc_id"], "scan")
        self.assertEqual(
            set(result["documents"][0]["questions"][0]),
            {"question_id", "question"},
        )
        self.assertFalse(result["uses_gold_or_answer_labels"])

    def test_marks_unregistered_ocr_as_missing(self):
        result = build_r2_inventory(self.benchmark, self.split, self.pages, {"documents": []})
        self.assertEqual(result["ocr_missing_document_count"], 1)
        self.assertIsNone(result["documents"][0]["ocr"])

    def test_rejects_question_split_drift(self):
        self.split["development_tune"]["question_ids"].append("missing::q1")
        with self.assertRaisesRegex(ValueError, "do not match"):
            build_r2_inventory(self.benchmark, self.split, self.pages, self.registry)

    def test_verifies_registered_artifacts_exist(self):
        result = build_r2_inventory(
            self.benchmark, self.split, self.pages, self.registry
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(FileNotFoundError, "corpus_path"):
                verify_registered_ocr_artifacts(result, root=root)
            (root / "corpus.jsonl").write_text("record", encoding="utf-8")
            (root / "text").mkdir()
            (root / "manifest.json").write_text("{}", encoding="utf-8")
            verify_registered_ocr_artifacts(result, root=root)


if __name__ == "__main__":
    unittest.main()
