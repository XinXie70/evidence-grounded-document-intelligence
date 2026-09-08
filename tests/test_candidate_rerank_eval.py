import unittest

import numpy as np

from egdi.candidate_rerank_eval import evaluate_candidate_rerank
from egdi.text import build_page_record


class FakeEncoder:
    def split_text(self, text, chunk_tokens, overlap_tokens):
        return [text]

    def _vector(self, text):
        lowered = text.casefold()
        return np.array([
            float("alpha" in lowered),
            float("beta" in lowered),
            float("other" in lowered),
        ])

    def encode_passages(self, texts):
        return np.stack([self._vector(text) for text in texts])

    def encode_query(self, query):
        return self._vector(query)


class CandidateRerankEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.corpora = {
            "doc": [
                build_page_record("doc", 1, "other"),
                build_page_record("doc", 2, "alpha evidence"),
                build_page_record("doc", 3, "beta evidence"),
                build_page_record("doc", 4, "other material"),
                build_page_record("doc", 5, "other appendix"),
            ]
        }
        base = {
            "doc_id": "doc",
            "candidate_pages": [1, 2, 3, 4, 5],
            "retrieved_pages": [1, 2, 3, 4, 5],
            "slices": {
                "page_span": "single",
                "gold_text_status": "ok",
                "evidence_type": "text",
                "extract_class": "class1",
            },
        }
        self.run = {
            "split": "development_tune",
            "excluded_question_count": 0,
            "exclusion_reasons": {},
            "per_question": [
                {**base, "question_id": "doc::q1", "question": "alpha", "gold_pages": [2]},
                {**base, "question_id": "doc::q2", "question": "beta", "gold_pages": [3]},
            ],
        }

    def test_reranks_only_candidates_and_aggregates_multiple_k(self):
        result = evaluate_candidate_rerank(
            self.run,
            self.corpora,
            FakeEncoder(),
            candidate_depth=5,
            ks=(1, 2, 5),
        )

        self.assertEqual(result["eligible_question_count"], 2)
        self.assertEqual(result["per_question"][0]["retrieved_pages"][0], 2)
        self.assertEqual(result["per_question"][1]["retrieved_pages"][0], 3)
        self.assertEqual(
            result["aggregate"]["1"]["macro"]["complete_evidence_recall"], 1.0
        )

    def test_rejects_non_tune_short_candidates_and_missing_corpus(self):
        wrong_split = {**self.run, "split": "locked_test"}
        with self.assertRaisesRegex(ValueError, "development_tune"):
            evaluate_candidate_rerank(wrong_split, self.corpora, FakeEncoder(), candidate_depth=5)
        short = {**self.run, "per_question": [{**self.run["per_question"][0], "retrieved_pages": [1]}]}
        with self.assertRaisesRegex(ValueError, "too short"):
            evaluate_candidate_rerank(
                short, self.corpora, FakeEncoder(), candidate_depth=5, ks=(1, 5)
            )
        with self.assertRaisesRegex(ValueError, "no verified corpus"):
            evaluate_candidate_rerank(
                self.run, {}, FakeEncoder(), candidate_depth=5, ks=(1, 5)
            )


if __name__ == "__main__":
    unittest.main()
