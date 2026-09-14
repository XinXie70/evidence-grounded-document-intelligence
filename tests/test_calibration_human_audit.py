import unittest

from egdi.calibration_human_audit import select_cases


class CalibrationHumanAuditTests(unittest.TestCase):
    def test_selects_fifty_with_rare_routes_and_failures(self):
        cases = []
        audit = []
        index = 0

        def add(route, gold, status, task, support, cited):
            nonlocal index
            index += 1
            pilot = f"p{index:03d}"
            cases.append({
                "pilot_id": pilot, "question_id": f"q{index}", "route": route,
                "gold_is_answerable": gold, "gold_answer": "a", "question": "q",
                "prediction": {"status": status, "answer": "a" if status == "answerable" else None,
                               "cited_pages": list(range(1, cited + 1))},
            })
            audit.append({"pilot_id": pilot, "question_id": f"q{index}",
                          "task_correct": task, "evidence_supported": support,
                          "grounded_correct": task and support})

        for _ in range(8): add("r0_text", False, "insufficient_evidence", True, True, 0)
        for _ in range(3): add("r3_document_global", True, "insufficient_evidence", False, True, 0)
        add("r2_scanned_document", True, "answerable", True, True, 1)
        for route, task, support, cited in (
            [("r0_text", True, False, 1)] * 5
            + [("r0_text", False, False, 2)] * 5
            + [("r1_local_visual", False, True, 1)] * 2
            + [("r0_text", False, True, 2)]
            + [("r1_local_visual", True, False, 1)]
            + [("r1_local_visual", False, False, 1)]
        ):
            add(route, True, "answerable", task, support, cited)
        for _ in range(8): add("r0_text", True, "insufficient_evidence", False, True, 0)
        for _ in range(4): add("r1_local_visual", True, "insufficient_evidence", False, True, 0)
        for route, cited, count in (
            ("r0_text", 1, 4), ("r0_text", 2, 3),
            ("r1_local_visual", 1, 2), ("r1_local_visual", 2, 2),
        ):
            for _ in range(count): add(route, True, "answerable", True, True, cited)
        selected = select_cases({"cases": cases}, {"cases": audit})
        self.assertEqual(len(selected), 50)
        self.assertTrue(all(case["automatic"].get("grounded_correct") is not None for case in selected))
        self.assertEqual(sum(case["route"] == "r3_document_global" for case in selected), 3)


if __name__ == "__main__":
    unittest.main()
