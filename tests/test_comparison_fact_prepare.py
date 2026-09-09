import json
import tempfile
import unittest
from pathlib import Path

from egdi.comparison_fact_prepare import prepare_inputs
from egdi.io import write_json


class ComparisonFactPrepareTests(unittest.TestCase):
    def test_prepares_all_selected_cases_and_manifest_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pages = root / "pages.jsonl"
            pages.write_text(json.dumps({"page": 1, "text": "A 10 B 4"}) + "\n")
            selection = {
                "case_count": 1,
                "leakage_controls": {"uses_gold_answer": False,
                                     "uses_gold_evidence_pages": False},
                "cases": [{
                    "case_id": "validation_01", "question_id": "d::q", "doc_id": "d",
                    "question": "What is the difference between A and B?",
                    "candidate_pages": [1], "retrieval_method": "rrf_top1",
                    "page_records": str(pages), "uses_gold_answer": False,
                    "uses_gold_evidence_pages": False,
                }],
            }
            manifest = prepare_inputs(selection, output_dir=root / "prepared")
            input_path = Path(manifest["cases"][0]["input_path"])
            self.assertTrue(input_path.is_file())
            prepared = json.loads(input_path.read_text())
            self.assertEqual(prepared["evidence_pages"], [1])
            self.assertEqual(len(manifest["cases"][0]["input_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
