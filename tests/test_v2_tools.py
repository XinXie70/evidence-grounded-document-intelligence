import unittest

from egdi.v2.tools import MAX_PAGE_CHARS, TOOL_SCHEMAS, ToolBox


class FakeDocument:
    page_count = 3
    page_text = {
        1: "Revenue in 2022 was $1,200 million.",
        2: "Revenue in 2023 was  $1,500\nmillion.",
        3: "x" * (MAX_PAGE_CHARS + 50),
    }

    def search(self, query, k):
        return [{"page": p, "score": 1.0, "snippet": t[:20]} for p, t in list(self.page_text.items())[:k]]


def box():
    return ToolBox(FakeDocument())


class SearchReadTests(unittest.TestCase):
    def test_search_validation(self):
        t = box()
        self.assertEqual(len(t.execute("search_document", {"query": "revenue", "k": 2})["results"]), 2)
        for bad in ({"query": ""}, {"query": "a", "k": 6}, {"query": "a", "k": 0}, {"query": "a", "k": True}, {}):
            self.assertIn("error", t.execute("search_document", bad), bad)

    def test_read_pages_out_of_range_and_limits(self):
        t = box()
        out = t.execute("read_pages", {"pages": [1, 9]})["pages"]
        self.assertEqual(out[0]["truncated"], False)
        self.assertEqual(out[1], {"page": 9, "error": "page_out_of_range", "page_count": 3})
        self.assertEqual(t.pages_read, [1])
        self.assertEqual(t.execute("read_pages", {"pages": [1, 2, 3, 1]})["error"], "too_many_pages")
        self.assertEqual(t.execute("read_pages", {"pages": [0]})["pages"][0]["error"], "page_out_of_range")
        self.assertEqual(t.execute("read_pages", {"pages": []})["error"], "bad_pages")

    def test_truncation_is_recorded_and_enforced(self):
        t = box()
        page = t.execute("read_pages", {"pages": [3]})["pages"][0]
        self.assertTrue(page["truncated"])
        self.assertEqual(len(page["text"]), MAX_PAGE_CHARS)

    def test_unknown_tool_and_bad_arguments(self):
        t = box()
        self.assertEqual(t.execute("rm", {})["error"], "unknown_tool")
        self.assertEqual(t.execute("read_pages", {"page": 1})["error"], "bad_arguments")
        self.assertEqual(t.execute("read_pages", [1])["error"], "bad_arguments")


class CalculateTests(unittest.TestCase):
    def setUp(self):
        self.t = box()
        self.t.execute("read_pages", {"pages": [1, 2]})

    def op(self, name, *values_quotes):
        return self.t.execute(
            "calculate",
            {"op": name, "operands": [{"value": v, "page": p, "quote": q} for v, p, q in values_quotes]},
        )

    def test_percent_change_with_whitespace_normalised_quote(self):
        out = self.op("percent_change", (1200, 1, "$1,200 million"), (1500, 2, "$1,500 million"))
        self.assertEqual(out["result"], 25.0)
        self.assertEqual(out["expression"], "(1500 - 1200) / 1200 * 100")

    def test_basic_operations(self):
        a, b = (1200, 1, "$1,200"), (1500, 2, "$1,500")
        self.assertEqual(self.op("add", a, b)["result"], 2700)
        self.assertEqual(self.op("sum", a)["result"], 1200)
        self.assertEqual(self.op("subtract", b, a)["result"], 300)
        self.assertEqual(self.op("multiply", a, b)["result"], 1800000)
        self.assertEqual(self.op("divide", b, a)["result"], 1.25)
        self.assertEqual(self.op("ratio", a, b)["result"], 0.8)
        self.assertEqual(self.op("mean", a, b)["result"], 1350)

    def test_quote_must_be_in_read_page(self):
        out = self.op("add", (1200, 1, "$9,999"), (1500, 2, "$1,500"))
        self.assertEqual(out["error"], "quote_not_found")
        self.assertEqual(self.op("add", (1, 1, ""), (1, 1, "Revenue"))["error"], "quote_not_found")

    def test_quote_from_unread_page_is_rejected(self):
        self.assertEqual(self.op("sum", (5, 3, "x"))["error"], "page_not_read")

    def test_truncated_text_cannot_be_quoted(self):
        t = box()
        t.execute("read_pages", {"pages": [3]})
        out = t.execute("calculate", {"op": "sum", "operands": [{"value": 1, "page": 3, "quote": "x" * (MAX_PAGE_CHARS + 1)}]})
        self.assertEqual(out["error"], "quote_not_found")

    def test_input_errors(self):
        a = (1200, 1, "$1,200")
        self.assertEqual(self.op("power", a, a)["error"], "bad_op")
        self.assertEqual(self.op("subtract", a)["error"], "bad_operand_count")
        self.assertEqual(self.op("divide", a, (0, 1, "Revenue"))["error"], "division_by_zero")
        self.assertEqual(self.op("percent_change", (0, 1, "Revenue"), a)["error"], "division_by_zero")
        self.assertEqual(self.op("add", ("1", 1, "Revenue"), a)["error"], "bad_operand")
        self.assertEqual(self.t.execute("calculate", {"op": "add", "operands": [{"value": 1}]})["error"], "bad_operand_count")
        self.assertEqual(self.op("add", (float("nan"), 1, "Revenue"), a)["error"], "bad_operand")


class FinishTests(unittest.TestCase):
    def test_citations_must_have_been_read(self):
        t = box()
        t.execute("read_pages", {"pages": [1]})
        bad = t.execute("finish", {"status": "answered", "answer": "1200", "cited_pages": [1, 2]})
        self.assertEqual(bad["error"], "cited_page_not_read")
        self.assertIsNone(t.final)
        ok = t.execute("finish", {"status": "answered", "answer": " 1200 ", "cited_pages": [1, 1]})
        self.assertEqual(ok, {"ok": True})
        self.assertEqual(t.final, {"status": "answered", "answer": "1200", "cited_pages": [1]})

    def test_answered_needs_answer_and_citation(self):
        t = box()
        self.assertEqual(t.execute("finish", {"status": "answered", "answer": "", "cited_pages": [1]})["error"], "bad_answer")
        self.assertEqual(t.execute("finish", {"status": "answered", "answer": "x", "cited_pages": []})["error"], "no_citation")
        self.assertEqual(t.execute("finish", {"status": "done", "answer": "x", "cited_pages": []})["error"], "bad_status")

    def test_insufficient_evidence_needs_no_pages(self):
        t = box()
        out = t.execute("finish", {"status": "insufficient_evidence", "answer": "", "cited_pages": []})
        self.assertEqual(out, {"ok": True})
        self.assertEqual(t.final["status"], "insufficient_evidence")


class SchemaTests(unittest.TestCase):
    def test_schemas_cover_exactly_the_tools(self):
        self.assertEqual([s["name"] for s in TOOL_SCHEMAS], ["search_document", "read_pages", "calculate", "finish"])


if __name__ == "__main__":
    unittest.main()
