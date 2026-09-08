import json
import unittest

from egdi.oracle_region_input import build_oracle_region_record


class OracleRegionInputTests(unittest.TestCase):
    def setUp(self):
        self.oracle_page = {
            "schema_version": 1,
            "question_id": "doc-a::q1",
            "doc_id": "doc-a",
            "condition": "oracle_page",
            "evidence_pages": [14],
            "model_input": {
                "instructions": "Use only supplied evidence.",
                "question": "What does the example say?",
                "evidence": [{"page": 14, "text": ""}],
                "response_schema": {"type": "object"},
            },
            "answer": "MUST NOT LEAK",
        }
        self.manifest = {
            "question_id": "doc-a::q1",
            "crops": [
                {
                    "evidence_local_id": "e1",
                    "page": 14,
                    "bbox": [1, 2, 3, 4],
                    "element_type": "table",
                    "output_png": "e1.png",
                    "output_png_sha256": "a" * 64,
                }
            ],
        }
        self.review = {"question_id": "doc-a::q1", "status": "confirmed"}

    def test_builds_image_input_without_answer_or_fact_leakage(self):
        record = build_oracle_region_record(
            self.oracle_page, self.manifest, self.review
        )
        serialized_model_input = json.dumps(record["model_input"])

        self.assertEqual(record["condition"], "oracle_region")
        self.assertEqual(record["evidence_pages"], [14])
        self.assertEqual(record["model_input"]["evidence"][0]["image_path"], "e1.png")
        self.assertNotIn("MUST NOT LEAK", serialized_model_input)
        self.assertNotIn("answer", serialized_model_input)
        self.assertNotIn("facts", serialized_model_input)

    def test_requires_confirmed_review(self):
        self.review["status"] = "pending"
        with self.assertRaisesRegex(ValueError, "manually confirmed"):
            build_oracle_region_record(self.oracle_page, self.manifest, self.review)

    def test_rejects_full_page_text_in_place_of_intersection_text(self):
        self.oracle_page["model_input"]["evidence"][0]["text"] = "whole page"
        with self.assertRaisesRegex(ValueError, "bbox-intersection"):
            build_oracle_region_record(self.oracle_page, self.manifest, self.review)

    def test_accepts_explicit_crop_intersection_text_for_nonempty_page(self):
        self.oracle_page["model_input"]["evidence"][0]["text"] = "whole page"
        self.manifest["condition"] = "oracle_region_context"
        crop = self.manifest["crops"][0]
        crop["text_scope"] = "crop_intersection"
        crop["intersecting_text"] = "Males\nPersonal care 10.8"

        record = build_oracle_region_record(
            self.oracle_page, self.manifest, self.review
        )

        self.assertEqual(
            record["model_input"]["evidence"][0]["text"],
            "Males\nPersonal care 10.8",
        )
        self.assertEqual(record["condition"], "oracle_region_context")
        self.assertNotIn(
            "whole page", json.dumps(record["model_input"]["evidence"])
        )

    def test_accepts_verified_empty_intersection_for_image_only_crop(self):
        self.oracle_page["model_input"]["evidence"][0]["text"] = "page caption"
        crop = self.manifest["crops"][0]
        crop["text_scope"] = "crop_intersection"
        crop["intersecting_text"] = ""

        record = build_oracle_region_record(
            self.oracle_page, self.manifest, self.review
        )

        self.assertEqual(record["model_input"]["evidence"][0]["text"], "")

    def test_accepts_explicit_image_only_scope_without_claiming_text_is_missing(self):
        self.oracle_page["model_input"]["evidence"][0]["text"] = "whole page"
        crop = self.manifest["crops"][0]
        crop["text_scope"] = "image_only"

        record = build_oracle_region_record(
            self.oracle_page, self.manifest, self.review
        )

        evidence = record["model_input"]["evidence"][0]
        self.assertEqual(evidence["text"], "")
        self.assertEqual(evidence["text_scope"], "image_only")


if __name__ == "__main__":
    unittest.main()
