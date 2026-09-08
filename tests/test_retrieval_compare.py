import unittest

from egdi.retrieval_compare import compare_retrieval_runs


def question(question_id, gold, retrieved, *, evidence_type="table"):
    return {
        "question_id": question_id,
        "question": f"Question {question_id}",
        "doc_id": "doc-a",
        "gold_pages": gold,
        "retrieved_pages": retrieved,
        "slices": {
            "evidence_type": evidence_type,
            "page_span": "multi" if len(gold) > 1 else "single",
            "gold_text_status": "ok",
            "extract_class": "class-test",
        },
    }


class RetrievalComparisonTests(unittest.TestCase):
    def test_reports_complementarity_and_union_candidate_ceiling(self):
        left = {
            "split": "development_tune",
            "per_question": [
                question("q1", [1, 2], [1, 9]),
                question("q2", [3], [3, 8], evidence_type="text"),
            ],
        }
        right = {
            "split": "development_tune",
            "per_question": [
                question("q1", [1, 2], [2, 8]),
                question("q2", [3], [7, 6], evidence_type="text"),
            ],
        }
        result = compare_retrieval_runs(
            left, right, left_label="bm25", right_label="dense", ks=(1, 2)
        )

        at_two = result["comparisons"]["2"]
        self.assertEqual(
            at_two["outcomes"]["complete_evidence_recall"],
            {"both": 0, "left_only": 1, "right_only": 0, "neither": 1},
        )
        self.assertEqual(at_two["union_candidate_pool"]["complete_evidence_recall"], 1.0)
        self.assertEqual(result["per_question"][0]["union_pages"], [1, 9, 2, 8])

    def test_rejects_split_question_and_gold_drift(self):
        base = {
            "split": "development_tune",
            "per_question": [question("q1", [1], [1])],
        }
        with self.assertRaisesRegex(ValueError, "same split"):
            compare_retrieval_runs(
                base,
                {**base, "split": "locked_test"},
                left_label="left",
                right_label="right",
            )
        with self.assertRaisesRegex(ValueError, "identical question IDs"):
            compare_retrieval_runs(
                base,
                {"split": "development_tune", "per_question": [question("q2", [1], [1])]},
                left_label="left",
                right_label="right",
            )
        with self.assertRaisesRegex(ValueError, "gold-page drift"):
            compare_retrieval_runs(
                base,
                {"split": "development_tune", "per_question": [question("q1", [2], [1])]},
                left_label="left",
                right_label="right",
            )


if __name__ == "__main__":
    unittest.main()
