import json
import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from egdi.v2.eval.judge import judge_row, local_support_result, local_task_result, pending_calls
from egdi.v2.eval.report import build_report, paired_bootstrap, point_estimates
from egdi.v2.llm import CostLedger, LlmClient

ANSWERED = {"status": "answered", "answer": "42", "cited_pages": [3]}
ABSTAINED = {"status": "insufficient_evidence", "answer": None, "cited_pages": []}


def result(final, error=None, validation_errors=()):
    return {"question_id": "q::1", "doc_id": "d", "final": final, "error": error,
            "validation_errors": list(validation_errors), "cost_usd": 0.01, "latency_s": 1.0}


def gold(answerable=True):
    return {"question": "Q?", "answer": {"is_answerable": answerable, "answer_text": "42"},
            "evidences": [{"page": 3}, {"page": 4}]}


class LocalRuleTests(unittest.TestCase):
    def test_task_rules_follow_v1(self):
        self.assertIsNone(local_task_result(result(ANSWERED), gold()))  # judge decides
        self.assertFalse(local_task_result(result(ABSTAINED), gold()))  # abstaining on answerable is wrong
        self.assertTrue(local_task_result(result(ABSTAINED), gold(False)))
        self.assertFalse(local_task_result(result(ANSWERED), gold(False)))
        self.assertFalse(local_task_result(result(None, error="boom"), gold(False)))  # failure beats abstention
        self.assertFalse(local_task_result(result(ABSTAINED, error="no_valid_finish"), gold(False)))
        self.assertFalse(local_task_result(result(ANSWERED, validation_errors=["x"]), gold()))

    def test_support_rules_follow_v1(self):
        self.assertIsNone(local_support_result(result(ANSWERED)))
        self.assertTrue(local_support_result(result(ABSTAINED)))
        self.assertFalse(local_support_result(result({**ANSWERED, "cited_pages": []})))
        self.assertTrue(local_support_result(result(None, error="boom")))
        self.assertFalse(local_support_result(result(ANSWERED, validation_errors=["x"])))

    def test_pending_calls_counts_only_judged_cases(self):
        results = {"A": [result(ANSWERED), result(ABSTAINED)]}
        counts = pending_calls(results, {"q::1": gold()})
        self.assertEqual((counts["semantic"], counts["support_upper_bound"]), (1, 1))


class FakeClient:
    def __init__(self, decisions):
        self.decisions, self.calls = list(decisions), []
        self.responses = SimpleNamespace(create=self.create)

    def create(self, **request):
        self.calls.append(request)
        key = "consistent" if "reference answer" in request["input"][0]["content"].lower() else "supported"
        usage = SimpleNamespace(model_dump=lambda: {"input_tokens": 100, "output_tokens": 10, "input_tokens_details": {"cached_tokens": 0}})
        return SimpleNamespace(output_text=json.dumps({key: self.decisions.pop(0), "reason": "r"}), usage=usage, id="r")


PRICING = {"input_usd_per_million": 2.0, "output_usd_per_million": 12.0,
           "cached_input_usd_per_million": 0.2, "cache_write_input_multiplier": 1.25}
JUDGE_CONFIG = {
    "model": "m", "reasoning_effort": "low", "max_output_tokens": 100, "store": False,
    "provider": "openai", "endpoint_mode": "v1/responses", "max_retries": 0, "instructions": "judge",
    "response_schema": {"type": "object", "properties": {"consistent": {"type": "boolean"}, "supported": {"type": "boolean"}, "reason": {"type": "string"}}},
}


class PagesStub:
    def text(self, doc_id, page):
        return f"text of page {page}"


