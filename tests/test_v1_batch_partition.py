import unittest

from egdi.v1_batch_partition import partition_cases


class V1BatchPartitionTests(unittest.TestCase):
    def test_preserves_order_and_keeps_local_abstention(self):
        cases = [{"question_id": value} for value in ("q1", "q2", "q3", "q4")]
        plan = [
            {"question_id": "q1", "conservative_cost_usd": 0.4},
            {"question_id": "q2", "conservative_cost_usd": 0.4},
            {"question_id": "q4", "conservative_cost_usd": 0.4},
        ]
        batches = partition_cases({"cases": cases}, plan, target_usd=0.8)
        self.assertEqual([[case["question_id"] for case in batch] for batch in batches], [["q1", "q2", "q3"], ["q4"]])

    def test_rejects_invalid_target_and_oversized_request(self):
        with self.assertRaisesRegex(ValueError, "positive"):
            partition_cases({"cases": []}, [], target_usd=0)
        with self.assertRaisesRegex(ValueError, "single request"):
            partition_cases(
                {"cases": [{"question_id": "q1"}]},
                [{"question_id": "q1", "conservative_cost_usd": 1.1}],
                target_usd=1.0,
            )


if __name__ == "__main__":
    unittest.main()
