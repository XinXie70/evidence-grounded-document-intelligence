import tempfile
import unittest
from pathlib import Path

from egdi.io import sha256_file, write_json
from egdi.selective_decision_batch import apply_selective_batch


class SelectiveDecisionBatchTests(unittest.TestCase):
    def test_freezes_retained_and_abstained_predictions_without_labels(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.json"
            write_json(source, {
                "question_id": "q1", "doc_id": "d", "evidence_pages": [1],
                "output": {"answer": "yes", "cited_pages": [1], "status": "answerable"},
                "validation": {"valid": True, "citations_within_supplied_context": True, "errors": []},
            })
            features = {
                "question_id": "q1", "route": "r0_text", "policy_eligible": True,
                "query_token_coverage_ratio": 1.0, "citation_to_evidence_ratio": 1.0,
                "bm25_dense_agreement_at_10": 1.0,
            }
            manifest = {
                "split": "development_calibration", "contains_gold_or_answer_labels": False,
                "case_count": 1, "cases": [{
                    "pilot_id": "p1", "question_id": "q1", "doc_id": "d",
                    "reasoning_result": {"path": str(source), "sha256": sha256_file(source)},
                    "features": features,
                }],
            }
            policy = {
                "weights": {"route_prior": .65, "query_token_coverage_ratio": .15,
                            "citation_to_evidence_ratio": .15, "bm25_dense_agreement_at_10": .05},
                "route_priors": {"r0_text": 1/3, "r1_local_visual": 5/6,
                                 "r2_scanned_document": 3/4, "r3_document_global": 1/2},
                "missing_values": {"bm25_dense_agreement_at_10": .5},
            }
            threshold = {
                "status": "protocol_corrected_and_frozen_before_locked_test",
                "split_used_for_threshold_selection": "development_calibration",
                "locked_test_accessed": False, "confidence_threshold": .9,
            }
            result = apply_selective_batch(manifest, policy, threshold, output_dir=root / "final")
            self.assertEqual(result["retained_answer_count"], 0)
            self.assertEqual(result["abstained_count"], 1)
            final = __import__("json").loads(
                (root / "final" / "p1" / "real_retrieval.json").read_text()
            )
            self.assertEqual(final["output"]["status"], "insufficient_evidence")
            self.assertFalse(result["contains_gold_or_answer_labels"])