class JudgeRowTests(unittest.TestCase):
    def run_row(self, decisions, final=ANSWERED, cache=None, answerable=True):
        client = FakeClient(decisions)
        ledger = CostLedger(1.0)
        llm = LlmClient(JUDGE_CONFIG, PRICING, ledger, client=client)
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "cache.jsonl"
            cache = {} if cache is None else cache
            row = judge_row("A", result(final), gold(answerable), PagesStub(), (llm, JUDGE_CONFIG), (llm, JUDGE_CONFIG), cache, file)
            written = file.read_text().count("\n") if file.exists() else 0
        return row, client, cache, written

    def test_correct_and_supported(self):
        row, client, _, written = self.run_row([True, True])
        self.assertTrue(row["task_correct"] and row["grounded_correct"])
        self.assertEqual((len(client.calls), written), (2, 2))
        self.assertTrue(row["multi_page"])
        self.assertIn("[Physical PDF page 3]", client.calls[1]["input"][0]["content"])

    def test_incorrect_answer_skips_the_support_judge(self):
        row, client, _, _ = self.run_row([False])
        self.assertFalse(row["task_correct"] or row["grounded_correct"])
        self.assertIsNone(row["supported"])
        self.assertEqual(len(client.calls), 1)

    def test_unsupported_answer_is_task_correct_but_not_grounded(self):
        row, _, _, _ = self.run_row([True, False])
        self.assertTrue(row["task_correct"])
        self.assertFalse(row["grounded_correct"])

    def test_abstention_needs_no_judge_calls(self):
        row, client, _, _ = self.run_row([], final=ABSTAINED, answerable=False)
        self.assertTrue(row["task_correct"] and row["grounded_correct"] and not row["answered"])
        self.assertEqual(len(client.calls), 0)

    def test_cached_judgments_are_reused(self):
        cache = {"A|q::1|semantic": {"key": "A|q::1|semantic", "decision": True, "reason": "", "cost_usd": 0},
                 "A|q::1|support": {"key": "A|q::1|support", "decision": True, "reason": "", "cost_usd": 0}}
        row, client, _, written = self.run_row([], cache=cache)
        self.assertTrue(row["grounded_correct"])
        self.assertEqual((len(client.calls), written), (0, 0))


def row(system, qid, doc, correct, answerable=True, multi=True):
    return {"system": system, "question_id": qid, "doc_id": doc, "answerable": answerable, "multi_page": multi,
            "answered": correct or answerable, "task_correct": correct, "grounded_correct": correct,
            "cost_usd": 0.01, "latency_s": 1.0, "tool_calls": None, "pages_read": [1, 2]}


def synthetic(rate_a, rate_b, docs=60, per_doc=2, seed=1):
    rng = random.Random(seed)
    rows = []
    for d in range(docs):
        for q in range(per_doc):
            qid = f"d{d}::q{q}"
            rows.append(row("A", qid, f"d{d}", rng.random() < rate_a))
            rows.append(row("B0", qid, f"d{d}", rng.random() < rate_b))
    return rows


class ReportTests(unittest.TestCase):
    def test_point_estimates(self):
        rows = [row("A", "a::1", "a", True), row("A", "a::2", "a", False),
                row("A", "b::1", "b", True, answerable=False, multi=False)]
        m = point_estimates(rows)
        self.assertAlmostEqual(m["task_accuracy"], 2 / 3)
        self.assertEqual((m["multi_page_task_accuracy_n"], m["unanswerable_correct_abstention_n"]), (2, 1))

    def test_clear_difference_excludes_zero_and_identical_systems_include_it(self):
        rows = synthetic(0.9, 0.5)
        by = {"A": [r for r in rows if r["system"] == "A"], "B0": [r for r in rows if r["system"] == "B0"]}
        out = paired_bootstrap(by, "A", "B0", "task_accuracy", replicates=2000)
        self.assertGreater(out["ci95_lower"], 0)
        self.assertEqual(out["documents"], 60)
        same = [dict(r, system="B0") for r in by["A"]]
        out = paired_bootstrap({"A": by["A"], "B0": same}, "A", "B0", "task_accuracy", replicates=2000)
        self.assertEqual((out["difference"], out["ci95_lower"], out["ci95_upper"]), (0.0, 0.0, 0.0))

    def test_deterministic_and_pairs_use_shared_questions_only(self):
        rows = synthetic(0.7, 0.6)
        by = {"A": [r for r in rows if r["system"] == "A"], "B0": [r for r in rows if r["system"] == "B0"][:-4]}
        first = paired_bootstrap(by, "A", "B0", "task_accuracy", replicates=500)
        self.assertEqual(first, paired_bootstrap(by, "A", "B0", "task_accuracy", replicates=500))
        self.assertEqual(first["questions"], 116)

    def test_build_report_has_expected_comparisons(self):
        rows = synthetic(0.8, 0.5) + [dict(r, system="B1") for r in synthetic(0.6, 0.6) if r["system"] == "A"]
        report = build_report(rows, replicates=200)
        pairs = {(c["a"], c["b"]) for c in report["paired_comparisons"]}
        self.assertEqual(pairs, {("A", "B0"), ("A", "B1"), ("B1", "B0")})
        self.assertEqual(set(report["systems"]), {"A", "B0", "B1"})


if __name__ == "__main__":
    unittest.main()
