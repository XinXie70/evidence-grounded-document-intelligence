import unittest

from egdi.splits import build_split_manifest


def record(question_id, split, doc_id, answerable=True, pages=(1,), kind="text"):
    return {
        "id": question_id,
        "split": split,
        "answer": {"is_answerable": answerable},
        "pdf": {"doc_id_str": doc_id},
        "evidences": [{"page": page, "element_type": kind} for page in pages],
        "extract_class": 1,
    }


class SplitTests(unittest.TestCase):
    def test_document_isolation_and_determinism(self):
        records = [record(f"d{i}", "dev", f"doc{i}") for i in range(10)]
        records += [record("overlap-dev", "dev", "locked")]
        records += [record("test", "test", "locked")]
        first = build_split_manifest(records)
        second = build_split_manifest(records)
        self.assertEqual(first, second)
        tune = set(first["development_tune"]["document_ids"])
        calibration = set(first["development_calibration"]["document_ids"])
        locked = set(first["locked_test"]["document_ids"])
        self.assertFalse(tune & calibration)
        self.assertFalse((tune | calibration) & locked)
        self.assertEqual(first["excluded_official_dev_question_ids"], ["overlap-dev"])
        self.assertEqual(len(calibration), 3)


if __name__ == "__main__":
    unittest.main()

