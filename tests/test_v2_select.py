import unittest

from egdi.v2.eval.select import build_pool, final_document_ids, is_eligible_answerable

AUDIT = {
    "d1": {1: {"low_text": False, "text_layer_missing": False}, 2: {"low_text": True, "text_layer_missing": False}},
    "d2": {1: {"low_text": False, "text_layer_missing": False}},
}


def rec(qid, doc, answerable=True, evidences=((1, "text"),)):
    return {
        "id": qid,
        "answer": {"is_answerable": answerable},
        "pdf": {"doc_id_str": doc},
        "evidences": [{"page": p, "element_type": t} for p, t in evidences],
    }


class SelectTests(unittest.TestCase):
    def test_rules(self):
        self.assertTrue(is_eligible_answerable(rec("a", "d1", evidences=[(1, "table")]), AUDIT))
        self.assertFalse(is_eligible_answerable(rec("a", "d1", evidences=[]), AUDIT))
        self.assertFalse(is_eligible_answerable(rec("a", "d1", evidences=[(1, "text"), (1, "chart")]), AUDIT))
        self.assertFalse(is_eligible_answerable(rec("a", "d1", evidences=[(2, "text")]), AUDIT))
        self.assertFalse(is_eligible_answerable(rec("a", "d1", evidences=[(9, "text")]), AUDIT))
        self.assertFalse(is_eligible_answerable(rec("a", "d1", answerable=False), AUDIT))

    def test_unanswerable_only_from_pool_documents(self):
        pool = build_pool(
            [
                rec("a", "d1", evidences=[(1, "text")]),
                rec("u1", "d1", answerable=False, evidences=[(1, "chart")]),
                rec("u2", "d2", answerable=False),
            ],
            AUDIT,
        )
        self.assertEqual(pool["unanswerable_question_ids"], ["u1"])
        self.assertEqual(pool["document_ids"], ["d1"])

    def test_final_documents_exclude_archived(self):
        manifest = {"locked_test": {"document_ids": ["x", "y", "z"]}}
        self.assertEqual(final_document_ids(manifest, {"document_ids": ["y"]}), ["x", "z"])


if __name__ == "__main__":
    unittest.main()
