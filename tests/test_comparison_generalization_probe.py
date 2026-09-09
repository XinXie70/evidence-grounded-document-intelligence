import json
from pathlib import Path
import tempfile
import unittest

from egdi.comparison_generalization_probe import probe_manifest


class ComparisonGeneralizationProbeTests(unittest.TestCase):
    def manifest(self, page_records):
        return {
            "split": "development_tune",
            "uses_gold_answer": False,
            "uses_gold_evidence_pages": False,
            "cases": [{
                "case_id": "heldout_01", "question_id": "doc::q2", "doc_id": "doc",
                "question": "What is the difference between full-time female and male students?",
                "selector_version": "continued_enrollment_table_v0",
                "candidate_pages": [1], "page_records": page_records,
            }],
        }

    def test_records_expected_selector_rejection_as_unsupported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pages.jsonl").write_text(
                json.dumps({"page": 1, "text": "ordinary page"}) + "\n", encoding="utf-8"
            )
            result = probe_manifest(self.manifest("pages.jsonl"), root=root)
        self.assertEqual(result["summary"]["unsupported_count"], 1)
        self.assertEqual(result["cases"][0]["status"], "unsupported")
        self.assertIn("supported enrolment comparison pattern", result["cases"][0]["reason"])

    def test_rejects_gold_labels_and_locked_split(self):
        manifest = self.manifest("unused.jsonl")
        manifest["uses_gold_answer"] = True
        with self.assertRaisesRegex(ValueError, "uses_gold_answer=false"):
            probe_manifest(manifest, root=Path("."))
        manifest["uses_gold_answer"] = False
        manifest["split"] = "locked_test"
        with self.assertRaisesRegex(ValueError, "development_tune"):
            probe_manifest(manifest, root=Path("."))


if __name__ == "__main__":
    unittest.main()
