import unittest

from egdi.comparison_scope_audit import audit_comparison_scope


def record(question_id, question, answerable=True):
    return {
        "id": question_id,
        "question": question,
        "answer": {"is_answerable": answerable},
    }


class ComparisonScopeAuditTests(unittest.TestCase):
    def test_counts_only_answerable_development_tune_questions(self):
        benchmark = [
            record("d1", "How many more A than B?"),
            record("d2", "How much less is A than B?"),
            record("d3", "What is the difference between A and B?"),
            record("d4", "How many more A than B?", answerable=False),
            record("test1", "How many more locked A than B?"),
        ]
        manifest = {"development_tune": {"question_ids": ["d1", "d2", "d3", "d4"]}}
        result = audit_comparison_scope(benchmark, manifest)
        self.assertEqual(result["answerable_question_count"], 3)
        self.assertEqual(result["categories"]["strict_more_than"]["count"], 1)
        self.assertEqual(result["coverage"]["safe_directional_extension_candidate_count"], 2)
        serialized = str(result)
        self.assertNotIn("test1", serialized)
        self.assertNotIn("locked", serialized)

    def test_rejects_missing_or_duplicate_tune_ids(self):
        with self.assertRaisesRegex(ValueError, "unique"):
            audit_comparison_scope([], {"development_tune": {"question_ids": ["a", "a"]}})
        with self.assertRaisesRegex(ValueError, "every"):
            audit_comparison_scope([], {"development_tune": {"question_ids": ["a"]}})


if __name__ == "__main__":
    unittest.main()
