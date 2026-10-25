"""The agent's three tools plus ``finish``, with their JSON schemas.

Every call returns a plain dict and never raises: bad input becomes
``{"error": ..., "message": ...}`` so the model can correct itself. The toolbox also
tracks which pages were actually shown to the model, because both ``calculate`` (quotes)
and ``finish`` (citations) are validated against that set and nothing else. Answer
correctness is deliberately not checked here; the evaluation judges that.
"""

from __future__ import annotations

import math
from typing import Any, Protocol

from egdi.text import normalize_whitespace

MAX_SEARCH_K = 5
MAX_READ_PAGES = 3
MAX_PAGE_CHARS = 6000

OPERATIONS = (
    "add", "subtract", "multiply", "divide", "percent_change", "ratio", "sum", "mean",
)
# op -> (min operands, max operands); None means unbounded.
_ARITY = {
    "add": (2, None), "sum": (1, None), "mean": (1, None), "multiply": (2, None),
    "subtract": (2, 2), "divide": (2, 2), "ratio": (2, 2), "percent_change": (2, 2),
}

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "search_document",
        "description": (
            "Search the current document. Returns the best-matching pages with a short "
            "snippet each. Snippets are hints only; call read_pages before relying on a page."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query."},
                "k": {"type": "integer", "description": f"Number of pages, 1-{MAX_SEARCH_K}. Default {MAX_SEARCH_K}."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_pages",
        "description": f"Read the full text of up to {MAX_READ_PAGES} pages (1-based PDF page numbers).",
        "parameters": {
            "type": "object",
            "properties": {
                "pages": {"type": "array", "items": {"type": "integer"}, "description": "Page numbers."},
            },
            "required": ["pages"],
        },
    },
    {
        "name": "calculate",
        "description": (
            "Compute from numbers found in pages you have read. Each operand needs the page "
            "and an exact quote copied from that page that contains the number. "
            "percent_change takes [old, new]; subtract/divide/ratio take [a, b] meaning a-b, a/b."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "op": {"type": "string", "enum": list(OPERATIONS)},
                "operands": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "value": {"type": "number"},
                            "page": {"type": "integer"},
                            "quote": {"type": "string"},
                        },
                        "required": ["value", "page", "quote"],
                    },
                },
            },
            "required": ["op", "operands"],
        },
    },
    {
        "name": "finish",
        "description": (
            "End the task. Use status 'answered' with the answer and the pages you read that "
            "support it, or 'insufficient_evidence' if the document does not contain the answer."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["answered", "insufficient_evidence"]},
                "answer": {"type": ["string", "null"], "description": "null when status is insufficient_evidence"},
                "cited_pages": {"type": "array", "items": {"type": "integer"}},
            },
            "required": ["status", "answer", "cited_pages"],
        },
    },
]


class SearchableDocument(Protocol):
    page_count: int
    page_text: dict[int, str]

    def search(self, query: str, k: int) -> list[dict[str, Any]]: ...


def _error(code: str, message: str) -> dict[str, Any]:
    return {"error": code, "message": message}


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _fmt(value: float) -> str:
    return f"{value:.10g}"


