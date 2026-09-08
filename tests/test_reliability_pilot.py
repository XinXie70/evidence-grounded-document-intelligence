import json
import unittest

from egdi.reliability_pilot import SLOTS, select_reliability_pilot


class ReliabilityPilotSelectionTests(unittest.TestCase):
    def setUp(self):
        self.questions = {}
        self.features = []
        self.retrieval = []

        for index, slot in enumerate(SLOTS, start=1):
            question_id = f"doc-{index:02d}::q1"
            is_answerable = slot["kind"] == "answerable"
            self.questions[question_id] = {
                "id": question_id,
                "question": f"Question {index}",
                "pdf": {"doc_id_str": f"doc-{index:02d}"},
                "answer": {
                    "is_answerable": is_answerable,
                    "answer_text": f"SECRET ANSWER {index}",
                },
                "facts": [{"text_description": f"SECRET FACT {index}"}],
                "evidences": [{"page": 2}],
            }

            signal_score = {"low": 10.0, "mid": 20.0, "high": 30.0}.get(
                slot.get("signal"), 20.0
            )
            self.features.append({
                "question_id": question_id,
                "bm25_top1_score": signal_score,
                "bm25_top1_top2_margin": 1.0,
                "top3_pages": [1, 2, 3],
                "top3_extraction_status_counts": {
                    "ok": 3,
                    "low_text": 0,
                    "text_layer_missing": 0,
                },
            })

            if is_answerable:
                band = slot["band"]
                scores = {
                    "complete": {
                        "complete_evidence_recall": 1,
                        "any_evidence_recall": 1,
                    },
                    "partial": {
                        "complete_evidence_recall": 0,
                        "any_evidence_recall": 1,
                    },
                    "none": {
                        "complete_evidence_recall": 0,
                        "any_evidence_recall": 0,
                    },
                }[band]
                evidence_type = (
                    "chart" if slot["bucket"] == "visual" else slot["bucket"]
                )
                self.retrieval.append({
                    "question_id": question_id,
                    "gold_pages": [2],
                    "scores": {"3": scores},
                    "slices": {
                        "evidence_type": evidence_type,
                        "page_span": slot["span"],
                        "gold_text_status": slot["status"],
                    },
                })

        self.tune_ids = set(self.questions)

    def test_selects_all_frozen_slots_without_document_or_answer_leakage(self):
        selected = select_reliability_pilot(
            self.questions,
            list(reversed(self.retrieval)),
            list(reversed(self.features)),
            tune_question_ids=self.tune_ids,
            excluded_question_ids=set(),
        )

        self.assertEqual(len(selected), 24)
        self.assertEqual(len({item["question_id"] for item in selected}), 24)
        self.assertEqual(len({item["doc_id"] for item in selected}), 24)
        self.assertEqual(
            [item["slot_id"] for item in selected],
            [slot["id"] for slot in SLOTS],
        )
        self.assertEqual(sum(item["kind"] == "answerable" for item in selected), 18)
        self.assertEqual(sum(item["kind"] == "unanswerable" for item in selected), 6)
        serialized = json.dumps(selected)
        self.assertNotIn("SECRET", serialized)
        self.assertNotIn("answer_text", serialized)
        self.assertNotIn('"facts"', serialized)
        self.assertNotIn('"evidences"', serialized)

    def test_same_inputs_are_deterministic(self):
        first = select_reliability_pilot(
            self.questions,
            self.retrieval,
            self.features,
            tune_question_ids=self.tune_ids,
            excluded_question_ids=set(),
        )
        second = select_reliability_pilot(
            self.questions,
            list(reversed(self.retrieval)),
            list(reversed(self.features)),
            tune_question_ids=set(reversed(sorted(self.tune_ids))),
            excluded_question_ids=set(),
        )
        self.assertEqual(first, second)

    def test_excluding_only_high_signal_candidate_is_rejected(self):
        high_id = next(
            question_id
            for question_id in self.tune_ids
            if self.questions[question_id]["question"] == "Question 24"
        )
        with self.assertRaisesRegex(ValueError, "no candidates"):
            select_reliability_pilot(
                self.questions,
                self.retrieval,
                self.features,
                tune_question_ids=self.tune_ids,
                excluded_question_ids={high_id},
            )


if __name__ == "__main__":
    unittest.main()
