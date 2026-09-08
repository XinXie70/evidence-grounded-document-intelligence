import json
from pathlib import Path
import tempfile
import unittest

from egdi.oracle_region import (
    DOCSCOPE_RENDER_DPI,
    bbox_to_pixel_crop,
    build_crop_specs,
    build_pdftoppm_command,
    _load_question,
)


class OracleRegionTests(unittest.TestCase):
    def setUp(self):
        self.record = {
            "id": "doc-a::q1",
            "question": "What does the table example say?",
            "answer": {"answer_text": "SECRET", "is_answerable": True},
            "pdf": {"doc_id_str": "doc-a"},
            "evidences": [
                {
                    "local_id": "e1",
                    "page": 14,
                    "bbox": [167.7, 68, 260.9, 447.2],
                    "element_type": "table",
                }
            ],
            "facts": [
                {
                    "local_id": "f1",
                    "text_description": "SECRET FACT",
                    "evidence_local_id": "e1",
                }
            ],
        }

    def test_bbox_rounds_outward_without_dpi_rescaling(self):
        self.assertEqual(
            bbox_to_pixel_crop([167.7, 68, 260.9, 447.2]),
            (167, 68, 261, 448),
        )

    def test_bbox_rejects_invalid_values_and_area(self):
        for bbox in ([0, 0, 0, 1], [-1, 0, 1, 1], [0, 0, float("nan"), 1]):
            with self.subTest(bbox=bbox), self.assertRaises(ValueError):
                bbox_to_pixel_crop(bbox)

    def test_crop_specs_exclude_gold_answer_and_facts(self):
        specs = build_crop_specs(self.record)
        serialized = json.dumps(specs)

        self.assertEqual(specs[0]["page"], 14)
        self.assertEqual(specs[0]["pixel_crop"], [167, 68, 261, 448])
        self.assertNotIn("SECRET", serialized)
        self.assertNotIn("answer", serialized)
        self.assertNotIn("facts", serialized)

    def test_pdftoppm_command_pins_cropbox_dpi_page_and_dimensions(self):
        spec = build_crop_specs(self.record)[0]
        command = build_pdftoppm_command(
            "pdftoppm", "doc-a.pdf", "crop-e1", spec
        )

        self.assertIn("-cropbox", command)
        self.assertEqual(command[command.index("-r") + 1], str(DOCSCOPE_RENDER_DPI))
        self.assertEqual(command[command.index("-f") + 1], "14")
        self.assertEqual(command[command.index("-W") + 1], "94")
        self.assertEqual(command[command.index("-H") + 1], "380")

    def test_question_loader_cannot_select_locked_test_record(self):
        records = [
            {**self.record, "id": "dev-q", "split": "dev"},
            {**self.record, "id": "locked-q", "split": "test"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            benchmark = Path(directory) / "benchmark.json"
            benchmark.write_text(json.dumps(records), encoding="utf-8")

            self.assertEqual(_load_question(benchmark, "dev-q")["id"], "dev-q")
            with self.assertRaisesRegex(ValueError, "expected exactly one"):
                _load_question(benchmark, "locked-q")


if __name__ == "__main__":
    unittest.main()
