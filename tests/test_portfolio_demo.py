import tempfile
import unittest
from pathlib import Path

from egdi.portfolio_demo import load_demo_cases, render_case, render_demo


class PortfolioDemoTests(unittest.TestCase):
    def test_renders_answer_with_facts_citations_and_evaluation(self):
        prediction = {
            "case_id": "validation_x",
            "question": "What is the difference?",
            "status": "success",
            "selected_facts": [
                {"label": "A", "value": "100", "unit": "pins", "cited_pages": [7]},
                {"label": "B", "value": "4", "unit": "pins", "cited_pages": [7]},
            ],
            "deterministic_comparison": {"magnitude": "96", "unit": "pins"},
        }
        rendered = render_case(prediction, {"answer_match": True})
        self.assertIn("Decision: ANSWER", rendered)
        self.assertIn("Answer: 96 pins", rendered)
        self.assertIn("Citations: 7", rendered)
        self.assertIn("Post-hoc benchmark: CORRECT", rendered)

    def test_renders_abstention_as_reliability_success(self):
        prediction = {
            "case_id": "validation_x",
            "question": "Question?",
            "status": "unsupported",
        }
        rendered = render_case(prediction, {"answer_match": False})
        self.assertIn("Decision: ABSTAIN", rendered)
        self.assertIn("did not guess", rendered)
        self.assertIn("reliability success", rendered)

    def test_rejects_prediction_without_matching_score(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "finalized_citation_repaired.json").write_text(
                '{"cases":[{"case_id":"x"}]}', encoding="utf-8"
            )
            (root / "score.json").write_text(
                '{"cases":[],"summary":{}}', encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "missing frozen score"):
                load_demo_cases(root)

    def test_summary_uses_frozen_counts(self):
        rendered = render_demo(
            [],
            {
                "case_count": 6,
                "answer_exact_match_count": 4,
                "complete_evidence_match_count": 5,
            },
        )
        self.assertIn("Answer exact match: 4/6", rendered)
        self.assertIn("Complete evidence match: 5/6", rendered)


if __name__ == "__main__":
    unittest.main()
