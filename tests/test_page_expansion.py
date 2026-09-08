import unittest

from egdi.page_expansion import evaluate_adjacent_expansion, expand_ranked_pages


class PageExpansionTests(unittest.TestCase):
    def test_expands_in_stable_seed_previous_next_order(self):
        self.assertEqual(
            expand_ranked_pages([3, 1], page_count=5, radius=1),
            [3, 2, 4, 1],
        )

    def test_drops_boundaries_and_deduplicates(self):
        self.assertEqual(
            expand_ranked_pages([1, 2, 5], page_count=5, radius=1),
            [1, 2, 3, 5, 4],
        )

    def test_evaluates_gold_only_after_expansion(self):
        retrieval = {
            "split": "development_tune",
            "per_question": [
                {
                    "question_id": "doc::q1",
                    "doc_id": "doc",
                    "gold_pages": [4],
                    "retrieved_pages": [3, 1],
                }
            ],
        }
        result = evaluate_adjacent_expansion(
            retrieval, {"doc": 5}, seed_top_k=2, radius=1
        )
        item = result["per_question"][0]
        self.assertEqual(item["expanded_candidate_pages"], [3, 2, 4, 1])
        self.assertEqual(item["complete_evidence_recall"], 1.0)
        self.assertTrue(result["uses_gold_labels_only_after_candidate_generation"])

    def test_rejects_invalid_pages_and_missing_document_counts(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            expand_ranked_pages([0], page_count=5)
        retrieval = {
            "per_question": [
                {
                    "question_id": "missing::q1",
                    "doc_id": "missing",
                    "gold_pages": [1],
                    "retrieved_pages": [1],
                }
            ]
        }
        with self.assertRaisesRegex(ValueError, "page count"):
            evaluate_adjacent_expansion(retrieval, {}, seed_top_k=1)


if __name__ == "__main__":
    unittest.main()
