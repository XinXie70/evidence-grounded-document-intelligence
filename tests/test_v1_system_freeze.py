import tempfile
import unittest
from pathlib import Path

from egdi.io import sha256_file
from egdi.v1_system_freeze import build_system_freeze, verify_system_freeze


class V1SystemFreezeTests(unittest.TestCase):
    def test_hashes_unique_declared_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("a", encoding="utf-8")
            result = build_system_freeze({
                "status": "ready_to_hash_before_locked_test",
                "components": {"runtime": ["a.txt"]},
            }, root)
            self.assertEqual(result["component_count"], 1)
            self.assertEqual(len(result["components"]["runtime"][0]["sha256"]), 64)

    def test_rejects_missing_and_duplicate_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("a", encoding="utf-8")
            with self.assertRaises(FileNotFoundError):
                build_system_freeze({
                    "status": "ready_to_hash_before_locked_test",
                    "components": {"runtime": ["missing.txt"]},
                }, root)

    def test_verifies_unchanged_files_and_spec(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            component = root / "a.txt"
            spec = root / "spec.json"
            component.write_text("a", encoding="utf-8")
            spec.write_text("{}", encoding="utf-8")
            manifest = build_system_freeze({
                "status": "ready_to_hash_before_locked_test",
                "components": {"runtime": ["a.txt"]},
            }, root)
            manifest["freeze_spec_sha256"] = sha256_file(spec)
            verified = verify_system_freeze(manifest, root, spec_path=spec)
            self.assertEqual(verified["status"], "verified_unchanged_before_locked_test")
            component.write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "verification failed"):
                verify_system_freeze(manifest, root, spec_path=spec)

    def test_verifier_rejects_accessed_or_inconsistent_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("a", encoding="utf-8")
            manifest = build_system_freeze({
                "status": "ready_to_hash_before_locked_test",
                "components": {"runtime": ["a.txt"]},
            }, root)
            manifest["locked_test_accessed"] = True
            with self.assertRaisesRegex(ValueError, "pre-test boundary"):
                verify_system_freeze(manifest, root)
            with self.assertRaises(ValueError):
                build_system_freeze({
                    "status": "ready_to_hash_before_locked_test",
                    "components": {"one": ["a.txt"], "two": ["a.txt"]},
                }, root)


if __name__ == "__main__":
    unittest.main()
