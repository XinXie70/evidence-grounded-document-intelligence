"""Run B0 / B1 / A on a development question sample. Dry-run unless --execute is given."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from egdi.access import load_records, require_evaluation_split_access
from egdi.v2.agent import Agent, AgentLimits
from egdi.v2.baseline import INSTRUCTIONS, PAGE_BUDGETS, render_input, run_baseline
from egdi.v2.index import DocumentIndex
from egdi.v2.llm import BudgetExceeded, CostLedger, LlmClient, load_config
from egdi.v2.eval.select import build_pool, load_audit, record_final_selection
from egdi.v2.tools import MAX_PAGE_CHARS

DEV_SPLITS = ("development_tune", "development_calibration")
SPLITS = DEV_SPLITS + ("final",)
AGENT_TYPICAL_USD = 0.05  # the archived V2 agent averaged about this per question
ASSUMED_OUTPUT_TOKENS = 600  # reasoning + answer; deliberately generous for the estimate
CHARS_PER_TOKEN = 4


def sample_question_ids(pool: dict[str, Any], count: int, seed: str, subset: str = "mixed") -> list[str]:
    """Deterministic hash-ordered sample; ``subset="unanswerable"`` draws only unanswerable questions."""
    ids = list(pool["unanswerable_question_ids"])
    if subset == "mixed":
        ids += pool["answerable_question_ids"]
    return sorted(ids, key=lambda qid: hashlib.sha256(f"{seed}:{qid}".encode()).hexdigest())[:count]


def load_final(root: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Final evaluation only: needs the V1 locked-test acknowledgement; stores only a hash of the ids."""
    require_evaluation_split_access("locked_test")
    fixture = json.loads((root / "data/fixtures/v2_question_sets.json").read_text(encoding="utf-8"))
    wanted = set(fixture["final"]["document_ids"])
    records = {
        r["id"]: r
        for r in load_records(root / "data/raw/docscope/benchmark.json", "test")
        if r["pdf"]["doc_id_str"] in wanted
    }
    pool = build_pool(list(records.values()), load_audit(root / "data/manifests/pdf_audit.json"))
    record_final_selection(root / "data/fixtures/v2_final_selection.json", pool)
    return records, sorted(pool["answerable_question_ids"] + pool["unanswerable_question_ids"])


def failed_result(system: str, error: Exception, cost_usd: float) -> dict[str, Any]:
    return {
        "system": system, "final": None, "validation_errors": [], "error": f"{type(error).__name__}: {error}",
        "stop_reason": "error", "pages_read": [], "tool_calls": 0, "model_calls": 0,
        "usage": None, "cost_usd": round(cost_usd, 6), "latency_s": 0.0, "trace": [],
    }


def estimate_usd(input_chars: int, pricing: dict[str, Any]) -> float:
    tokens_in = input_chars / CHARS_PER_TOKEN + len(INSTRUCTIONS) / CHARS_PER_TOKEN
    return (tokens_in * pricing["input_usd_per_million"] + ASSUMED_OUTPUT_TOKENS * pricing["output_usd_per_million"]) / 1e6


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", required=True, choices=sorted(PAGE_BUDGETS) + ["A"])
    parser.add_argument("--split", default="development_tune", choices=SPLITS)
    parser.add_argument("--count", type=int, default=30)
    parser.add_argument("--seed", default="v2-dev")
    parser.add_argument("--subset", default="mixed", choices=["mixed", "unanswerable"])
    parser.add_argument("--max-usd", type=float, required=True, help="hard cap for this run")
    parser.add_argument("--execute", action="store_true", help="make paid API calls")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output-dir", type=Path, default=None, help="default results/v2_dev, or results/v2_final for the final split")
    args = parser.parse_args()

    root = args.root
    config, pricing = load_config(root)
    if args.split == "final":
        records, question_ids = load_final(root)
        tag = "all"
    else:
        pool = json.loads((root / "data/fixtures/v2_question_sets.json").read_text(encoding="utf-8"))[args.split]
        records = {r["id"]: r for r in load_records(root / "data/raw/docscope/benchmark.json", "dev")}
        question_ids = sample_question_ids(pool, args.count, args.seed, args.subset)
        tag = args.seed if args.subset == "mixed" else f"{args.seed}-{args.subset}"
    args.output_dir = args.output_dir or Path("results/v2_final" if args.split == "final" else "results/v2_dev")
    out_path = args.output_dir / f"{args.split}_{tag}_{args.system}.jsonl"
    done = set()
    if out_path.exists():
        done = {json.loads(line)["question_id"] for line in out_path.read_text(encoding="utf-8").splitlines()}

    documents: dict[str, DocumentIndex] = {}
    plan, estimate = [], 0.0
    for qid in question_ids:
        if qid in done:
            continue
        record = records[qid]
        doc_id = record["pdf"]["doc_id_str"]
        if doc_id not in documents:
            documents[doc_id] = DocumentIndex.load(root, doc_id)
        document = documents[doc_id]
        if args.system != "A":
            hits = document.search(record["question"], PAGE_BUDGETS[args.system])
            pages = {h["page"]: document.page_text[h["page"]][:MAX_PAGE_CHARS] for h in hits}
            estimate += estimate_usd(len(render_input(record["question"], pages)), pricing)
        plan.append((qid, record, document))
    print(f"{args.system} on {args.split}: {len(plan)} questions to run ({len(done)} already done)")
    if args.system == "A":
        limits = AgentLimits()
        estimate = AGENT_TYPICAL_USD * len(plan)
        print(f"agent per-question cap ${limits.max_cost_usd:.2f}, so the worst case is ${limits.max_cost_usd * len(plan):.2f}")
    print(f"estimated cost ${estimate:.3f}; hard cap ${args.max_usd:.2f}")
    if not args.execute:
        print("dry run only; add --execute to make paid calls")
        return

    ledger = CostLedger(args.max_usd)
    llm = LlmClient(config, pricing, ledger, log_path=args.output_dir / "requests.jsonl")
    agent = Agent(llm, AgentLimits()) if args.system == "A" else None
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a", encoding="utf-8") as handle:
        for qid, record, document in plan:
            spent_before = ledger.spent
            try:
                label = f"{args.system}:{qid}"
                if agent is not None:
                    result = agent.run(record["question"], document, label)
                else:
                    result = run_baseline(args.system, record["question"], document, llm, label=label)
            except BudgetExceeded as error:
                print(f"stopped: {error}")
                break
            except Exception as error:  # same policy as the baselines: a failed question is recorded, counts as wrong, is not retried
                result = failed_result(args.system, error, ledger.spent - spent_before)
            result.update(
                question_id=qid,
                doc_id=record["pdf"]["doc_id_str"],
                gold_pages=sorted({e["page"] for e in record["evidences"]}),
                is_answerable=record["answer"]["is_answerable"],
            )
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
            handle.flush()
    print(f"spent ${ledger.spent:.4f} over {ledger.calls} calls; results in {out_path}")


if __name__ == "__main__":
    main()
