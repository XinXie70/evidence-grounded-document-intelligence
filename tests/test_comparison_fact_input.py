import json
from pathlib import Path
import tempfile
import unittest

from egdi.comparison_fact_input import build_fact_input


class ComparisonFactInputTests(unittest.TestCase):
    def test_builds_ordered_label_free_retrieval_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pages.jsonl"
            path.write_text("\n".join([
                json.dumps({"page": 2, "text": "second"}),
                json.dumps({"page": 1, "text": "first"})]) + "\n", encoding="utf-8")
            result = build_fact_input(
                {"question_id": "d::q", "doc_id": "d", "question": "Difference?",
                 "candidate_pages": [1, 2], "retrieval_method": "method_top2"}, path)
        self.assertEqual([item["page"] for item in result["model_input"]["evidence"]], [1, 2])
        serialized = json.dumps(result["model_input"])
        self.assertNotIn("answer_text", serialized)
        self.assertNotIn("gold", serialized)
        self.assertEqual(result["retrieval_method"], "method_top2")

    def test_rejects_retrieval_top_k_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pages.jsonl"
            path.write_text(json.dumps({"page": 1, "text": "one"}) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "top-k"):
                build_fact_input(
                    {"question_id": "d::q", "doc_id": "d", "question": "Difference?",
                     "candidate_pages": [1], "retrieval_method": "method_top3"}, path)


if __name__ == "__main__":
    unittest.main()