class ToolBox:
    """Tool executor bound to one document and one task."""

    def __init__(self, document: SearchableDocument, max_page_chars: int = MAX_PAGE_CHARS):
        self.document = document
        self.max_page_chars = max_page_chars
        self.read_text: dict[int, str] = {}  # page -> text exactly as shown to the model
        self.final: dict[str, Any] | None = None

    @property
    def pages_read(self) -> list[int]:
        return sorted(self.read_text)

    def execute(self, name: str, arguments: Any) -> dict[str, Any]:
        handlers = {
            "search_document": self.search_document,
            "read_pages": self.read_pages,
            "calculate": self.calculate,
            "finish": self.finish,
        }
        if name not in handlers:
            return _error("unknown_tool", f"unknown tool {name!r}; use one of {sorted(handlers)}")
        if not isinstance(arguments, dict):
            return _error("bad_arguments", "arguments must be a JSON object")
        try:
            return handlers[name](**arguments)
        except TypeError as exc:  # missing or unexpected argument names
            return _error("bad_arguments", str(exc))

    def search_document(self, query: Any, k: Any = MAX_SEARCH_K) -> dict[str, Any]:
        if not isinstance(query, str) or not query.strip():
            return _error("bad_query", "query must be a non-empty string")
        if not _is_int(k) or not 1 <= k <= MAX_SEARCH_K:
            return _error("bad_k", f"k must be an integer from 1 to {MAX_SEARCH_K}")
        return {"results": self.document.search(query, k)}

    def read_pages(self, pages: Any) -> dict[str, Any]:
        if not isinstance(pages, list) or not pages or not all(_is_int(p) for p in pages):
            return _error("bad_pages", "pages must be a non-empty list of integers")
        if len(pages) > MAX_READ_PAGES:
            return _error("too_many_pages", f"read at most {MAX_READ_PAGES} pages per call")
        results: list[dict[str, Any]] = []
        for page in dict.fromkeys(pages):
            if page not in self.document.page_text:
                results.append(
                    {"page": page, "error": "page_out_of_range", "page_count": self.document.page_count}
                )
                continue
            text = self.document.page_text[page]
            truncated = len(text) > self.max_page_chars
            shown = text[: self.max_page_chars]
            self.read_text[page] = shown
            results.append({"page": page, "text": shown, "truncated": truncated})
        return {"pages": results}

    def calculate(self, op: Any, operands: Any) -> dict[str, Any]:
        if op not in OPERATIONS:
            return _error("bad_op", f"op must be one of {list(OPERATIONS)}")
        if not isinstance(operands, list):
            return _error("bad_operands", "operands must be a list")
        low, high = _ARITY[op]
        if len(operands) < low or (high is not None and len(operands) > high):
            return _error("bad_operand_count", f"{op} needs {low}" + (f"-{high}" if high != low else "") + " operands")
        values: list[float] = []
        for index, operand in enumerate(operands):
            problem = self._check_operand(operand)
            if problem:
                return _error(problem[0], f"operand {index}: {problem[1]}")
            values.append(float(operand["value"]))
        return self._compute(op, values)

    def _check_operand(self, operand: Any) -> tuple[str, str] | None:
        if not isinstance(operand, dict) or not {"value", "page", "quote"} <= operand.keys():
            return "bad_operand", "each operand needs value, page and quote"
        if not _is_number(operand["value"]):
            return "bad_operand", "value must be a finite number"
        if not _is_int(operand["page"]) or not isinstance(operand["quote"], str):
            return "bad_operand", "page must be an integer and quote a string"
        if operand["page"] not in self.read_text:
            return "page_not_read", f"page {operand['page']} has not been read; call read_pages first"
        quote = normalize_whitespace(operand["quote"])
        if not quote or quote not in normalize_whitespace(self.read_text[operand["page"]]):
            return "quote_not_found", f"quote does not appear in the text of page {operand['page']}"
        return None

    @staticmethod
    def _compute(op: str, v: list[float]) -> dict[str, Any]:
        try:
            if op in ("add", "sum"):
                result, expression = sum(v), " + ".join(map(_fmt, v))
            elif op == "mean":
                result, expression = sum(v) / len(v), f"({' + '.join(map(_fmt, v))}) / {len(v)}"
            elif op == "multiply":
                result = math.prod(v)
                expression = " * ".join(map(_fmt, v))
            elif op == "subtract":
                result, expression = v[0] - v[1], f"{_fmt(v[0])} - {_fmt(v[1])}"
            elif op in ("divide", "ratio"):
                result, expression = v[0] / v[1], f"{_fmt(v[0])} / {_fmt(v[1])}"
            else:  # percent_change
                result = (v[1] - v[0]) / v[0] * 100
                expression = f"({_fmt(v[1])} - {_fmt(v[0])}) / {_fmt(v[0])} * 100"
        except ZeroDivisionError:
            return _error("division_by_zero", "the divisor (or the old value) is zero")
        return {"result": float(_fmt(result)), "expression": expression}

    def finish(self, status: Any, answer: Any, cited_pages: Any) -> dict[str, Any]:
        if status not in ("answered", "insufficient_evidence"):
            return _error("bad_status", "status must be 'answered' or 'insufficient_evidence'")
        if status == "answered" and (not isinstance(answer, str) or not answer.strip()):
            return _error("bad_answer", "an answered task needs a non-empty answer string")
        if status == "insufficient_evidence" and answer is not None and not isinstance(answer, str):
            return _error("bad_answer", "answer must be a string or null")
        if not isinstance(cited_pages, list) or not all(_is_int(p) for p in cited_pages):
            return _error("bad_cited_pages", "cited_pages must be a list of integers")
        if status == "answered" and not cited_pages:
            return _error("no_citation", "an answered task must cite at least one page")
        unread = sorted(set(cited_pages) - set(self.read_text))
        if unread:
            return _error("cited_page_not_read", f"pages {unread} were never read; read them or remove them")
        self.final = {
            "status": status,
            "answer": answer.strip() if isinstance(answer, str) else None,
            "cited_pages": sorted(set(cited_pages)),
        }
        return {"ok": True}
