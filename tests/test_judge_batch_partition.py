import unittest

from egdi.judge_batch_partition import build_batch_manifest, partition_judge_requests


class JudgeBatchPartitionTests(unittest.TestCase):
    def test_partitions_individual_requests_without_exceeding_target(self):
        plan = [
            {"pilot_id": "p1", "judge_type": "semantic", "conservative_cost_usd": 0.4},
            {"pilot_id": "p1", "judge_type": "support", "conservative_cost_usd": 0.4},
            {"pilot_id": "p2", "judge_type": "semantic", "conservative_cost_usd": 0.4},
        ]
        batches = partition_judge_requests(plan, target_usd=0.8)
        self.assertEqual([len(batch) for batch in batches], [2, 1])
        self.assertTrue(all(sum(x["conservative_cost_usd"] for x in batch) <= 0.8 for batch in batches))

    def test_rejects_invalid_costs_and_oversized_request(self):
        with self.assertRaisesRegex(ValueError, "positive"):
            partition_judge_requests([], target_usd=0)
        with self.assertRaisesRegex(ValueError, "exceeds"):
            partition_judge_requests(
                [{"pilot_id": "p", "judge_type": "support", "conservative_cost_usd": 1.1}],
                target_usd=1.0,
            )

    def test_builds_one_request_per_projected_case(self):
        parent = {
            "split": "locked_test",
            "cases": [{
                "pilot_id": "p1", "question_id": "q1", "doc_id": "d1",
                "semantic_input": {"path": "s.json", "sha256": "a" * 64},
                "support_input": {"path": "g.json", "sha256": "b" * 64},
            }],
        }
        request = {"pilot_id": "p1", "judge_type": "support"}
        result = build_batch_manifest(parent, [request], parent_sha256="c" * 64, batch_id="batch_01")
        self.assertEqual(result["judge_request_count"], 1)
        self.assertNotIn("semantic_input", result["cases"][0])
        self.assertEqual(result["cases"][0]["support_input"]["path"], "g.json")


if __name__ == "__main__":
    unittest.main()
