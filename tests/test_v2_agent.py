import json
import unittest
from types import SimpleNamespace

from egdi.v2.agent import Agent, AgentLimits
from egdi.v2.llm import LlmResult


def call(name, call_id="c", **arguments):
    raw = arguments.pop("_raw", None)
    args = raw if raw is not None else json.dumps(arguments)
    item = {"type": "function_call", "name": name, "arguments": args, "call_id": call_id}
    return SimpleNamespace(**item, model_dump=lambda exclude_none=True, item=item: dict(item))


def text(content="thinking"):
    item = {"type": "message", "content": content}
    return SimpleNamespace(**item, model_dump=lambda exclude_none=True, item=item: dict(item))


class ScriptedLlm:
    """Replays one scripted model turn per request and records what it was sent."""

    def __init__(self, turns, input_tokens=100, cost=0.001):
        self.turns, self.requests = list(turns), []
        self.input_tokens, self.cost = input_tokens, cost

    def respond(self, **kwargs):
        self.requests.append({**kwargs, "input": list(kwargs["input"])})
        output = self.turns.pop(0)
        usage = {"input_tokens": self.input_tokens, "output_tokens": 10}
        return LlmResult(SimpleNamespace(output=output), usage, self.cost, 0.01)


class Doc:
    page_count = 3
    page_text = {1: "Revenue 2022: 100", 2: "Revenue 2023: 125", 3: "Appendix"}

    def search(self, query, k):
        return [{"page": p, "score": 1.0, "snippet": t[:10]} for p, t in list(self.page_text.items())[:k]]


def run(turns, limits=AgentLimits(), **kw):
    llm = ScriptedLlm(turns, **kw)
    return Agent(llm, limits).run("How much did revenue grow?", Doc(), "q1"), llm


def finish(call_id="f", status="answered", answer="25%", pages=(1, 2)):
    return call("finish", call_id, status=status, answer=answer, cited_pages=list(pages))


