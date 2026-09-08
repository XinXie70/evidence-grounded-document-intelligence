import unittest

from egdi.bm25 import PageBm25Index
from egdi.evaluation import evaluate_document, evaluate_question
from egdi.text import build_page_record


class Bm25EvaluationTests(unittest.TestCase):
    def setUp(self):
        records = [
            build_page_record("doc-1", 1, "alpha"),
            build_page_record("doc-1", 2, "beta"),
            build_page_record("doc-1", 3, "alpha beta"),
        ]
        self.index = PageBm25Index(records)
        self.question = {
            "id": "doc-1::q1",
            "question": "alpha",
            "answer": {"is_answerable": True},
            "pdf": {"doc_id_str": "doc-1"},
            "evidences": [{"page": 1}, {"page": 2}],
        }

    def test_connects_ranking_to_scores_at_multiple_k(self):
        result = evaluate_question(self.index, self.question, ks=(1, 3))

        self.assertEqual(result["gold_pages"], [1, 2])
        self.assertEqual(result["retrieved_pages"], [1, 3, 2])
        self.assertEqual(result["scores"]["1"]["any_evidence_recall"], 1.0)
        self.assertEqual(result["scores"]["1"]["complete_evidence_recall"], 0.0)
        self.assertEqual(result["scores"]["1"]["recall"], 0.5)
        self.assertEqual(result["scores"]["3"]["complete_evidence_recall"], 1.0)

    def test_aggregates_questions_at_each_k(self):
        result = evaluate_document(self.index, [self.question], ks=(1, 3))

        self.assertEqual(result["eligible_question_count"], 1)
        self.assertEqual(result["excluded_question_count"], 0)
        self.assertEqual(result["aggregate"]["1"]["question_count"], 1)
        self.assertEqual(result["aggregate"]["1"]["macro"]["recall"], 0.5)
        self.assertEqual(result["aggregate"]["3"]["macro"]["recall"], 1.0)

    def test_reports_unanswerable_question_as_protocol_exclusion(self):
        unanswerable = dict(self.question)
        unanswerable["id"] = "doc-1::unanswerable"
        unanswerable["answer"] = {"is_answerable": False}

        result = evaluate_document(self.index, [self.question, unanswerable], ks=(1,))

        self.assertEqual(result["eligible_question_count"], 1)
        self.assertEqual(result["excluded_question_count"], 1)
        self.assertEqual(
            result["exclusions"],
            [{"question_id": "doc-1::unanswerable", "reason": "unanswerable"}],
        )

    def test_rejects_index_for_a_different_document(self):
        question = dict(self.question)
        question["pdf"] = {"doc_id_str": "other-doc"}

        with self.assertRaises(ValueError):
            evaluate_question(self.index, question, ks=(1,))


if __name__ == "__main__":
    unittest.main()
