import json
import unittest
from types import SimpleNamespace

from egdi.v2.answer import normalize_final, validate_final
from egdi.v2.baseline import run_baseline
from egdi.v2.eval.run import sample_question_ids
from egdi.v2.llm import BudgetExceeded, CostLedger, LlmClient

CONFIG = {"model": "m", "reasoning_effort": "low", "max_output_tokens": 100, "store": False}
PRICING = {
    "input_usd_per_million": 2.0, "output_usd_per_million": 12.0,
    "cached_input_usd_per_million": 0.2, "cache_write_input_multiplier": 1.25,
}


class FakeClient:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.requests = []
        self.responses = SimpleNamespace(create=self.create)

    def create(self, **request):
        self.requests.append(request)
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        usage = SimpleNamespace(model_dump=lambda: {"input_tokens": 1000, "output_tokens": 100, "input_tokens_details": {"cached_tokens": 0}})
        return SimpleNamespace(output_text=output, usage=usage, id="resp_1")


class FakeDocument:
    page_text = {p: f"text of page {p}" for p in range(1, 9)}

    def search(self, query, k):
        return [{"page": p, "score": 1.0, "snippet": ""} for p in range(1, k + 1)]


def llm(outputs, cap=1.0):
    return LlmClient(CONFIG, PRICING, CostLedger(cap), client=FakeClient(outputs))


class BaselineTests(unittest.TestCase):
    def test_b0_reads_three_pages_and_records_cost(self):
        answer = json.dumps({"status": "answered", "answer": "42", "cited_pages": [2]})
        client = llm([answer])
        result = run_baseline("B0", "q?", FakeDocument(), client, "t")
        self.assertEqual(result["retrieved_pages"], [1, 2, 3])
        self.assertEqual(result["final"], {"status": "answered", "answer": "42", "cited_pages": [2]})
        self.assertEqual(result["validation_errors"], [])
        self.assertAlmostEqual(result["cost_usd"], (1000 * 2 + 100 * 12) / 1e6)
        self.assertIn("[Physical PDF page 3]", client.client.requests[0]["input"])
        self.assertNotIn("[Physical PDF page 4]", client.client.requests[0]["input"])

    def test_b1_reads_six_pages(self):
        answer = json.dumps({"status": "insufficient_evidence", "answer": None, "cited_pages": [5]})
        result = run_baseline("B1", "q?", FakeDocument(), llm([answer]), "t")
        self.assertEqual(len(result["retrieved_pages"]), 6)
        self.assertEqual(result["final"], {"status": "insufficient_evidence", "answer": None, "cited_pages": []})

    def test_citation_outside_supplied_pages_is_flagged(self):
        answer = json.dumps({"status": "answered", "answer": "x", "cited_pages": [7]})
        result = run_baseline("B0", "q?", FakeDocument(), llm([answer]), "t")
        self.assertEqual(result["validation_errors"], ["cited pages were not supplied: [7]"])

    def test_failures_are_recorded_not_raised(self):
        result = run_baseline("B0", "q?", FakeDocument(), llm(["not json"]), "t")
        self.assertIsNone(result["final"])
        self.assertIn("unparseable", result["error"])
        result = run_baseline("B0", "q?", FakeDocument(), llm([RuntimeError("boom")]), "t")
        self.assertIn("boom", result["error"])

    def test_budget_cap_stops_the_run(self):
        answer = json.dumps({"status": "answered", "answer": "x", "cited_pages": [1]})
        client = llm([answer, answer], cap=0.001)  # first call costs 0.0032 and exhausts the cap
        run_baseline("B0", "q?", FakeDocument(), client, "t")
        with self.assertRaises(BudgetExceeded):
            run_baseline("B0", "q?", FakeDocument(), client, "t")


class AnswerTests(unittest.TestCase):
    def test_normalize_and_validate(self):
        self.assertEqual(normalize_final({"status": "insufficient_evidence", "answer": "n/a", "cited_pages": [1]})["cited_pages"], [])
        final = normalize_final({"status": "answered", "answer": " 5 ", "cited_pages": [2, 2, 1]})
        self.assertEqual(final, {"status": "answered", "answer": "5", "cited_pages": [1, 2]})
        self.assertEqual(validate_final({"status": "answered", "answer": None, "cited_pages": []}, [1]),
                         ["answered result has no answer", "answered result cites no page"])


class SampleTests(unittest.TestCase):
    def test_sample_is_deterministic_and_seeded(self):
        pool = {"answerable_question_ids": [f"a{i}" for i in range(20)], "unanswerable_question_ids": ["u1", "u2"]}
        self.assertEqual(sample_question_ids(pool, 5, "s"), sample_question_ids(pool, 5, "s"))
        self.assertNotEqual(sample_question_ids(pool, 5, "s"), sample_question_ids(pool, 5, "t"))


if __name__ == "__main__":
    unittest.main()
