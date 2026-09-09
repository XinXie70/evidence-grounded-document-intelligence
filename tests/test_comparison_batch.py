import json
from pathlib import Path
import tempfile
import unittest

from egdi.comparison_batch import run_manifest


class ComparisonBatchTests(unittest.TestCase):
    def selection(self, value_a="7", value_b="2"):
        def fact(topic, value, page):
            return {"topic": topic, "value": value, "unit": "steps", "pages": [page],
                    "marker_style": "numbered", "observed_numbers": [1],
                    "selection_basis": "topic_then_sequence"}
        return {"question_id": "doc::q1", "doc_id": "doc",
                "question": "How many more steps does A have than B?",
                "selector_version": "list_count_selector_v1_excludes_reference_sections",
                "selected_facts": [fact("A", value_a, 1), fact("B", value_b, 2)],
                "uses_gold_answer": False, "uses_gold_evidence_pages": False}

    def test_runs_two_cases_through_one_interface(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, data in (("one.json", self.selection()),
                               ("two.json", self.selection("3", "8"))):
                (root / name).write_text(json.dumps(data), encoding="utf-8")
            result = run_manifest(
                {"split": "development_tune", "entries": [
                    {"case_id": "one", "selection": "one.json"},
                    {"case_id": "two", "selection": "two.json"}]}, root=root)
        self.assertEqual(result["summary"]["processed_count"], 2)
        self.assertEqual(result["records"][0]["deterministic_comparison"]["magnitude"], "5")
        self.assertEqual(result["records"][1]["deterministic_comparison"]["direction"], "fewer")

    def test_rejects_locked_split_and_duplicate_ids(self):
        with self.assertRaisesRegex(ValueError, "development_tune"):
            run_manifest({"split": "locked_test", "entries": [{}]}, root=Path("."))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "one.json").write_text(json.dumps(self.selection()), encoding="utf-8")
            manifest = {"split": "development_tune", "entries": [
                {"case_id": "same", "selection": "one.json"},
                {"case_id": "same", "selection": "one.json"}]}
            with self.assertRaisesRegex(ValueError, "unique"):
                run_manifest(manifest, root=root)


if __name__ == "__main__":
    unittest.main()
