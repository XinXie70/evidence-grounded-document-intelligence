import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from egdi.reasoning_api import (
    BudgetPreflightError,
    ResponseProcessingError,
    build_call_log,
    build_openai_request,
    estimate_cost_usd,
    execute_one,
    preflight_request_budget,
    snapshot_api_response,
    validate_execution_logging_config,
    validate_comparison_fact_output,
    validate_grounded_output,
    validate_pricing_snapshot,
)


class FakeUsage:
    def model_dump(self):
        return {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}


class FakeResponses:
    def __init__(self, output):
        self.output = output
        self.calls = []
        self.input_token_calls = []
        self.input_tokens = SimpleNamespace(count=self._count_input_tokens)

    def _count_input_tokens(self, **request):
        self.input_token_calls.append(request)
        return SimpleNamespace(input_tokens=100)

    def create(self, **request):
        self.calls.append(request)
        return SimpleNamespace(
            id="resp-test",
            model="gpt-test-snapshot",
            output_text=json.dumps(self.output),
            usage=FakeUsage(),
            status="completed",
            incomplete_details=None,
            error=None,
            output=[],
        )


class FakeClient:
    def __init__(self, output):
        self.responses = FakeResponses(output)


class ReasoningApiTests(unittest.TestCase):
    def setUp(self):
        self.record = {
            "schema_version": 1,
            "question_id": "doc-a::q1",
            "doc_id": "doc-a",
            "condition": "oracle_page",
            "evidence_pages": [2],
            "model_input": {
                "instructions": "Use only the supplied evidence.",
                "question": "What is the threshold?",
                "evidence": [{"page": 2, "text": "The threshold is 18."}],
                "response_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["answer", "cited_pages", "status"],
                    "properties": {
                        "answer": {"type": ["string", "null"]},
                        "cited_pages": {"type": "array", "items": {"type": "integer"}},
                        "status": {
                            "type": "string",
                            "enum": ["answerable", "insufficient_evidence"],
                        },
                    },
                },
            },
        }
        self.config = {
            "endpoint_mode": "v1/responses",
            "experiment_id": "test-experiment",
            "max_retries": 0,
            "model": "gpt-test",
            "pricing_snapshot_path": "pricing.json",
            "provider": "openai",
            "reasoning_effort": "low",
            "max_output_tokens": 256,
            "store": False,
        }
        self.pricing = {
            "pricing_snapshot_id": "test-pricing",
            "provider": "openai",
            "model": "gpt-test",
            "currency": "USD",
            "source_url": "https://example.test/pricing",
            "input_usd_per_million": 2.0,
            "cached_input_usd_per_million": 0.2,
            "output_usd_per_million": 12.0,
            "cache_write_input_multiplier": 1.25,
        }

    def test_request_is_condition_blind_and_uses_strict_schema(self):
        request = build_openai_request(self.record, self.config)
        serialized_input = json.dumps(request["input"])

        self.assertEqual(request["model"], "gpt-test")
        self.assertFalse(request["store"])
        self.assertNotIn("oracle_page", serialized_input)
        self.assertNotIn("condition", serialized_input)
        self.assertEqual(request["text"]["format"]["type"], "json_schema")
        self.assertTrue(request["text"]["format"]["strict"])

    def test_image_request_embeds_only_verified_in_directory_png(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            image = base / "crop.png"
            image.write_bytes(b"\x89PNG\r\n\x1a\nverified-image")
            import hashlib

            image_sha256 = hashlib.sha256(image.read_bytes()).hexdigest()
            self.record["model_input"]["evidence"] = [
                {
                    "page": 2,
                    "evidence_local_id": "e1",
                    "bbox": [1, 2, 3, 4],
                    "text": "",
                    "text_scope": "image_only",
                    "image_path": "crop.png",
                    "image_sha256": image_sha256,
                }
            ]
            self.config["image_detail"] = "original"

            request = build_openai_request(
                self.record, self.config, input_base_dir=base
            )
            content = request["input"][1]["content"]

            self.assertEqual(content[-1]["type"], "input_image")
            self.assertEqual(content[-1]["detail"], "original")
            self.assertTrue(content[-1]["image_url"].startswith("data:image/png;base64,"))
            self.assertIn("intentionally omitted", content[-2]["text"])

            self.record["model_input"]["evidence"][0]["image_sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                build_openai_request(self.record, self.config, input_base_dir=base)

    def test_forbidden_gold_keys_are_rejected_before_any_call(self):
        self.record["model_input"]["answer_text"] = "SECRET"
        with self.assertRaisesRegex(ValueError, "forbidden keys"):
            build_openai_request(self.record, self.config)

    def test_execute_one_records_output_usage_and_validation(self):
        client = FakeClient(
            {"answer": "18", "cited_pages": [2], "status": "answerable"}
        )
        result = execute_one(self.record, self.config, client=client)

        self.assertEqual(len(client.responses.calls), 1)
        self.assertEqual(result["output"]["answer"], "18")
        self.assertTrue(result["validation"]["valid"])
        self.assertEqual(result["usage"]["total_tokens"], 120)

    def test_validates_comparison_fact_extraction_output(self):
        output = {
            "status": "extracted",
            "facts": [
                {"label": "server", "metric": "baud rate", "value": "57600",
                 "unit": "baud", "cited_pages": [24]},
                {"label": "default", "metric": "baud rate", "value": "38400",
                 "unit": "baud", "cited_pages": [20]},
            ],
        }
        self.assertTrue(validate_comparison_fact_output(output, [20, 24, 27])["valid"])
        output["facts"][0]["value"] = "157,472"
        self.assertTrue(validate_comparison_fact_output(output, [20, 24, 27])["valid"])
        output["facts"][0]["value"] = "(39.0)"
        self.assertTrue(validate_comparison_fact_output(output, [20, 24, 27])["valid"])
        output["facts"][0]["value"] = "15,74,72"
        self.assertFalse(validate_comparison_fact_output(output, [20, 24, 27])["valid"])
        output["facts"][0]["value"] = "57600"
        output["facts"][1]["cited_pages"] = [99]
        invalid = validate_comparison_fact_output(output, [20, 24, 27])
        self.assertFalse(invalid["valid"])
        self.assertFalse(invalid["citations_within_supplied_context"])

    def test_execute_one_dispatches_comparison_fact_validation(self):
        self.config["output_role"] = "comparison_fact_extraction"
        client = FakeClient({"status": "extracted", "facts": [
            {"label": "A", "metric": "m", "value": "10", "unit": "items",
             "cited_pages": [2]},
            {"label": "B", "metric": "m", "value": "5", "unit": "items",
             "cited_pages": [2]}]})
        result = execute_one(self.record, self.config, client=client)
        self.assertTrue(result["validation"]["valid"])

    def test_empty_output_preserves_response_status_and_usage(self):
        response = SimpleNamespace(
            id="resp-incomplete",
            model="gpt-test-snapshot",
            output_text="",
            usage=FakeUsage(),
            status="incomplete",
            incomplete_details=SimpleNamespace(
                model_dump=lambda **kwargs: {"reason": "max_output_tokens"}
            ),
            error=None,
            output=[],
        )
        client = SimpleNamespace(
            responses=SimpleNamespace(create=lambda **request: response)
        )

        with self.assertRaises(ResponseProcessingError) as caught:
            execute_one(self.record, self.config, client=client)

        snapshot = snapshot_api_response(caught.exception.api_response)
        self.assertEqual(snapshot["response_id"], "resp-incomplete")
        self.assertEqual(snapshot["status"], "incomplete")
        self.assertEqual(snapshot["incomplete_details"]["reason"], "max_output_tokens")
        self.assertEqual(snapshot["usage"]["total_tokens"], 120)
        self.assertFalse(snapshot["output_text_present"])
        json.dumps(snapshot)

    def test_invalid_json_preserves_completed_response_and_usage(self):
        response = SimpleNamespace(
            id="resp-invalid-json",
            model="gpt-test-snapshot",
            output_text="not-json",
            usage=FakeUsage(),
            status="completed",
            incomplete_details=None,
            error=None,
            output=[
                SimpleNamespace(
                    model_dump=lambda **kwargs: {"type": "message", "content": []}
                )
            ],
        )
        client = SimpleNamespace(
            responses=SimpleNamespace(create=lambda **request: response)
        )

        with self.assertRaises(ResponseProcessingError) as caught:
            execute_one(self.record, self.config, client=client)

        snapshot = snapshot_api_response(caught.exception.api_response)
        self.assertEqual(snapshot["status"], "completed")
        self.assertEqual(snapshot["usage"]["input_tokens"], 100)
        self.assertTrue(snapshot["output_text_present"])
        self.assertEqual(snapshot["output"][0]["type"], "message")
        json.dumps(snapshot)

    def test_grounding_validation_flags_outside_or_inconsistent_citations(self):
        outside = validate_grounded_output(
            {"answer": "18", "cited_pages": [99], "status": "answerable"}, [2]
        )
        inconsistent = validate_grounded_output(
            {
                "answer": "unsupported guess",
                "cited_pages": [2],
                "status": "insufficient_evidence",
            },
            [2],
        )

        self.assertFalse(outside["valid"])
        self.assertFalse(outside["citations_within_supplied_context"])
        self.assertFalse(inconsistent["valid"])
        self.assertEqual(len(inconsistent["errors"]), 2)

    def test_grounding_validation_rejects_duplicate_citations(self):
        duplicate = validate_grounded_output(
            {"answer": "18", "cited_pages": [2, 2], "status": "answerable"}, [2]
        )

        self.assertFalse(duplicate["valid"])
        self.assertIn("cited_pages contains duplicates", duplicate["errors"])

    def test_closed_book_allows_answer_without_document_citation(self):
        ordinary = validate_grounded_output(
            {"answer": "18", "cited_pages": [], "status": "answerable"}, []
        )
        closed_book = validate_grounded_output(
            {"answer": "18", "cited_pages": [], "status": "answerable"},
            [],
            allow_uncited_answer=True,
        )

        self.assertFalse(ordinary["valid"])
        self.assertTrue(closed_book["valid"])

    def test_execution_logging_requires_zero_implicit_retries(self):
        self.assertIs(validate_execution_logging_config(self.config), self.config)
        self.config["max_retries"] = 2
        with self.assertRaisesRegex(ValueError, "exactly observable"):
            validate_execution_logging_config(self.config)

    def test_pricing_snapshot_must_match_model(self):
        self.assertIs(
            validate_pricing_snapshot(self.pricing, expected_model="gpt-test"),
            self.pricing,
        )
        with self.assertRaisesRegex(ValueError, "does not match"):
            validate_pricing_snapshot(self.pricing, expected_model="another-model")

    def test_cost_estimate_distinguishes_ordinary_cached_and_cache_write_tokens(self):
        usage = {
            "input_tokens": 100,
            "output_tokens": 20,
            "input_tokens_details": {
                "cached_tokens": 10,
                "cache_write_tokens": 40,
            },
        }
        self.assertEqual(estimate_cost_usd(usage, self.pricing), 0.000442)

    def test_budget_preflight_allows_request_below_cap(self):
        client = FakeClient(
            {"answer": "18", "cited_pages": [2], "status": "answerable"}
        )
        request = build_openai_request(self.record, self.config)

        result = preflight_request_budget(
            client, request, self.pricing, approved_hard_cap_usd=1.0
        )

        self.assertTrue(result["within_cap"])
        self.assertEqual(result["input_tokens"], 100)
        self.assertEqual(len(client.responses.input_token_calls), 1)
        self.assertEqual(len(client.responses.calls), 0)

    def test_budget_preflight_blocks_before_generation_above_cap(self):
        client = FakeClient(
            {"answer": "18", "cited_pages": [2], "status": "answerable"}
        )
        request = build_openai_request(self.record, self.config)

        with self.assertRaisesRegex(BudgetPreflightError, "blocked before"):
            preflight_request_budget(
                client, request, self.pricing, approved_hard_cap_usd=0.000001
            )

        self.assertEqual(len(client.responses.input_token_calls), 1)
        self.assertEqual(len(client.responses.calls), 0)

    def test_budget_preflight_rejects_invalid_cap_without_api_call(self):
        client = FakeClient(
            {"answer": "18", "cited_pages": [2], "status": "answerable"}
        )
        request = build_openai_request(self.record, self.config)

        with self.assertRaisesRegex(ValueError, "hard cap"):
            preflight_request_budget(
                client, request, self.pricing, approved_hard_cap_usd=None
            )

        self.assertEqual(len(client.responses.input_token_calls), 0)
        self.assertEqual(len(client.responses.calls), 0)

    def test_call_log_contains_frozen_protocol_fields(self):
        request = build_openai_request(self.record, self.config)
        usage = {
            "input_tokens": 100,
            "output_tokens": 20,
            "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
        }
        call_log = build_call_log(
            self.record,
            self.config,
            request,
            self.pricing,
            model_snapshot="gpt-test-snapshot",
            usage=usage,
            request_date_utc="2026-09-02T00:00:00+00:00",
            latency_ms=123.4567,
            status="ok",
        )

        self.assertEqual(call_log["experiment_id"], "test-experiment")
        self.assertEqual(call_log["context_ids"], ["doc-a::physical_page:2"])
        self.assertEqual(call_log["latency_ms"], 123.457)
        self.assertEqual(call_log["retries"], 0)
        self.assertEqual(call_log["status"], "ok")
        self.assertEqual(len(call_log["prompt_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
