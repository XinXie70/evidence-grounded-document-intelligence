import json
import tempfile
import unittest
from pathlib import Path

from egdi.corpus import write_page_records_jsonl
from egdi.io import sha256_file
from egdi.r2_evaluate import load_registered_r2_corpora, select_inventory_questions
from egdi.text import build_page_record


class R2EvaluateTests(unittest.TestCase):
    def test_selects_exact_inventory_order(self):
        tune = [
            {"id": "a::q1"},
            {"id": "b::q1"},
        ]
        inventory = {
            "split": "development_tune",
            "question_count": 2,
            "documents": [
                {"questions": [{"question_id": "b::q1"}, {"question_id": "a::q1"}]}
            ],
        }
        self.assertEqual(
            [item["id"] for item in select_inventory_questions(tune, inventory)],
            ["b::q1", "a::q1"],
        )

    def test_rejects_inventory_question_drift(self):
        inventory = {
            "split": "development_tune",
            "question_count": 1,
            "documents": [{"questions": [{"question_id": "missing::q1"}]}],
        }
        with self.assertRaisesRegex(ValueError, "absent from tune"):
            select_inventory_questions([{"id": "a::q1"}], inventory)

    def test_loads_only_checksum_verified_sequential_corpus(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            corpus = root / "scan.jsonl"
            records = [
                build_page_record("scan", 1, "alpha"),
                build_page_record("scan", 2, "beta"),
            ]
            write_page_records_jsonl(corpus, records)
            registry = {
                "documents": [
                    {
                        "doc_id": "scan",
                        "page_count": 2,
                        "corpus_path": "scan.jsonl",
                        "corpus_sha256": sha256_file(corpus),
                    }
                ]
            }
            loaded = load_registered_r2_corpora(registry, ["scan"], root=root)
            self.assertEqual(loaded["scan"], records)
            registry["documents"][0]["corpus_sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                load_registered_r2_corpora(registry, ["scan"], root=root)


if __name__ == "__main__":
    unittest.main()
