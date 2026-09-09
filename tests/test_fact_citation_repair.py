import unittest

from egdi.fact_citation_repair import repair_citations


class FactCitationRepairTests(unittest.TestCase):
    def _finalized(self):
        return {
            "cases": [{
                "case_id": "x", "question_id": "d::q", "status": "success",
                "selected_facts": [
                    {"value": "10", "cited_pages": [1], "selection_basis": "model"},
                    {"value": "4", "cited_pages": [1], "selection_basis": "model"},
                ],
            }],
            "leakage_controls": {"uses_gold_answer": False, "uses_gold_evidence_pages": False},
        }

    def _audit(self):
        return {
            "uses_benchmark_labels": False,
            "cases": [{
                "case_id": "x", "question_id": "d::q", "facts": [
                    {"value_occurs_on_a_cited_page": False,
                     "value_occurs_on_supplied_pages": [9, 4]},
                    {"value_occurs_on_a_cited_page": False,
                     "value_occurs_on_supplied_pages": [12, 4]},
                ],
            }],
        }

    def test_repairs_to_earliest_common_support_page(self):
        output = repair_citations(self._finalized(), self._audit())
        case = output["cases"][0]
        self.assertEqual(case["selected_facts"][0]["cited_pages"], [4])
        self.assertEqual(case["selected_facts"][1]["cited_pages"], [4])
        self.assertEqual(case["citation_repair"]["status"], "repaired")
        self.assertTrue(case["citation_repair"]["used_shared_support_page"])

    def test_preserves_already_supported_citations(self):
        audit = self._audit()
        audit["cases"][0]["facts"][0]["value_occurs_on_a_cited_page"] = True
        output = repair_citations(self._finalized(), audit)
        facts = output["cases"][0]["selected_facts"]
        self.assertEqual(facts[0]["cited_pages"], [1])
        self.assertEqual(facts[1]["cited_pages"], [4])

    def test_rejects_when_no_supplied_page_contains_value(self):
        audit = self._audit()
        audit["cases"][0]["facts"][0]["value_occurs_on_supplied_pages"] = []
        output = repair_citations(self._finalized(), audit)
        self.assertEqual(output["cases"][0]["status"], "unsupported")
        self.assertEqual(output["summary"]["rejected_case_count"], 1)

    def test_preserves_upstream_abstention(self):
        finalized = self._finalized()
        finalized["cases"][0]["status"] = "unsupported"
        finalized["cases"][0]["selected_facts"] = []
        audit = self._audit()
        audit["cases"][0]["facts"] = []
        output = repair_citations(finalized, audit)
        self.assertEqual(output["cases"][0]["status"], "unsupported")
        self.assertEqual(output["summary"]["abstained_case_count"], 1)


if __name__ == "__main__":
    unittest.main()
