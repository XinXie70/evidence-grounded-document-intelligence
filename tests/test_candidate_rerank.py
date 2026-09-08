import unittest

import numpy as np

from egdi.candidate_rerank import build_reranked_reasoning_input
from egdi.reasoning_inputs import PILOT_INSTRUCTIONS_V1, RESPONSE_SCHEMA


class FakeEncoder:
    def split_text(self, text, chunk_tokens, overlap_tokens):
        return [text]

    @staticmethod
    def _vector(text):
        lowered = text.casefold()
        return np.array([
            float("personal care" in lowered),
            float("housework" in lowered),
            float("irrelevant" in lowered),
        ])

    def encode_passages(self, texts):
        return np.stack([self._vector(text) for text in texts])

    def encode_query(self, query):
        return self._vector(query)


class CandidateRerankTests(unittest.TestCase):
    def setUp(self):
        evidence = [
            {"page": 8, "text": "irrelevant introductory material"},
            {"page": 21, "text": "Males personal care 10.8 hours"},
            {"page": 55, "text": "Females housework total 287.4 minutes"},
        ]
        self.source = {
            "schema_version": 1,
            "question_id": "doc::q1",
            "doc_id": "doc",
            "condition": "real_retrieval",
            "evidence_pages": [8, 21, 55],
            "page_budget": 3,
            "retriever": "hybrid_rrf_bm25_dense_v0",
            "model_input": {
                "instructions": PILOT_INSTRUCTIONS_V1,
                "question": "Compare males personal care with females housework.",
                "evidence": evidence,
                "response_schema": RESPONSE_SCHEMA,
            },
        }

    def test_selects_pages_by_question_but_sends_full_page_text(self):
        result = build_reranked_reasoning_input(self.source, FakeEncoder(), top_k=2)

        self.assertEqual(result["evidence_pages"], [21, 55])
        self.assertEqual(
            [item["page"] for item in result["model_input"]["evidence"]],
            [21, 55],
        )
        self.assertEqual(
            result["model_input"]["evidence"][1]["text"],
            "Females housework total 287.4 minutes",
        )
        self.assertNotIn("score", result["model_input"])
        self.assertEqual(
            result["candidate_rerank"]["reasoning_evidence_scope"],
            "full_selected_physical_pages",
        )

    def test_rejects_invalid_and_inconsistent_candidate_pools(self):
        with self.assertRaises(ValueError):
            build_reranked_reasoning_input(self.source, FakeEncoder(), top_k=0)
        broken = {**self.source, "evidence_pages": [8, 55, 21]}
        with self.assertRaisesRegex(ValueError, "order"):
            build_reranked_reasoning_input(broken, FakeEncoder(), top_k=2)


if __name__ == "__main__":
    unittest.main()
