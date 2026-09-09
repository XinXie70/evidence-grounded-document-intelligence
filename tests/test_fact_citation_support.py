import unittest

from egdi.fact_citation_support import audit_fact_citations, numeric_values_in_text


class FactCitationSupportTests(unittest.TestCase):
    def setUp(self):
        self.input = {
            "question_id": "d::q", "doc_id": "d", "evidence_pages": [1, 2],
            "model_input": {"evidence": [
                {"page": 1, "text": "A broad estimate was nearly 150,000."},
                {"page": 2, "text": "Exact values: 157,472 and 144,042."},
            ]},
        }
        self.result = {
            "question_id": "d::q", "doc_id": "d", "evidence_pages": [1, 2],
            "output": {"status": "extracted", "facts": [
                {"label": "A", "value": "157,472", "cited_pages": [1]},
                {"label": "B", "value": "144042", "cited_pages": [2]},
            ]},
        }

    def test_normalizes_plain_and_grouped_numbers(self):
        values = numeric_values_in_text("A 157,472; B 144042; cost (39.0); malformed 15,74.")
        self.assertIn("157472", values)
        self.assertIn("144042", values)
        self.assertIn("-39", values)
        self.assertNotIn("1574", values)

    def test_flags_unsupported_citation_and_finds_supplied_support(self):
        audit = audit_fact_citations(self.input, self.result)
        self.assertFalse(audit["all_facts_supported_by_citations"])
        self.assertEqual(audit["policy_action"], "reject_unverified_citations")
        self.assertEqual(audit["facts"][0]["unsupported_cited_pages"], [1])
        self.assertEqual(audit["facts"][0]["value_occurs_on_supplied_pages"], [2])
        self.assertTrue(audit["facts"][1]["value_occurs_on_a_cited_page"])

    def test_accepts_when_each_value_occurs_on_its_citation(self):
        self.result["output"]["facts"][0]["cited_pages"] = [2]
        audit = audit_fact_citations(self.input, self.result)
        self.assertTrue(audit["all_facts_supported_by_citations"])
        self.assertEqual(audit["policy_action"], "accept")

    def test_preserves_insufficient_evidence_as_abstention(self):
        self.result["output"] = {"status": "insufficient_evidence", "facts": []}
        audit = audit_fact_citations(self.input, self.result)
        self.assertEqual(audit["policy_action"], "abstain_no_extracted_facts")
        self.assertFalse(audit["eligible_for_answer_acceptance"])


if __name__ == "__main__":
    unittest.main()
