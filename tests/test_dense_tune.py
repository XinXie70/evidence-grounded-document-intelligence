import unittest

import numpy as np

from egdi.dense_tune import _validated_choice, evaluate_dense_tune
from egdi.text import build_page_record


class FakeDenseEncoder:
    def split_text(self, text, chunk_tokens, overlap_tokens):
        return [text]

    @staticmethod
    def _vector(text):
        lowered = text.casefold()
        return np.array(
            [float("alpha" in lowered), float("beta" in lowered), float("noise" in lowered)]
        )

    def encode_passages(self, texts):
        return np.stack([self._vector(text) for text in texts])

    def encode_query(self, query):
        return self._vector(query)


class DenseTuneTests(unittest.TestCase):
    def setUp(self):
        self.corpora = {
            "doc-a": [
                build_page_record("doc-a", 1, "alpha evidence"),
                build_page_record("doc-a", 2, "noise"),
            ],
            "doc-b": [
                build_page_record("doc-b", 1, "noise"),
                build_page_record("doc-b", 2, "beta evidence"),
            ],
        }

    @staticmethod
    def question(question_id, doc_id, text, pages, *, answerable=True):
        return {
            "id": question_id,
            "question": text,
            "answer": {"is_answerable": answerable},
            "pdf": {"doc_id_str": doc_id},
            "evidences": [{"page": page, "element_type": "text"} for page in pages],
            "extract_class": "class-test",
        }

    def test_evaluates_each_document_once_and_preserves_question_order(self):
        questions = [
            self.question("doc-b::q1", "doc-b", "beta", [2]),
            self.question("doc-a::q1", "doc-a", "alpha", [1]),
            self.question("doc-a::q2", "doc-a", "alpha", [], answerable=False),
        ]
        result = evaluate_dense_tune(
            questions,
            self.corpora,
            FakeDenseEncoder(),
            chunk_tokens=256,
            overlap_tokens=0,
            ks=(1, 2),
        )

        self.assertEqual(result["evaluated_document_count"], 2)
        self.assertEqual(result["eligible_question_count"], 2)
        self.assertEqual(result["excluded_question_count"], 1)
        self.assertEqual(
            [item["question_id"] for item in result["per_question"]],
            ["doc-b::q1", "doc-a::q1"],
        )
        self.assertEqual(result["aggregate"]["1"]["macro"]["complete_evidence_recall"], 1.0)
        self.assertGreater(result["total_embedding_bytes"], 0)

    def test_rejects_missing_corpus_and_invalid_candidates(self):
        question = self.question("missing::q1", "missing", "alpha", [1])
        with self.assertRaisesRegex(ValueError, "no Page Record corpus"):
            evaluate_dense_tune(
                [question],
                self.corpora,
                FakeDenseEncoder(),
                chunk_tokens=256,
                overlap_tokens=0,
            )
        with self.assertRaisesRegex(ValueError, "outside predeclared"):
            _validated_choice({"sizes": [256, 512]}, "sizes", 128)


if __name__ == "__main__":
    unittest.main()