class AgentTests(unittest.TestCase):
    def test_search_read_calculate_finish(self):
        result, llm = run([
            [call("search_document", "1", query="revenue")],
            [call("read_pages", "2", pages=[1, 2])],
            [call("calculate", "3", op="percent_change", operands=[
                {"value": 100, "page": 1, "quote": "Revenue 2022: 100"},
                {"value": 125, "page": 2, "quote": "Revenue 2023: 125"}])],
            [finish()],
        ])
        self.assertEqual(result["stop_reason"], "finished")
        self.assertEqual(result["final"], {"status": "answered", "answer": "25%", "cited_pages": [1, 2]})
        self.assertEqual((result["tool_calls"], result["model_calls"]), (3, 4))
        self.assertEqual(result["pages_read"], [1, 2])
        self.assertEqual(result["validation_errors"], [])
        self.assertEqual(result["trace"][2]["result"]["result"], 25.0)
        self.assertNotIn("text", json.dumps(result["trace"][1]))  # page text is summarised in the trace
        outputs = [i for i in llm.requests[-1]["input"] if i.get("type") == "function_call_output"]
        self.assertEqual([o["call_id"] for o in outputs], ["1", "2", "3"])

    def test_citing_an_unread_page_is_rejected_then_corrected(self):
        result, _ = run([
            [call("read_pages", "1", pages=[1])],
            [finish("f1", pages=(1, 2))],
            [call("read_pages", "2", pages=[2])],
            [finish("f2", pages=(1, 2))],
        ])
        self.assertEqual(result["trace"][1]["result"]["error"], "cited_page_not_read")
        self.assertEqual(result["stop_reason"], "finished")
        self.assertEqual(result["final"]["cited_pages"], [1, 2])

    def test_tool_limit_forces_a_finish_only_turn(self):
        limits = AgentLimits(max_tool_calls=2)
        result, llm = run([
            [call("search_document", "1", query="a")],
            [call("read_pages", "2", pages=[1])],
            [finish("f", pages=(1,))],  # the forced turn
        ], limits)
        self.assertEqual(result["stop_reason"], "tool_limit")
        self.assertEqual(result["final"]["status"], "answered")
        forced = llm.requests[-1]
        self.assertEqual([t["name"] for t in forced["tools"]], ["finish"])
        self.assertEqual(forced["tool_choice"], {"type": "function", "name": "finish"})
        self.assertIn("tool_limit", forced["input"][-1]["content"])

    def test_forced_turn_that_does_not_finish_becomes_a_recorded_abstention(self):
        result, _ = run([[call("search_document", "1", query="a")], [text()]], AgentLimits(max_tool_calls=1))
        self.assertEqual(result["error"], "no_valid_finish")
        self.assertEqual(result["final"], {"status": "insufficient_evidence", "answer": None, "cited_pages": []})

    def test_parallel_calls_beyond_the_limit_get_a_budget_error(self):
        result, _ = run([
            [call("search_document", "1", query="a"), call("search_document", "2", query="b"), call("search_document", "3", query="c")],
            [finish("f", status="insufficient_evidence", answer="", pages=())],
        ], AgentLimits(max_tool_calls=2))
        self.assertEqual(result["trace"][2]["result"]["error"], "tool_budget_exhausted")
        self.assertEqual(result["tool_calls"], 2)
        self.assertEqual(result["final"]["status"], "insufficient_evidence")

    def test_token_limit_uses_cumulative_input_tokens(self):
        result, _ = run([
            [call("search_document", "1", query="a")],
            [call("search_document", "2", query="b")],  # cumulative 200 >= 150 after this call
            [finish("f", status="insufficient_evidence", answer="", pages=())],  # forced turn
        ], AgentLimits(max_input_tokens=150), input_tokens=100)
        self.assertEqual(result["stop_reason"], "token_limit")
        self.assertEqual((result["model_calls"], result["input_tokens"]), (3, 300))

    def test_cost_limit(self):
        result, _ = run([
            [call("search_document", "1", query="a")],
            [call("search_document", "2", query="b")],  # cumulative cost 0.002 >= 0.0015
            [finish("f", status="insufficient_evidence", answer="", pages=())],
        ], AgentLimits(max_cost_usd=0.0015), cost=0.001)
        self.assertEqual(result["stop_reason"], "cost_limit")

    def test_plain_text_reply_is_nudged_and_malformed_arguments_are_reported(self):
        result, llm = run([
            [text("let me think")],
            [call("read_pages", "1", _raw="{not json")],
            [finish("f", status="insufficient_evidence", answer="", pages=())],
        ])
        self.assertEqual(result["trace"][0], {"event": "no_tool_call"})
        self.assertEqual(result["trace"][1]["result"]["error"], "bad_arguments")
        self.assertEqual(result["stop_reason"], "finished")
        self.assertTrue(any(i.get("content", "").startswith("Continue with a tool call") for i in llm.requests[1]["input"] if "content" in i))

    def test_model_call_limit_prevents_endless_chatter(self):
        result, _ = run([[text()]] * 3 + [[finish("f", status="insufficient_evidence", answer="", pages=())]],
                        AgentLimits(max_model_calls=3))
        self.assertEqual(result["stop_reason"], "model_call_limit")

    def test_results_show_remaining_budget_and_duplicates_are_free(self):
        result, llm = run([
            [call("search_document", "1", query="revenue")],
            [call("search_document", "2", query="Revenue")],  # duplicate: not charged
            [call("read_pages", "3", pages=[1])],
            [finish("f", pages=(1,))],
        ], AgentLimits(max_tool_calls=3))
        remaining = [t["result"]["tool_calls_remaining"] for t in result["trace"] if t.get("tool") != "finish"]
        self.assertEqual(remaining, [2, 2, 1])
        self.assertTrue(result["trace"][1]["result"]["duplicate"])
        self.assertEqual(result["tool_calls"], 2)
        self.assertEqual(result["stop_reason"], "finished")

    def test_instructions_state_the_tool_budget(self):
        _, llm = run([[finish("f", status="insufficient_evidence", answer=None, pages=())]], AgentLimits(max_tool_calls=5))
        self.assertIn("at most 5 tool calls", llm.requests[0]["instructions"])

    def test_requests_ask_for_encrypted_reasoning_and_all_tools(self):
        _, llm = run([[finish("f", status="insufficient_evidence", answer="", pages=())]])
        first = llm.requests[0]
        self.assertEqual(first["include"], ["reasoning.encrypted_content"])
        self.assertEqual([t["name"] for t in first["tools"]], ["search_document", "read_pages", "calculate", "finish"])
        self.assertIn("3 pages", first["input"][0]["content"])


if __name__ == "__main__":
    unittest.main()
