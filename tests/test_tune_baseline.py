import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from egdi.corpus import write_page_records_jsonl
from egdi.io import sha256_file
from egdi.text import build_page_record
from egdi.tune_baseline import evaluate_tune, load_verified_corpora


class TuneBaselineTests(unittest.TestCase):
    def setUp(self):
        self.corpora = {
            "doc-a": [
                build_page_record("doc-a", 1, "alpha " * 30),
                build_page_record("doc-a", 2, "noise " * 30),
            ],
            "doc-b": [
                build_page_record("doc-b", 1, ""),
                build_page_record("doc-b", 2, "beta " * 30),
            ],
        }

    @staticmethod
    def question(question_id, doc_id, text, pages, *, answerable=True):
        return {
            "id": question_id,
            "question": text,
            "answer": {"is_answerable": answerable},
            "pdf": {"doc_id_str": doc_id},
            "evidences": [
                {"page": page, "element_type": "text"} for page in pages
            ],
            "extract_class": "class-test",
        }

    def test_aggregates_documents_exclusions_and_predefined_slices(self):
        questions = [
            self.question("doc-a::q1", "doc-a", "alpha", [1]),
            self.question("doc-a::q2", "doc-a", "alpha", [1, 2]),
            self.question("doc-b::q1", "doc-b", "beta", [2]),
            self.question("doc-b::q2", "doc-b", "beta", [1]),
            self.question("doc-b::q3", "doc-b", "beta", [], answerable=False),
        ]

        result = evaluate_tune(questions, self.corpora, ks=(1, 2))

        self.assertEqual(result["corpus_document_count"], 2)
        self.assertEqual(result["evaluated_document_count"], 2)
        self.assertEqual(result["question_count"], 5)
        self.assertEqual(result["eligible_question_count"], 4)
        self.assertEqual(result["excluded_question_count"], 1)
        self.assertEqual(result["exclusion_reasons"], {"unanswerable": 1})
        self.assertEqual(
            result["aggregate"]["1"]["macro"]["any_evidence_recall"], 0.75
        )
        self.assertEqual(
            result["slices"]["page_span"]["multi"]["2"]["macro"]["recall"], 1.0
        )
        self.assertEqual(
            result["slices"]["gold_text_status"]["text_layer_missing"]["1"]
            ["macro"]["recall"],
            0.0,
        )

    def test_rejects_question_without_a_document_corpus(self):
        question = self.question("missing::q1", "missing", "alpha", [1])
        with self.assertRaisesRegex(ValueError, "no Page Record corpus"):
            evaluate_tune([question], self.corpora, ks=(1,))

    def test_verified_corpus_loader_rejects_checksum_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            corpus_dir = root / "corpora"
            corpus_dir.mkdir()
            path = corpus_dir / "doc-a.jsonl"
            write_page_records_jsonl(path, self.corpora["doc-a"])
            manifest = {
                "split": "development_tune",
                "documents": [
                    {
                        "doc_id": "doc-a",
                        "page_count": 2,
                        "output_jsonl_sha256": "0" * 64,
                        "status_counts": {
                            "ok": 2,
                            "low_text": 0,
                            "text_layer_missing": 0,
                        },
                    }
                ],
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                load_verified_corpora(manifest_path, corpus_dir, ["doc-a"])

            manifest["documents"][0]["output_jsonl_sha256"] = sha256_file(path)
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            loaded = load_verified_corpora(manifest_path, corpus_dir, ["doc-a"])
            self.assertEqual(loaded["doc-a"], self.corpora["doc-a"])


if __name__ == "__main__":
    unittest.main()
