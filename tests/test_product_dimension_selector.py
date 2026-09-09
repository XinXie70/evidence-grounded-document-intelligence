import unittest

from egdi.product_dimension_selector import (
    parse_less_than_descriptors,
    select_product_depth_facts,
)


QUESTION = (
    "The depth dimension of the digital time clock module with four push buttons "
    "visible on its front panel is how many millimeters less than the depth dimension "
    "of the 5A unboxed power supply unit?"
)


class ProductDimensionSelectorTests(unittest.TestCase):
    def setUp(self):
        self.pages = {
            10: (
                "UBPSU5.0 POWER SUPPL Y The UBPSU5.0 power supply is a 5A unboxed PSU. "
                "UBPSU5.0 Dimensions terminal details"
            ),
            11: "PSU Dimensions : 235mm (L) x 100mm (W) x 40mm (D) Technical Specifications",
            12: (
                "Art.701T BST/GMT Time Clock The Art.701T is a digital time clock. "
                "Programming uses the four push buttons: MODE, UP, DOWN and SELECT."
            ),
            14: (
                "Art.701T Dimensions Module Dimensions : "
                "110mm (L) x 70mm (W) x 30mm (D)"
            ),
        }

    def test_parses_ordered_less_than_descriptors(self):
        left, right = parse_less_than_descriptors(QUESTION)
        self.assertIn("time clock", left)
        self.assertIn("5A unboxed", right)

    def test_links_descriptions_to_ids_and_explicit_depth_values(self):
        facts = select_product_depth_facts(QUESTION, self.pages)
        self.assertEqual(
            [(fact.product_id, fact.identity_page, fact.value_page, fact.value) for fact in facts],
            [("Art.701T", 12, 14, "30"), ("UBPSU5.0", 10, 11, "40")],
        )

    def test_rejects_missing_continuation_specification(self):
        pages = dict(self.pages)
        del pages[11]
        with self.assertRaisesRegex(ValueError, "no explicit L/W/D"):
            select_product_depth_facts(QUESTION, pages)

    def test_rejects_unsupported_question_instead_of_guessing(self):
        with self.assertRaisesRegex(ValueError, "less than"):
            select_product_depth_facts("What is the depth?", self.pages)


if __name__ == "__main__":
    unittest.main()
