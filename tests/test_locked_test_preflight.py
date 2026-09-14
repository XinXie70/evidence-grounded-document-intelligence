import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from egdi.constants import LOCKED_TEST_ACK, LOCKED_TEST_ENV
from egdi.locked_test_preflight import run_preflight


def fixture(root: Path):
    locked_docs = [f"d{index:03d}" for index in range(156)]
    checksum_lines = []
    for doc_id in locked_docs:
        relative = f"data/raw/docscope/pdfs/{doc_id}.pdf"
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(doc_id.encode())
        checksum_lines.append(f"{hashlib.sha256(doc_id.encode()).hexdigest()}  {relative}")
    checksums = root / "checksums.sha256"
    checksums.write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    return {
        "root": root,
        "split_manifest": {
            "development_tune": {"document_ids": ["tune"]},
            "development_calibration": {"document_ids": ["cal"]},
            "locked_test": {
                "document_count": 156, "document_ids": locked_docs,
                "question_count": 730, "question_ids_sha256": "a" * 64,
            },
        },
        "pdf_audit": {
            "observed_pdf_count": 273, "openable_pdf_count": 273,
            "total_pages": 14014, "documents": [{"openable": True}] * 273,
        },
        "threshold": {
            "status": "protocol_corrected_and_frozen_before_locked_test",
            "locked_test_accessed": False,
            "confidence_threshold": 0.3566666666666667,
        },
        "environment": {"status": "recorded_before_locked_test", "locked_test_accessed": False},
        "checksums_path": checksums,
    }


class LockedTestPreflightTests(unittest.TestCase):
    def test_verifies_sealed_metadata_and_all_locked_pdfs(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run_preflight(**fixture(Path(directory)))
            self.assertEqual(result["locked_pdf_checksums_verified"], 156)
            self.assertFalse(result["locked_test_accessed"])
            self.assertFalse(result["paid_api_called"])

    def test_rejects_enabled_guard_and_existing_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            args = fixture(Path(directory))
            with patch.dict("os.environ", {LOCKED_TEST_ENV: LOCKED_TEST_ACK}):
                with self.assertRaisesRegex(RuntimeError, "disabled"):
                    run_preflight(**args)
            (Path(directory) / "forbidden").mkdir()
            with self.assertRaisesRegex(ValueError, "already exist"):
                run_preflight(**args, forbidden_artifacts=("forbidden",))


if __name__ == "__main__":
    unittest.main()
