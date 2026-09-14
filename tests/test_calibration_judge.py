import unittest
from types import SimpleNamespace

from egdi.calibration_judge import build_judge_request, execute_judge
from egdi.reasoning_api import ResponseProcessingError


def config(field):
    return {
        "provider": "openai", "endpoint_mode": "v1/responses", "model": "m",
        "max_retries": 0, "instructions": "judge", "reasoning_effort": "low",
        "max_output_tokens": 20, "store": False,
        "response_schema": {"type": "object", "properties": {field: {"type": "boolean"}, "reason": {"type": "string"}}},
    }


class CalibrationJudgeTests(unittest.TestCase):
    def test_semantic_request_keeps_document_evidence_out(self):
        request = build_judge_request({
            "judge_type": "semantic", "question": "Q", "reference_answer": "A",
            "candidate_answer": "B",
        }, config("consistent"))
        text = request["input"][1]["content"]
        self.assertIn("Reference answer", text)
        self.assertNotIn("Cited evidence", text)

    def test_support_request_keeps_reference_answer_out(self):
        request = build_judge_request({
            "judge_type": "support", "question": "Q", "candidate_answer": "B",
            "cited_evidence": [{"page": 2, "text": "E"}],
        }, config("supported"))
        text = request["input"][1]["content"]
        self.assertIn("Cited evidence", text)
        self.assertNotIn("Reference answer", text)

    def test_empty_api_output_preserves_response_for_failure_logging(self):
        response = SimpleNamespace(
            output_text="", id="r1", model="m", usage=None, status="incomplete",
            incomplete_details={"reason": "max_output_tokens"}, error=None, output=[],
        )
        client = SimpleNamespace(
            responses=SimpleNamespace(
                input_tokens=SimpleNamespace(count=lambda **kwargs: SimpleNamespace(input_tokens=10)),
                create=lambda **kwargs: response,
            )
        )
        pricing = {
            "input_usd_per_million": 1, "cached_input_usd_per_million": 1,
            "output_usd_per_million": 1, "cache_write_input_multiplier": 1,
            "pricing_snapshot_id": "p",
        }
        with self.assertRaises(ResponseProcessingError) as caught:
            execute_judge({
                "question_id": "q", "judge_type": "semantic", "question": "Q",
                "reference_answer": "A", "candidate_answer": "B",
            }, {**config("consistent"), "experiment_id": "x"}, pricing, client,
                approved_hard_cap_usd=1.0)
        self.assertIs(caught.exception.api_response, response)


if __name__ == "__main__":
    unittest.main()
