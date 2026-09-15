"""Open guarded evaluation labels after prediction freeze and prepare judge inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .access import require_evaluation_split_access
from .io import sha256_file, write_json


def _benchmark_index(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {item.get("id"): item for item in records if isinstance(item, dict)}
    if len(result) != len(records) or None in result:
        raise ValueError("benchmark IDs must be present and unique")
    return result


def build_inputs(
    selection: dict[str, Any], benchmark: list[dict[str, Any]], reasoning_manifest: dict[str, Any],
    predictions_dir: Path, output_dir: Path,
) -> dict[str, Any]:
    split = selection.get("split")
    if split not in {"development_calibration", "locked_test"}:
        raise ValueError("selection must be development_calibration or locked_test")
    require_evaluation_split_access(split)
    if reasoning_manifest.get("split") != split:
        raise ValueError("selection and reasoning manifest splits must match")
    by_benchmark = _benchmark_index(benchmark)
    reasoning_cases = {item["question_id"]: item for item in reasoning_manifest["cases"]}
    cases = []
    semantic_count = support_count = 0
    for selected in selection["questions"]:
        qid, pilot_id = selected["question_id"], selected["pilot_id"]
        gold = by_benchmark.pop(qid, None)
        if gold is None:
            raise ValueError(f"benchmark record missing: {qid}")
        result_path = predictions_dir / pilot_id / "real_retrieval.json"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get("question_id") != qid:
            raise ValueError(f"prediction identity mismatch: {result_path}")
        output = result["output"]
        prediction_valid = result.get("validation", {}).get("valid") is True
        operational_failure = isinstance(result.get("operational_failure"), dict)
        system_failure = operational_failure or not prediction_valid
        answerable = gold["answer"]["is_answerable"]
        reference = gold["answer"]["answer_text"]
        candidate = output["answer"]
        cited_pages = output["cited_pages"]
        reasoning_case = reasoning_cases[qid]
        if system_failure:
            semantic = {
                "mode": "local",
                "task_correct": False,
                "rule": (
                    "operational_failure_counts_as_task_failure"
                    if operational_failure
                    else "invalid_prediction_contract_counts_as_task_failure"
                ),
            }
        else:
            semantic = {"mode": "judge"} if answerable and candidate is not None else {
                "mode": "local",
                "task_correct": bool(not answerable and candidate is None),
                "rule": (
                    "gold_unanswerable_and_abstained"
                    if not answerable and candidate is None
                    else "answerability_status_mismatch"
                ),
            }
        semantic_path = None
        if semantic["mode"] == "judge":
            semantic_count += 1
            semantic_path = output_dir / pilot_id / "semantic.json"
            write_json(semantic_path, {
                "schema_version": 1, "judge_type": "semantic", "question_id": qid,
                "question": gold["question"], "reference_answer": reference,
                "candidate_answer": candidate,
            })
        if system_failure:
            support = {
                "mode": "local",
                "evidence_supported": candidate is None,
                "rule": (
                    "operational_failure_no_answer_claim"
                    if operational_failure and candidate is None
                    else "invalid_prediction_contract_is_unsupported"
                ),
            }
            support_path = None
        elif candidate is None:
            support = {"mode": "local", "evidence_supported": True, "rule": "no_answer_claim"}
            support_path = None
        elif not cited_pages:
            support = {"mode": "local", "evidence_supported": False, "rule": "answer_without_citation"}
            support_path = None
        else:
            original_input = json.loads(Path(reasoning_case["reasoning_input"]["path"]).read_text())
            evidence_by_page = {item["page"]: item["text"] for item in original_input["model_input"]["evidence"]}
            cited_evidence = [{"page": page, "text": evidence_by_page[page]} for page in cited_pages]
            support = {"mode": "judge"}
            support_count += 1
            support_path = output_dir / pilot_id / "support.json"
            write_json(support_path, {
                "schema_version": 1, "judge_type": "support", "question_id": qid,
                "question": gold["question"], "candidate_answer": candidate,
                "cited_evidence": cited_evidence,
            })
        gold_pages = sorted({item["page"] for item in gold.get("evidences", [])})
        cases.append({
            "pilot_id": pilot_id, "question_id": qid, "doc_id": selected["doc_id"],
            "route": reasoning_case["route"], "gold_is_answerable": answerable,
            "gold_answer": reference, "gold_pages": gold_pages,
            "prediction": {
                "answer": candidate,
                "status": output["status"],
                "cited_pages": cited_pages,
                "valid": prediction_valid,
                "operational_failure": operational_failure,
            },
            "semantic": semantic,
            "semantic_input": None if semantic_path is None else {"path": str(semantic_path), "sha256": sha256_file(semantic_path)},
            "support": support,
            "support_input": None if support_path is None else {"path": str(support_path), "sha256": sha256_file(support_path)},
        })
    return {
        "schema_version": 1, "status": "prepared_after_scoring_protocol_freeze",
        "split": split, "case_count": len(cases),
        "semantic_judge_request_count": semantic_count,
        "support_judge_request_count": support_count,
        "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--benchmark", required=True, type=Path)
    parser.add_argument("--reasoning-manifest", required=True, type=Path)
    parser.add_argument("--predictions-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    selection = json.loads(args.selection.read_text())
    require_evaluation_split_access(selection.get("split"))
    manifest = build_inputs(
        selection, json.loads(args.benchmark.read_text()),
        json.loads(args.reasoning_manifest.read_text()), args.predictions_dir, args.output_dir,
    )
    manifest["artifacts"] = {
        "scoring_protocol_sha256": sha256_file(Path("V1_CALIBRATION_SCORING_PROTOCOL.md")),
        "selection_sha256": sha256_file(args.selection),
        "benchmark_sha256": sha256_file(args.benchmark),
        "reasoning_manifest_sha256": sha256_file(args.reasoning_manifest),
    }
    path = args.output_dir / "manifest.json"
    write_json(path, manifest)
    print(json.dumps({k: manifest[k] for k in (
        "status", "case_count", "semantic_judge_request_count", "support_judge_request_count", "artifacts"
    )}, indent=2))


if __name__ == "__main__":
    main()
