"""Select and freeze the V2 question sets (V2_PLAN.md section 2).

Development and validation questions come from the V1 document-level split. The final
set is frozen as a document list plus a hash of this file; its labels are only read by
``build_final_question_ids`` under the V1 locked-test acknowledgement.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from egdi.access import load_records, require_evaluation_split_access
from egdi.io import sha256_file, write_json

# Evidence element types a text-layer system can answer from (no chart/image/figure).
ELIGIBLE_ELEMENT_TYPES = frozenset({"text", "paragraph_title", "title", "table"})

DEV_SPLITS = ("development_tune", "development_calibration")


def page_is_usable(audit_pages: dict[int, dict[str, Any]], page: int) -> bool:
    entry = audit_pages.get(page)
    return entry is not None and not entry["low_text"] and not entry["text_layer_missing"]


def is_eligible_answerable(
    record: dict[str, Any], audit: dict[str, dict[int, dict[str, Any]]]
) -> bool:
    """An answerable question whose every evidence is text/table on a usable text page."""
    if not record["answer"]["is_answerable"]:
        return False
    evidences = record.get("evidences") or []
    if not evidences:  # also drops the two answerable-but-no-evidence anomalies
        return False
    audit_pages = audit.get(record["pdf"]["doc_id_str"], {})
    return all(
        str(e["element_type"]).lower() in ELIGIBLE_ELEMENT_TYPES
        and page_is_usable(audit_pages, e["page"])
        for e in evidences
    )


def build_pool(
    records: list[dict[str, Any]], audit: dict[str, dict[int, dict[str, Any]]]
) -> dict[str, Any]:
    """Eligible answerable questions, plus unanswerable ones from the same documents."""
    answerable = [r for r in records if is_eligible_answerable(r, audit)]
    documents = {r["pdf"]["doc_id_str"] for r in answerable}
    unanswerable = [
        r
        for r in records
        if not r["answer"]["is_answerable"] and r["pdf"]["doc_id_str"] in documents
    ]
    multi_page = sum(len({e["page"] for e in r["evidences"]}) > 1 for r in answerable)
    return {
        "document_ids": sorted(documents),
        "answerable_question_ids": sorted(r["id"] for r in answerable),
        "unanswerable_question_ids": sorted(r["id"] for r in unanswerable),
        "counts": {
            "documents": len(documents),
            "answerable": len(answerable),
            "answerable_multi_page": multi_page,
            "answerable_single_page": len(answerable) - multi_page,
            "unanswerable": len(unanswerable),
        },
    }


def load_audit(path: Path) -> dict[str, dict[int, dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {d["doc_id"]: {p["page"]: p for p in d["pages"]} for d in payload["documents"]}


def final_document_ids(manifest: dict[str, Any], excluded: dict[str, Any]) -> list[str]:
    """Locked-test documents minus the ones the archived V2 touched; needs no labels."""
    return sorted(set(manifest["locked_test"]["document_ids"]) - set(excluded["document_ids"]))


def question_ids_sha256(question_ids: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(question_ids)).encode()).hexdigest()


def pool_for_documents(
    records: list[dict[str, Any]], documents: list[str], audit: dict[str, dict[int, dict[str, Any]]]
) -> dict[str, Any]:
    wanted = set(documents)
    return build_pool([r for r in records if r["pdf"]["doc_id_str"] in wanted], audit)


def build_final_question_ids(
    benchmark_path: Path, documents: list[str], audit: dict[str, dict[int, dict[str, Any]]]
) -> dict[str, Any]:
    """Final-evaluation day only: reads locked-test labels, so it needs the V1 guard."""
    require_evaluation_split_access("locked_test")
    return pool_for_documents(load_records(benchmark_path, "test"), documents, audit)


def record_final_selection(path: Path, pool: dict[str, Any]) -> dict[str, Any]:
    """Store only counts and a hash of the question ids; verify the hash on every later run."""
    ids = pool["answerable_question_ids"] + pool["unanswerable_question_ids"]
    entry = {
        "schema_version": 1,
        "counts": pool["counts"],
        "question_ids_sha256": question_ids_sha256(ids),
        "select_py_sha256": sha256_file(Path(__file__)),
    }
    if path.exists():
        previous = json.loads(path.read_text(encoding="utf-8"))
        if previous["question_ids_sha256"] != entry["question_ids_sha256"]:
            raise RuntimeError("final question set differs from the one recorded earlier")
        return previous
    write_json(path, entry)
    return entry


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, default=Path("data/fixtures/v2_question_sets.json"))
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite frozen selection: {args.output}")

    root = args.root
    manifest = json.loads((root / "data/manifests/split_manifest.json").read_text(encoding="utf-8"))
    excluded = json.loads(
        (root / "data/fixtures/v2_excluded_locked_test_documents.json").read_text(encoding="utf-8")
    )
    audit = load_audit(root / "data/manifests/pdf_audit.json")
    dev_records = {r["id"]: r for r in load_records(root / "data/raw/docscope/benchmark.json", "dev")}

    result: dict[str, Any] = {
        "schema_version": 1,
        "rules": {
            "eligible_element_types": sorted(ELIGIBLE_ELEMENT_TYPES),
            "unusable_pages": ["low_text", "text_layer_missing"],
            "unanswerable": "kept only from documents that have an eligible answerable question",
        },
        "select_py_sha256": sha256_file(Path(__file__)),
    }
    for split in DEV_SPLITS:
        records = [dev_records[qid] for qid in manifest[split]["question_ids"]]
        result[split] = build_pool(records, audit)

    documents = final_document_ids(manifest, excluded)
    result["final"] = {
        "document_ids": documents,
        "document_count": len(documents),
        "question_ids": "not read before v2-freeze; regenerate with build_final_question_ids",
    }
    write_json(args.output, result)
    print(json.dumps({s: result[s]["counts"] for s in DEV_SPLITS} | {"final_documents": len(documents)}, indent=2))


if __name__ == "__main__":
    main()
