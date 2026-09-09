"""Question-guided extraction of counts from numbered, possibly multi-page lists."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from .io import sha256_file, write_json


_ARTICLE_TOPICS = re.compile(
    r"article about (.+?) that .+? and the article about (.+?) that ",
    re.IGNORECASE,
)
_NUMBERED_ITEM = re.compile(r"(?<![\w.])(\d{1,2})\.\s+(?=[A-Z])")
_STEP_ITEM = re.compile(r"\bStep\s+(\d{1,2})\s*:", re.IGNORECASE)
_REFERENCES_HEADING = re.compile(r"\bReferences\b", re.IGNORECASE)
_TOKEN = re.compile(r"[a-z0-9]+")
_TOPIC_STOPWORDS = {
    "a",
    "about",
    "and",
    "article",
    "competencies",
    "describes",
    "lists",
    "mental",
    "numbered",
    "of",
    "practices",
    "that",
    "the",
    "to",
}


@dataclass(frozen=True)
class ListCountFact:
    topic: str
    pages: tuple[int, ...]
    marker_style: str
    observed_numbers: tuple[int, ...]
    value: str
    unit: str = "steps"
    selection_basis: str = "question_topic_then_contiguous_numbered_sequence"

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["pages"] = list(self.pages)
        result["observed_numbers"] = list(self.observed_numbers)
        return result


def extract_article_topics(question: str) -> tuple[str, str]:
    """Extract the two article descriptors from the benchmark question wording."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be a non-empty string")
    match = _ARTICLE_TOPICS.search(question)
    if match is None:
        raise ValueError("question must describe two compared articles")
    return tuple(part.strip(" ,") for part in match.groups())  # type: ignore[return-value]


def _stem(token: str) -> str:
    if token.endswith("ing") and len(token) > 5:
        return token[:-3]
    if token.endswith("s") and len(token) > 4:
        return token[:-1]
    return token


def _topic_tokens(text: str) -> set[str]:
    return {
        _stem(token)
        for token in _TOKEN.findall(text.casefold())
        if token not in _TOPIC_STOPWORDS
    }


def _markers(text: str, style: str) -> list[int]:
    # Bibliography numbering is not an article's instructional list.  PDF text is
    # flattened, so discard the suffix after an explicit References heading.
    reference_heading = _REFERENCES_HEADING.search(text)
    if reference_heading is not None:
        text = text[: reference_heading.start()]
    pattern = _STEP_ITEM if style == "step" else _NUMBERED_ITEM
    return [int(value) for value in pattern.findall(text)]


def _consecutive_prefix(numbers: Sequence[int], *, start: int = 1) -> list[int]:
    """Keep the first monotonic 1..N list while ignoring duplicate markers."""
    expected = start
    output: list[int] = []
    for number in numbers:
        if number == expected:
            output.append(number)
            expected += 1
        elif output and number == output[-1]:
            continue
        elif output:
            break
    return output


def _best_seed(topic: str, pages: Mapping[int, str]) -> tuple[int, str, list[int]]:
    wanted = _topic_tokens(topic)
    if not wanted:
        raise ValueError("article topic has no discriminative terms")
    candidates = []
    for page, text in pages.items():
        page_tokens = _topic_tokens(text)
        overlap = len(wanted & page_tokens)
        for style in ("step", "numbered"):
            sequence = _consecutive_prefix(_markers(text, style))
            if sequence:
                candidates.append((overlap, len(sequence), -page, page, style, sequence))
    if not candidates:
        raise ValueError(f"no numbered-list seed found for topic: {topic}")
    best = max(candidates)
    if best[0] == 0:
        raise ValueError(f"numbered lists exist but none matches topic: {topic}")
    return best[3], best[4], best[5]


def _extend_forward(
    seed_page: int,
    style: str,
    sequence: list[int],
    pages: Mapping[int, str],
) -> tuple[list[int], list[int]]:
    used_pages = [seed_page]
    output = list(sequence)
    next_page = seed_page + 1
    while next_page in pages:
        continuation = _consecutive_prefix(
            _markers(pages[next_page], style), start=output[-1] + 1
        )
        if not continuation:
            break
        output.extend(continuation)
        used_pages.append(next_page)
        next_page += 1
    return used_pages, output


def select_list_count_facts(
    question: str, page_text_by_page: Mapping[int, str]
) -> list[ListCountFact]:
    """Select two ordered list counts without using gold pages or gold answers."""
    if not page_text_by_page:
        raise ValueError("candidate page text must not be empty")
    topics = extract_article_topics(question)
    selected = []
    for topic in topics:
        seed_page, style, sequence = _best_seed(topic, page_text_by_page)
        used_pages, complete_sequence = _extend_forward(
            seed_page, style, sequence, page_text_by_page
        )
        selected.append(
            ListCountFact(
                topic=topic,
                pages=tuple(used_pages),
                marker_style=style,
                observed_numbers=tuple(complete_sequence),
                value=str(complete_sequence[-1]),
            )
        )
    return selected


def _load_candidate_pages(path: Path, candidates: Sequence[int]) -> dict[int, str]:
    wanted = set(candidates)
    output: dict[int, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        page = record.get("page")
        if page in wanted:
            output[page] = record.get("text", "")
    missing = wanted - output.keys()
    if missing:
        raise ValueError(f"candidate pages missing from page records: {sorted(missing)}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--page-records", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite immutable selection: {args.output}")
    experiment = json.loads(args.input.read_text(encoding="utf-8"))
    pages = _load_candidate_pages(args.page_records, experiment["candidate_pages"])
    facts = select_list_count_facts(experiment["question"], pages)
    result = {
        "schema_version": 1,
        "experiment_type": "question_guided_list_count_selection",
        "selector_version": "list_count_selector_v1_excludes_reference_sections",
        "question_id": experiment["question_id"],
        "doc_id": experiment["doc_id"],
        "question": experiment["question"],
        "candidate_page_count": len(pages),
        "selected_facts": [fact.to_dict() for fact in facts],
        "uses_gold_answer": False,
        "uses_gold_evidence_pages": False,
        "input_sha256": sha256_file(args.input),
        "page_records_sha256": sha256_file(args.page_records),
        "paid_api_used": False,
    }
    write_json(args.output, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
