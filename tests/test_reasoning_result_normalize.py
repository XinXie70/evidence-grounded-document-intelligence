import unittest

from egdi.reasoning_result_normalize import normalize_result


class ReasoningResultNormalizeTests(unittest.TestCase):
    def test_repairs_abstention_citations_without_changing_decision(self):
        source = {
            "condition": "real_retrieval",
            "evidence_pages": [2, 3],
            "output": {"answer": None, "cited_pages": [2], "status": "insufficient_evidence"},
        }
        result = normalize_result(source)
        self.assertEqual(result["output"], {"answer": None, "cited_pages": [], "status": "insufficient_evidence"})
        self.assertTrue(result["validation"]["valid"])
        self.assertTrue(result["output_normalization"]["applied"])

    def test_does_not_hide_an_invalid_answerable_result(self):
        source = {
            "condition": "real_retrieval",
            "evidence_pages": [2],
            "output": {"answer": "18", "cited_pages": [99], "status": "answerable"},
        }
        result = normalize_result(source)
        self.assertFalse(result["validation"]["valid"])
        self.assertFalse(result["output_normalization"]["applied"])

    def test_preserves_prior_normalization_audit_metadata(self):
        source = {
            "condition": "real_retrieval",
            "evidence_pages": [2],
            "output": {"answer": None, "cited_pages": [], "status": "insufficient_evidence"},
            "output_normalization": {
                "applied": True,
                "transformations": ["cleared_citations_from_insufficient_evidence"],
            },
        }
        result = normalize_result(source)
        self.assertTrue(result["output_normalization"]["applied"])
        self.assertEqual(
            result["output_normalization"]["transformations"],
            ["cleared_citations_from_insufficient_evidence"],
        )


if __name__ == "__main__":
    unittest.main()
