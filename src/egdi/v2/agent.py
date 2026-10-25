"""Search-and-read agent: a small LangGraph loop around the model and the ToolBox.

    call_model --(tool calls)--> run_tools --> call_model ...
        |                            |
        +-- limit / no tools --------+--> force_finish --> END
    run_tools --(finish accepted)--> END

The model decides what to search and read. The program only enforces limits (tool calls,
cumulative input tokens, cost, wall clock). When a limit is hit the model gets exactly one
more turn, restricted to ``finish``, to answer from what it has read or abstain.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from .answer import ANSWER_RULES, INSUFFICIENT, normalize_final, validate_final
from .llm import LlmClient, to_openai_tools
from .tools import TOOL_SCHEMAS, ToolBox

def build_instructions(limits: "AgentLimits") -> str:
    return (
        "You answer a question about one PDF document by searching and reading it with tools.\n"
        "- search_document finds candidate pages; snippets are only hints, so read_pages before "
        "relying on a page: a snippet is a short excerpt and can miss the relevant part, so read the top-ranked "
        "pages before ruling them out. If a search misses, try different words; repeating a search returns the same pages.\n"
        "- Questions may need several pages (for example a figure on one page and a definition on "
        "another). Keep going until you have everything the answer needs.\n"
        "- Use calculate for arithmetic, quoting each number exactly from a page you have read.\n"
        f"- You have at most {limits.max_tool_calls} tool calls (search, read and calculate each count; finish does not). "
        "Every tool result shows tool_calls_remaining. Plan your calls, and issue several in one step only when "
        "they are independent. Calls beyond the budget are refused.\n"
        "- When you have enough, or when after searching the document clearly does not contain the "
        "answer, call finish. Do not guess.\n" + ANSWER_RULES
    )


FORCE_MESSAGE = (
    "Your tool or budget limit has been reached ({reason}). Call finish now: answer from the pages "
    "you have read, or report insufficient_evidence if they do not support an answer."
)
NUDGE_MESSAGE = "Continue with a tool call. When you are done, call finish with your answer."


@dataclass(frozen=True)
class AgentLimits:
    max_tool_calls: int = 8  # was 6 in the plan; the one permitted development-time adjustment
    max_input_tokens: int = 30_000  # cumulative over the question's model calls
    max_cost_usd: float = 0.10
    max_seconds: float = 120.0
    max_model_calls: int = 12


class AgentState(TypedDict, total=False):
    question: str
    box: ToolBox
    label: str
    items: list[dict[str, Any]]
    tool_calls: int
    model_calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    started: float
    pending: list[Any]
    trace: list[dict[str, Any]]
    final: dict[str, Any] | None
    stop_reason: str
    force_reason: str | None


def _item_dict(item: Any) -> dict[str, Any]:
    return item.model_dump(exclude_none=True) if hasattr(item, "model_dump") else dict(item)


class Agent:
    def __init__(self, llm: LlmClient, limits: AgentLimits = AgentLimits()):
        self.llm, self.limits = llm, limits
        self.tools = to_openai_tools(TOOL_SCHEMAS)
        self.finish_only = [t for t in self.tools if t["name"] == "finish"]
        graph = StateGraph(AgentState)
        graph.add_node("call_model", self._call_model)
        graph.add_node("run_tools", self._run_tools)
        graph.add_node("force_finish", self._force_finish)
        graph.add_edge(START, "call_model")
        graph.add_conditional_edges("call_model", self._after_model, ["run_tools", "call_model", "force_finish"])
        graph.add_conditional_edges("run_tools", self._after_tools, ["call_model", "force_finish", END])
        graph.add_edge("force_finish", END)
        self.graph = graph.compile()

    def run(self, question: str, document: Any, label: str) -> dict[str, Any]:
        box = ToolBox(document)
        start = time.monotonic()
        user = f"Document: {document.page_count} pages (1-based physical PDF page numbers).\n\nQuestion:\n{question}"
        state = self.graph.invoke(
            {
                "question": question, "box": box, "label": label, "items": [{"role": "user", "content": user}],
                "tool_calls": 0, "model_calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
                "started": start, "pending": [], "trace": [], "final": None, "stop_reason": "", "force_reason": None,
            },
            config={"recursion_limit": 60},
        )
        final, error = state["final"], None
        if final is None:  # the model never produced a valid finish: record it as an abstention
            final, error = normalize_final({"status": INSUFFICIENT}), "no_valid_finish"
        return {
            "system": "A",
            "final": final,
            "validation_errors": validate_final(final, box.pages_read),
            "error": error,
            "stop_reason": state["stop_reason"],
            "pages_read": box.pages_read,
            "tool_calls": state["tool_calls"],
            "model_calls": state["model_calls"],
            "input_tokens": state["input_tokens"],
            "output_tokens": state["output_tokens"],
            "cost_usd": round(state["cost_usd"], 6),
            "latency_s": round(time.monotonic() - start, 3),
            "trace": state["trace"],
        }

    # --- nodes -------------------------------------------------------------------------

    def _limit_reason(self, state: AgentState) -> str | None:
        lim = self.limits
        if state["tool_calls"] >= lim.max_tool_calls:
            return "tool_limit"
        if state["input_tokens"] >= lim.max_input_tokens:
            return "token_limit"
        if state["cost_usd"] >= lim.max_cost_usd:
            return "cost_limit"
        if time.monotonic() - state["started"] >= lim.max_seconds:
            return "timeout"
        if state["model_calls"] >= lim.max_model_calls:
            return "model_call_limit"
        return None

    def _model_turn(self, state: AgentState, tools: list[dict[str, Any]], tool_choice: Any = None):
        reply = self.llm.respond(
            label=f"A:{state['label']}:{state['model_calls'] + 1}",
            input=state["items"],
            instructions=build_instructions(self.limits),
            tools=tools,
            tool_choice=tool_choice,
            include=["reasoning.encrypted_content"],
        )
        output = list(reply.response.output)
        usage = reply.usage or {}
        update = {
            "items": state["items"] + [_item_dict(item) for item in output],
            "model_calls": state["model_calls"] + 1,
            "input_tokens": state["input_tokens"] + usage.get("input_tokens", 0),
            "output_tokens": state["output_tokens"] + usage.get("output_tokens", 0),
            "cost_usd": state["cost_usd"] + reply.cost_usd,
            "pending": [item for item in output if getattr(item, "type", None) == "function_call"],
        }
        return update

    def _call_model(self, state: AgentState) -> dict[str, Any]:
        reason = self._limit_reason(state)
        if reason:
            return {"force_reason": reason, "pending": []}
        update = self._model_turn(state, self.tools)
        if not update["pending"]:  # plain text instead of a tool call: nudge once per turn
            update["items"] = update["items"] + [{"role": "user", "content": NUDGE_MESSAGE}]
            update["trace"] = state["trace"] + [{"event": "no_tool_call"}]
        return update

    def _after_model(self, state: AgentState) -> str:
        if state.get("force_reason"):
            return "force_finish"
        return "run_tools" if state["pending"] else "call_model"

    def _execute_calls(self, state: AgentState, accept_budget: bool) -> dict[str, Any]:
        box, items, trace = state["box"], list(state["items"]), list(state["trace"])
        calls_used, stop_reason = state["tool_calls"], state["stop_reason"]
        for call in state["pending"]:
            try:
                arguments = json.loads(call.arguments) if call.arguments else {}
            except json.JSONDecodeError:
                arguments = None
            counts = call.name != "finish"
            if counts and (not accept_budget or calls_used >= self.limits.max_tool_calls):
                result = {"error": "tool_budget_exhausted", "message": "no tool calls left; call finish"}
            elif arguments is None:
                result = {"error": "bad_arguments", "message": "arguments were not valid JSON"}
                calls_used += counts
            else:
                result = box.execute(call.name, arguments)
                calls_used += counts and not result.get("duplicate")
            if counts:
                result["tool_calls_remaining"] = max(self.limits.max_tool_calls - calls_used, 0)
            trace.append(_trace_entry(call.name, arguments, result))
            items.append({"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(result, ensure_ascii=False)})
            if call.name == "finish" and result.get("ok"):
                stop_reason = stop_reason or "finished"
                break
        update: dict[str, Any] = {"items": items, "trace": trace, "tool_calls": calls_used, "stop_reason": stop_reason}
        if box.final is not None:
            update["final"] = normalize_final(box.final)
        return update

    def _run_tools(self, state: AgentState) -> dict[str, Any]:
        return self._execute_calls(state, accept_budget=True)

    def _after_tools(self, state: AgentState) -> str:
        if state.get("final") is not None:
            return END
        return "force_finish" if self._limit_reason(state) else "call_model"

    def _force_finish(self, state: AgentState) -> dict[str, Any]:
        reason = state.get("force_reason") or self._limit_reason(state) or "limit"
        message = {"role": "user", "content": FORCE_MESSAGE.format(reason=reason)}
        staged = {**state, "items": state["items"] + [message]}
        update = self._model_turn(staged, self.finish_only, {"type": "function", "name": "finish"})
        staged.update(update)
        outcome = self._execute_calls(staged, accept_budget=False)
        outcome["stop_reason"] = reason
        outcome["model_calls"], outcome["input_tokens"] = update["model_calls"], update["input_tokens"]
        outcome["output_tokens"], outcome["cost_usd"] = update["output_tokens"], update["cost_usd"]
        return outcome


def _trace_entry(name: str, arguments: Any, result: dict[str, Any]) -> dict[str, Any]:
    """Compact record of a tool call; page text is summarised rather than stored twice."""
    shown = result
    if name == "read_pages" and "pages" in result:
        shown = result | {"pages": [{k: v for k, v in p.items() if k != "text"} | ({"chars": len(p["text"])} if "text" in p else {}) for p in result["pages"]]}
    return {"tool": name, "arguments": arguments, "result": shown}
