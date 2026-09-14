"""Hash every declared V1 component before the locked test is opened."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .io import sha256_file, write_json


def build_system_freeze(spec: dict[str, Any], root: Path) -> dict[str, Any]:
    components = spec.get("components")
    if spec.get("status") != "ready_to_hash_before_locked_test" or not isinstance(components, dict):
        raise ValueError("freeze spec is not ready")
    frozen: dict[str, list[dict[str, str]]] = {}
    seen: set[str] = set()
    for category, paths in components.items():
        if not isinstance(category, str) or not isinstance(paths, list) or not paths:
            raise ValueError("every component category requires a non-empty path list")
        rows = []
        for relative in paths:
            if not isinstance(relative, str) or relative.startswith("/") or relative in seen:
                raise ValueError("component paths must be unique relative paths")
            seen.add(relative)
            path = root / relative
            if not path.is_file():
                raise FileNotFoundError(f"frozen component is missing: {relative}")
            rows.append({"path": relative, "sha256": sha256_file(path)})
        frozen[category] = rows
    return {
        "schema_version": 1,
        "status": "v1_system_frozen_before_locked_test",
        "locked_test_accessed": False,
        "mutation_policy": "Any change to a listed file after this manifest invalidates the V1 locked-test run.",
        "component_count": len(seen),
        "components": frozen,
    }


def verify_system_freeze(
    manifest: dict[str, Any], root: Path, *, spec_path: Path | None = None
) -> dict[str, Any]:
    """Fail closed if any frozen file, declaration, or pre-test boundary changed."""
    if manifest.get("status") != "v1_system_frozen_before_locked_test":
        raise ValueError("system-freeze manifest has an invalid status")
    if manifest.get("locked_test_accessed") is not False:
        raise ValueError("system-freeze manifest does not preserve the pre-test boundary")
    components = manifest.get("components")
    if not isinstance(components, dict) or not components:
        raise ValueError("system-freeze components are missing")
    seen: set[str] = set()
    mismatches = []
    for category, rows in components.items():
        if not isinstance(category, str) or not isinstance(rows, list) or not rows:
            raise ValueError("system-freeze component category is invalid")
        for row in rows:
            relative = row.get("path") if isinstance(row, dict) else None
            expected = row.get("sha256") if isinstance(row, dict) else None
            if (
                not isinstance(relative, str)
                or relative.startswith("/")
                or relative in seen
                or not isinstance(expected, str)
                or len(expected) != 64
            ):
                raise ValueError("system-freeze component entry is invalid")
            seen.add(relative)
            path = root / relative
            actual = sha256_file(path) if path.is_file() else None
            if actual != expected:
                mismatches.append({"path": relative, "expected": expected, "actual": actual})
    if manifest.get("component_count") != len(seen):
        raise ValueError("system-freeze component count is inconsistent")
    if spec_path is not None:
        expected_spec = manifest.get("freeze_spec_sha256")
        actual_spec = sha256_file(spec_path) if spec_path.is_file() else None
        if actual_spec != expected_spec:
            mismatches.append({
                "path": str(spec_path), "expected": expected_spec, "actual": actual_spec
            })
    if mismatches:
        raise ValueError(f"system freeze verification failed: {mismatches}")
    return {
        "status": "verified_unchanged_before_locked_test",
        "component_count": len(seen),
        "locked_test_accessed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        result = verify_system_freeze(
            json.loads(args.output.read_text(encoding="utf-8")),
            args.root.resolve(),
            spec_path=args.spec,
        )
        print(json.dumps(result, indent=2))
        return
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite immutable output: {args.output}")
    result = build_system_freeze(
        json.loads(args.spec.read_text(encoding="utf-8")), args.root.resolve()
    )
    result["freeze_spec_sha256"] = sha256_file(args.spec)
    write_json(args.output, result)
    print(json.dumps({
        "status": result["status"],
        "component_count": result["component_count"],
        "output": str(args.output),
    }, indent=2))


if __name__ == "__main__":
    main()
