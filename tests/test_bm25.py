import unittest

from egdi.bm25 import PageBm25Index, prepare_query_tokens
from egdi.text import build_page_record


class PageBm25IndexTests(unittest.TestCase):
    def setUp(self):
        self.records = [
            build_page_record("doc", 1, "apple banana common"),
            build_page_record("doc", 2, "banana banana common"),
            build_page_record("doc", 3, "rare evidence common"),
            build_page_record("doc", 4, ""),
        ]
        self.index = PageBm25Index(self.records)

    def test_exact_rare_term_ranks_matching_page_first(self):
        results = self.index.search("rare evidence", top_k=4)
        self.assertEqual(results[0].page, 3)
        self.assertGreater(results[0].score, results[1].score)

    def test_term_frequency_affects_ranking(self):
        results = self.index.search("banana", top_k=2)
        self.assertEqual([result.page for result in results], [2, 1])

    def test_empty_page_is_retained_with_zero_score(self):
        results = self.index.search("missing", top_k=4)
        page_four = next(result for result in results if result.page == 4)
        self.assertEqual(page_four.score, 0.0)
        self.assertEqual(page_four.extraction_status, "text_layer_missing")

    def test_ties_are_deterministic_by_page(self):
        results = self.index.search("unknown", top_k=4)
        self.assertEqual([result.page for result in results], [1, 2, 3, 4])

    def test_empty_query_returns_no_results(self):
        self.assertEqual(self.index.search("", top_k=3), [])

    def test_query_token_deduplication_preserves_first_occurrence_order(self):
        self.assertEqual(
            prepare_query_tokens("Beta alpha beta ALPHA gamma", "deduplicate_preserve_order"),
            ["beta", "alpha", "gamma"],
        )

    def test_default_query_policy_retains_repetitions(self):
        self.assertEqual(
            prepare_query_tokens("Beta beta ALPHA"),
            ["beta", "beta", "alpha"],
        )

    def test_deduplicated_query_policy_changes_repeated_term_weight(self):
        repeated = PageBm25Index(self.records).search("banana banana rare", top_k=4)
        deduplicated = PageBm25Index(
            self.records,
            query_token_policy="deduplicate_preserve_order",
        ).search("banana banana rare", top_k=4)
        self.assertNotEqual(
            [result.page for result in repeated],
            [result.page for result in deduplicated],
        )

    def test_rejects_invalid_index_and_search_parameters(self):
        with self.assertRaises(ValueError):
            PageBm25Index([])
        with self.assertRaises(ValueError):
            PageBm25Index(self.records, k1=0)
        with self.assertRaises(ValueError):
            PageBm25Index(self.records, b=1.1)
        with self.assertRaisesRegex(ValueError, "query token policy"):
            PageBm25Index(self.records, query_token_policy="unknown")
        with self.assertRaises(ValueError):
            self.index.search("query", top_k=0)


if __name__ == "__main__":
    unittest.main()
