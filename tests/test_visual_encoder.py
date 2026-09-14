import tempfile
import unittest
from pathlib import Path

from egdi.visual_encoder import (
    COLSMOL_256M_BASE_REVISION,
    COLSMOL_256M_MODEL_ID,
    COLSMOL_256M_REVISION,
    resolve_colsmol_model_source,
    validate_colsmol_base_snapshot,
)


class VisualEncoderTests(unittest.TestCase):
    def test_resolves_exact_offline_adapter_and_base_snapshots(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            adapter = (
                root
                / "models--vidore--colSmol-256M"
                / "snapshots"
                / COLSMOL_256M_REVISION
            )
            adapter.mkdir(parents=True)
            (adapter / "modules.json").write_text("{}", encoding="utf-8")
            base = (
                root
                / "models--vidore--ColSmolVLM-Instruct-256M-base"
                / "snapshots"
                / COLSMOL_256M_BASE_REVISION
            )
            base.mkdir(parents=True)
            (base / "config.json").write_text("{}", encoding="utf-8")
            (base / "model.safetensors").write_bytes(b"fixture")

            self.assertEqual(
                resolve_colsmol_model_source(directory, local_files_only=True),
                str(adapter),
            )
            self.assertEqual(validate_colsmol_base_snapshot(directory), base)

    def test_online_source_uses_model_id(self):
        self.assertEqual(
            resolve_colsmol_model_source(None, local_files_only=False),
            COLSMOL_256M_MODEL_ID,
        )

    def test_offline_source_rejects_missing_snapshots(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "adapter snapshot"):
                resolve_colsmol_model_source(directory, local_files_only=True)
            with self.assertRaisesRegex(RuntimeError, "base snapshot"):
                validate_colsmol_base_snapshot(directory)


if __name__ == "__main__":
    unittest.main()
