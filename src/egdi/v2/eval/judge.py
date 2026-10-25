"""Judge V2 results with the V1 frozen semantic and evidence-support judges.

Scoring rules mirror V1 (calibration_judge_inputs.py / calibration_score.py):
  * answerable + answered   -> semantic judge decides task_correct
  * answerable + abstained  -> task_correct False
  * unanswerable            -> task_correct iff the system abstained
  * system failure (API/parse error, invalid citations, no valid finish) -> task_correct False
  * grounded_correct = task_correct and the cited pages support the answer
The support judge only runs when task_correct is True, because grounded_correct is False
otherwise; ``supported`` is therefore None for incorrect answers.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from egdi.access import load_records
from egdi.calibration_judge import build_judge_request
from egdi.corpus import read_page_records_jsonl
from egdi.v2.index import find_page_records
from egdi.v2.llm import BudgetExceeded, CostLedger, LlmClient
from egdi.v2.tools import MAX_PAGE_CHARS

SEMANTIC_CONFIG = "configs/locked_test_semantic_judge_v0.json"
SUPPORT_CONFIG = "configs/locked_test_support_judge_v0.json"
ABSTAIN = "insufficient_evidence"


def case_state(result: dict[str, Any]) -> dict[str, Any]:
    final = result.get("final")
    failure = bool(result.get("error")) or final is None or bool(result.get("validation_errors"))
    answered = (not failure) and final["status"] != ABSTAIN
    return {"failure": failure, "answered": answered, "final": final}


def local_task_result(result: dict[str, Any], gold: dict[str, Any]) -> bool | None:
    """task_correct when no judge is needed, else None (the semantic judge decides)."""
    state = case_state(result)
    if state["failure"]:
        return False
    if not gold["answer"]["is_answerable"]:
        return not state["answered"]
    return False if not state["answered"] else None


def local_support_result(result: dict[str, Any]) -> bool | None:
    """evidence_supported when no judge is needed, else None (the support judge decides)."""
    state = case_state(result)
    if state["failure"]:
        return state["final"] is None or state["final"]["answer"] is None
    if not state["answered"]:
        return True
    return False if not state["final"]["cited_pages"] else None


def call_judge(llm: LlmClient, config: dict[str, Any], kind: str, record: dict[str, Any], label: str) -> dict[str, Any]:
    request = build_judge_request({**record, "judge_type": kind}, config)
    reply = llm.respond(
        label=label,
        input=[request["input"][1]],
        instructions=config["instructions"],
        text=request["text"],
        max_output_tokens=config["max_output_tokens"],
    )
    parsed = json.loads(reply.response.output_text)
    key = "consistent" if kind == "semantic" else "supported"
    if not isinstance(parsed.get(key), bool):
        raise ValueError("judge returned no boolean decision")
    return {"decision": parsed[key], "reason": parsed.get("reason", ""), "cost_usd": reply.cost_usd}


class PageStore:
    """Page text exactly as a system could have seen it (truncated like the tools and baselines)."""

    def __init__(self, root: Path):
        self.root, self._docs = root, {}

    def text(self, doc_id: str, page: int) -> str:
        if doc_id not in self._docs:
            records = read_page_records_jsonl(find_page_records(self.root, doc_id))
            self._docs[doc_id] = {r.page: r.text for r in records}
        return self._docs[doc_id][page][:MAX_PAGE_CHARS]


def judge_row(system, result, gold, pages, semantic, support, cache, cache_file) -> dict[str, Any]:
    """Score one result; judge calls are cached by (system, question, kind)."""
    qid, doc_id = result["question_id"], result["doc_id"]
    state = case_state(result)
    final = state["final"] or {}
    evidence_pages = sorted({e["page"] for e in gold.get("evidences", [])})
    task = local_task_result(result, gold)
    supported = local_support_result(result)

    def cached_call(kind, llm, config, record):
        key = f"{system}|{qid}|{kind}"
        if key not in cache:
            cache[key] = {"key": key, **call_judge(llm, config, kind, record, key)}
            with cache_file.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(cache[key], ensure_ascii=False) + "\n")
        return cache[key]

    if task is None:
        verdict = cached_call("semantic", *semantic, {
            "question": gold["question"], "reference_answer": gold["answer"]["answer_text"],
            "candidate_answer": final["answer"]})
        task = verdict["decision"]
    if task and supported is None:
        verdict = cached_call("support", *support, {
            "question": gold["question"], "candidate_answer": final["answer"],
            "cited_evidence": [{"page": p, "text": pages.text(doc_id, p)} for p in final["cited_pages"]]})
        supported = verdict["decision"]
    elif not task:
        supported = None if state["answered"] else supported
    return {
        "system": system, "question_id": qid, "doc_id": doc_id,
        "answerable": gold["answer"]["is_answerable"],
        "multi_page": len(evidence_pages) > 1,
        "gold_pages": evidence_pages,
        "answered": state["answered"], "failure": state["failure"],
        "task_correct": bool(task),
        "supported": supported,
        "grounded_correct": bool(task) and supported is True,
        "answer": final.get("answer"), "cited_pages": final.get("cited_pages", []),
        "cost_usd": result.get("cost_usd", 0.0), "latency_s": result.get("latency_s", 0.0),
        "tool_calls": result.get("tool_calls"),
        "pages_read": result.get("pages_read") or result.get("retrieved_pages"),
    }


def pending_calls(system_results: dict[str, list[dict]], gold: dict[str, dict]) -> Counter:
    counts: Counter = Counter()
    for results in system_results.values():
        for result in results:
            if local_task_result(result, gold[result["question_id"]]) is None:
                counts["semantic"] += 1
                counts["support_upper_bound"] += bool((result["final"] or {}).get("cited_pages"))
    return counts


def load_system_results(specs: list[str]) -> dict[str, list[dict]]:
    out: dict[str, dict[str, dict]] = {}
    for spec in specs:
        system, path = spec.split("=", 1)
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            result = json.loads(line)
            out.setdefault(system, {})[result["question_id"]] = result  # a question may sit in two files
    return {system: list(results.values()) for system, results in out.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True, metavar="SYSTEM=PATH",
                        help="repeatable; a system may have several files")
    parser.add_argument("--output", required=True, type=Path, help="judged rows (jsonl)")
    parser.add_argument("--split", default="dev", choices=["dev", "final"], help="final reads locked-test labels (needs the V1 acknowledgement)")
    parser.add_argument("--max-usd", type=float, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    root = args.root

    systems = load_system_results(args.input)
    gold = {r["id"]: r for r in load_records(root / "data/raw/docscope/benchmark.json", "test" if args.split == "final" else "dev")}
    counts = pending_calls(systems, gold)
    print({s: len(r) for s, r in systems.items()}, dict(counts))
    if not args.execute:
        print("dry run only; add --execute to make paid judge calls")
        return

    semantic_cfg = json.loads((root / SEMANTIC_CONFIG).read_text(encoding="utf-8")) | {"timeout_seconds": 120}
    support_cfg = json.loads((root / SUPPORT_CONFIG).read_text(encoding="utf-8")) | {"timeout_seconds": 120}
    pricing = json.loads((root / "configs" / semantic_cfg["pricing_snapshot_path"]).read_text(encoding="utf-8"))
    ledger = CostLedger(args.max_usd)
    log = args.output.with_suffix(".requests.jsonl")
    semantic = (LlmClient(semantic_cfg, pricing, ledger, log_path=log), semantic_cfg)
    support = (LlmClient(support_cfg, pricing, ledger, log_path=log), support_cfg)

    cache_file = args.output.with_suffix(".judgments.jsonl")
    cache = {}
    if cache_file.exists():
        cache = {j["key"]: j for j in map(json.loads, cache_file.read_text(encoding="utf-8").splitlines())}
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    pages = PageStore(root)
    rows = []
    try:
        for system, results in systems.items():
            for result in results:
                rows.append(judge_row(system, result, gold[result["question_id"]], pages,
                                      semantic, support, cache, cache_file))
    except BudgetExceeded as error:
        print(f"stopped: {error}")
        return
    args.output.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(f"judged {len(rows)} rows; spent ${ledger.spent:.4f} over {ledger.calls} calls; wrote {args.output}")


if __name__ == "__main__":
    main()
