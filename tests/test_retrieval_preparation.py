import unittest
from pathlib import Path
from unittest.mock import Mock

from egdi.retrieval_preparation import prepare_retrieval
from egdi.text import build_page_record


class RetrievalPreparationTests(unittest.TestCase):
    @staticmethod
    def records(texts):
        return [
            build_page_record("doc-a", page, text)
            for page, text in enumerate(texts, start=1)
        ]

    def test_r2_plan_requires_ocr_without_executing_builder(self):
        builder = Mock()
        result = prepare_retrieval(
            "What is the difference between the two dates?",
            self.records(["", ""]),
            ocr_builder=builder,
        )
        self.assertEqual(result["status"], "ocr_required")
        self.assertEqual(result["action"], "build_full_document_ocr_corpus")
        self.assertFalse(result["execute_ocr_requested"])
        builder.assert_not_called()

    def test_r2_execute_calls_builder_with_frozen_settings(self):
        builder = Mock(return_value={"page_count": 2})
        result = prepare_retrieval(
            "What is the difference between the two dates?",
            self.records(["", ""]),
            execute_ocr=True,
            pdf_path=Path("source.pdf"),
            ocr_output_dir=Path("ocr-output"),
            pdftoppm="pdftoppm",
            tesseract="tesseract",
            ocr_builder=builder,
        )
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["corpus_kind"], "ocr_text")
        self.assertEqual(result["ocr_page_records"], "ocr-output/page_records.jsonl")
        builder.assert_called_once_with(
            Path("source.pdf"),
            "doc-a",
            Path("ocr-output"),
            pdftoppm="pdftoppm",
            tesseract="tesseract",
            dpi=200,
            language="eng",
            oem=1,
            psm=3,
        )

    def test_r2_execute_rejects_missing_execution_inputs(self):
        with self.assertRaisesRegex(ValueError, "R2 OCR execution requires"):
            prepare_retrieval(
                "What is the difference between the two dates?",
                self.records(["", ""]),
                execute_ocr=True,
            )

    def test_non_r2_routes_never_call_full_document_ocr(self):
        cases = (
            (
                "What age threshold applies?",
                self.records(["usable native text " * 20]),
                "use_native_page_records",
            ),
            (
                "What percentage appears in the chart?",
                self.records(["usable native text " * 20]),
                "render_retrieved_candidate_pages",
            ),
            (
                "How many charts appear across the entire document?",
                self.records([""] * 3),
                "inspect_complete_document_or_abstain",
            ),
        )
        for question, records, expected_action in cases:
            with self.subTest(expected_action=expected_action):
                builder = Mock()
                result = prepare_retrieval(
                    question,
                    records,
                    execute_ocr=True,
                    pdf_path=Path("source.pdf"),
                    ocr_output_dir=Path("ocr-output"),
                    pdftoppm="pdftoppm",
                    tesseract="tesseract",
                    ocr_builder=builder,
                )
                self.assertEqual(result["action"], expected_action)
                builder.assert_not_called()
                self.assertFalse(result["uses_gold_or_answer_labels"])


if __name__ == "__main__":
    unittest.main()
