import json
import unittest
from pathlib import Path


class EndToEndFixtureTests(unittest.TestCase):
    def test_question_document_page_bbox_fact_answer_chain(self):
        path = Path(__file__).parents[1] / "data" / "fixtures" / "end_to_end_synthetic.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(record["question"])
        self.assertTrue(record["pdf"]["doc_id_str"])
        evidence = record["evidences"][0]
        self.assertGreaterEqual(evidence["page"], 1)
        self.assertEqual(len(evidence["bbox"]), 4)
        self.assertEqual(record["facts"][0]["evidence_local_id"], evidence["local_id"])
        self.assertTrue(record["answer"]["answer_text"])
        self.assertIn("Synthetic", record["fixture_notice"])


if __name__ == "__main__":
    unittest.main()
