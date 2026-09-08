import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfWriter

from egdi.corpus import read_page_records_jsonl
from egdi.ocr_corpus import (
    build_ocr_corpus,
    build_render_command,
    build_tesseract_command,
    discover_rendered_pages,
)


class OcrCorpusTests(unittest.TestCase):
    def test_commands_pin_rendering_and_ocr_settings(self):
        self.assertEqual(
            build_render_command("pdftoppm", Path("source.pdf"), Path("pages/render")),
            ["pdftoppm", "-png", "-r", "200", "source.pdf", "pages/render"],
        )
        self.assertEqual(
            build_tesseract_command(
                "tesseract", Path("page-0001.png"), Path("page-0001")
            ),
            [
                "tesseract",
                "page-0001.png",
                "page-0001",
                "-l",
                "eng",
                "--oem",
                "1",
                "--psm",
                "3",
            ],
        )

    def test_discovery_rejects_page_gaps(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "render-1.png").write_bytes(b"one")
            (root / "render-3.png").write_bytes(b"three")
            with self.assertRaisesRegex(ValueError, "sequential"):
                discover_rendered_pages(root)

    def test_builder_creates_verified_page_records_and_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf_path = root / "source.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=100, height=100)
            writer.add_blank_page(width=100, height=100)
            with pdf_path.open("wb") as handle:
                writer.write(handle)
            output_dir = root / "ocr"
            commands = []

            def fake_run(command, *, check, capture_output, text):
                commands.append(command)
                if command[1:] == ["-v"]:
                    return subprocess.CompletedProcess(command, 0, "", "pdftoppm 1.0\n")
                if command[1:] == ["--version"]:
                    return subprocess.CompletedProcess(command, 0, "tesseract 5.5.3\n", "")
                if command[0] == "pdftoppm":
                    prefix = Path(command[-1])
                    (prefix.parent / "render-1.png").write_bytes(b"image-one")
                    (prefix.parent / "render-2.png").write_bytes(b"image-two")
                elif command[0] == "tesseract":
                    page = int(Path(command[1]).stem.split("-")[-1])
                    Path(command[2] + ".txt").write_text(
                        f"OCR evidence text for physical page {page}. " * 5,
                        encoding="utf-8",
                    )
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch("egdi.ocr_corpus.subprocess.run", side_effect=fake_run):
                manifest = build_ocr_corpus(
                    pdf_path,
                    "doc-test",
                    output_dir,
                    pdftoppm="pdftoppm",
                    tesseract="tesseract",
                )

            records = read_page_records_jsonl(output_dir / "page_records.jsonl")
            self.assertEqual([record.page for record in records], [1, 2])
            self.assertTrue(all(record.extraction_status == "ok" for record in records))
            self.assertEqual(manifest["page_count"], 2)
            self.assertEqual(manifest["page_records"]["record_count"], 2)
            self.assertEqual(manifest["page_records"]["status_counts"]["ok"], 2)
            self.assertTrue((output_dir / "manifest.json").is_file())
            self.assertEqual(len([command for command in commands if command[0] == "tesseract"]), 3)

    def test_builder_refuses_to_overwrite_existing_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf_path = root / "source.pdf"
            pdf_path.write_bytes(b"not read because output check runs first")
            output_dir = root / "existing"
            output_dir.mkdir()
            with self.assertRaisesRegex(FileExistsError, "refusing to overwrite"):
                build_ocr_corpus(
                    pdf_path,
                    "doc-test",
                    output_dir,
                    pdftoppm="pdftoppm",
                    tesseract="tesseract",
                )

    def test_builder_refuses_unfinished_staging_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf_path = root / "source.pdf"
            pdf_path.write_bytes(b"not read because staging check runs first")
            (root / "ocr.partial").mkdir()
            with self.assertRaisesRegex(FileExistsError, "unfinished OCR staging"):
                build_ocr_corpus(
                    pdf_path,
                    "doc-test",
                    root / "ocr",
                    pdftoppm="pdftoppm",
                    tesseract="tesseract",
                )


if __name__ == "__main__":
    unittest.main()
