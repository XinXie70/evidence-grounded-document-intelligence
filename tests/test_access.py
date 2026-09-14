import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from egdi.access import LockedTestAccessError, load_records, require_evaluation_split_access
from egdi.constants import LOCKED_TEST_ACK, LOCKED_TEST_ENV


class LockedTestAccessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "benchmark.json"
        self.path.write_text(
            json.dumps([{"id": "d", "split": "dev"}, {"id": "t", "split": "test"}]),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_dev_is_available_by_default(self):
        self.assertEqual([record["id"] for record in load_records(self.path)], ["d"])

    def test_test_is_locked_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(LockedTestAccessError):
                load_records(self.path, "test")

    def test_exact_acknowledgement_unlocks_test(self):
        with patch.dict(os.environ, {LOCKED_TEST_ENV: LOCKED_TEST_ACK}, clear=True):
            self.assertEqual([record["id"] for record in load_records(self.path, "test")], ["t"])

    def test_evaluation_split_guard_uses_exact_acknowledgement(self):
        with patch.dict(os.environ, {}, clear=True):
            require_evaluation_split_access("development_calibration")
            with self.assertRaises(LockedTestAccessError):
                require_evaluation_split_access("locked_test")
        with patch.dict(os.environ, {LOCKED_TEST_ENV: LOCKED_TEST_ACK}, clear=True):
            require_evaluation_split_access("locked_test")


if __name__ == "__main__":
    unittest.main()
