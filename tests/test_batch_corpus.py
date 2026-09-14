import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from egdi.batch_corpus import (
    execute_plan,
    plan_development_tune,
    plan_document_split,
    summarize_plan,
)
from egdi.constants import LOCKED_TEST_ACK, LOCKED_TEST_ENV
from egdi.corpus import write_page_records_jsonl
from egdi.text import build_page_record


class DevelopmentTuneBatchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.pdf_dir = self.root / "pdfs"
        self.output_dir = self.root / "outputs"
        self.pdf_dir.mkdir()
        self.output_dir.mkdir()
        self.split_manifest = self.root / "splits.json"
        self.pdf_audit = self.root / "audit.json"

        self.pdf_bytes = {"tune-a": b"pdf-a", "tune-b": b"pdf-b"}
        for doc_id, content in self.pdf_bytes.items():
            (self.pdf_dir / f"{doc_id}.pdf").write_bytes(content)
        self.split_manifest.write_text(
            json.dumps(
                {
                    "development_tune": {
                        "document_count": 2,
                        "document_ids": ["tune-b", "tune-a"],
                    },
                    "development_calibration": {
                        "document_ids": ["calibration-a"]
                    },
                    "locked_test": {"document_ids": ["locked-a"]},
                }
            ),
            encoding="utf-8",
        )
        self.pdf_audit.write_text(
            json.dumps(
                {
                    "documents": [
                        {
                            "doc_id": doc_id,
                            "openable": True,
                            "page_count": 2,
                            "sha256": hashlib.sha256(content).hexdigest(),
                        }
                        for doc_id, content in self.pdf_bytes.items()
                    ]
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_dry_run_verifies_existing_and_reports_pending_without_writing(self):
        existing = [
            build_page_record("tune-a", 1, "alpha"),
            build_page_record("tune-a", 2, "beta"),
        ]
        write_page_records_jsonl(self.output_dir / "tune-a.jsonl", existing)

        plans = plan_development_tune(
            self.split_manifest, self.pdf_audit, self.pdf_dir, self.output_dir
        )
        summary = summarize_plan(plans)

        self.assertEqual([plan.doc_id for plan in plans], ["tune-a", "tune-b"])
        self.assertEqual(summary["document_count"], 2)
        self.assertEqual(summary["expected_page_records"], 4)
        self.assertEqual(summary["verified_existing_documents"], 1)
        self.assertEqual(summary["pending_documents"], 1)
        self.assertFalse((self.output_dir / "tune-b.jsonl").exists())

    def test_rejects_calibration_locked_unknown_and_duplicate_requests(self):
        for doc_id in ("calibration-a", "locked-a", "unknown-a"):
            with self.subTest(doc_id=doc_id), self.assertRaises(ValueError):
                plan_development_tune(
                    self.split_manifest,
                    self.pdf_audit,
                    self.pdf_dir,
                    self.output_dir,
                    requested_doc_ids=[doc_id],
                )
        with self.assertRaises(ValueError):
            plan_development_tune(
                self.split_manifest,
                self.pdf_audit,
                self.pdf_dir,
                self.output_dir,
                requested_doc_ids=["tune-a", "tune-a"],
            )

    def test_calibration_planner_is_allowed_and_locked_test_is_guarded(self):
        calibration_pdf = self.pdf_dir / "calibration-a.pdf"
        calibration_pdf.write_bytes(b"calibration-pdf")
        split_manifest = json.loads(self.split_manifest.read_text(encoding="utf-8"))
        split_manifest["development_calibration"]["document_count"] = 1
        split_manifest["locked_test"]["document_count"] = 1
        self.split_manifest.write_text(json.dumps(split_manifest), encoding="utf-8")
        audit = json.loads(self.pdf_audit.read_text(encoding="utf-8"))
        audit["documents"].append({
            "doc_id": "calibration-a",
            "openable": True,
            "page_count": 1,
            "sha256": hashlib.sha256(b"calibration-pdf").hexdigest(),
        })
        self.pdf_audit.write_text(json.dumps(audit), encoding="utf-8")

        plans = plan_document_split(
            self.split_manifest,
            self.pdf_audit,
            self.pdf_dir,
            self.output_dir,
            "development_calibration",
        )
        self.assertEqual([plan.doc_id for plan in plans], ["calibration-a"])
        self.assertEqual(
            summarize_plan(plans, split_name="development_calibration")["split"],
            "development_calibration",
        )
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(RuntimeError):
            plan_document_split(
                self.split_manifest,
                self.pdf_audit,
                self.pdf_dir,
                self.output_dir,
                "locked_test",
            )

        locked_pdf = self.pdf_dir / "locked-a.pdf"
        locked_pdf.write_bytes(b"locked-pdf")
        audit = json.loads(self.pdf_audit.read_text(encoding="utf-8"))
        audit["documents"].append({
            "doc_id": "locked-a",
            "openable": True,
            "page_count": 1,
            "sha256": hashlib.sha256(b"locked-pdf").hexdigest(),
        })
        self.pdf_audit.write_text(json.dumps(audit), encoding="utf-8")
        with patch.dict(os.environ, {LOCKED_TEST_ENV: LOCKED_TEST_ACK}, clear=True):
            locked_plans = plan_document_split(
                self.split_manifest,
                self.pdf_audit,
                self.pdf_dir,
                self.output_dir,
                "locked_test",
            )
        self.assertEqual([plan.doc_id for plan in locked_plans], ["locked-a"])

    def test_rejects_invalid_existing_output(self):
        write_page_records_jsonl(
            self.output_dir / "tune-a.jsonl",
            [build_page_record("tune-a", 1, "only one page")],
        )

        with self.assertRaisesRegex(ValueError, "page count mismatch"):
            plan_development_tune(
                self.split_manifest,
                self.pdf_audit,
                self.pdf_dir,
                self.output_dir,
            )

    def test_execute_generates_only_pending_and_verifies_checksums(self):
        existing = [
            build_page_record("tune-a", 1, "alpha " * 30),
            build_page_record("tune-a", 2, "beta " * 30),
        ]
        generated = [
            build_page_record("tune-b", 1, "gamma " * 30),
            build_page_record("tune-b", 2, ""),
        ]
        write_page_records_jsonl(self.output_dir / "tune-a.jsonl", existing)
        plans = plan_development_tune(
            self.split_manifest, self.pdf_audit, self.pdf_dir, self.output_dir
        )

        with patch("egdi.batch_corpus.extract_pdf_page_records", return_value=generated) as extract:
            manifest = execute_plan(plans)

        extract.assert_called_once()
        self.assertEqual(extract.call_args.args[1], "tune-b")
        self.assertEqual(manifest["document_count"], 2)
        self.assertEqual(manifest["page_record_count"], 4)
        self.assertEqual(manifest["generated_documents"], 1)
        self.assertEqual(manifest["verified_existing_documents"], 1)
        self.assertEqual(manifest["status_counts"]["ok"], 3)
        self.assertEqual(manifest["status_counts"]["text_layer_missing"], 1)


if __name__ == "__main__":
    unittest.main()
