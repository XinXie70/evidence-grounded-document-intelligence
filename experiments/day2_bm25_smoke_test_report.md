# Day 2 Page-BM25 Smoke Test Report

## 1. Purpose and scope

This smoke test verifies that the smallest evidence-retrieval baseline works end to end before
running the complete `development_tune` evaluation:

```text
PDF physical pages
  -> pypdf text extraction
  -> page-bounded Page Records
  -> deterministic BM25 tokenization and ranking
  -> Top-K physical pages
  -> gold evidence-page scoring
```

This is not the formal BM25 baseline result. Only two deliberately inspected
`development_tune` documents were used. No calibration or locked-test document was accessed for
model selection or performance analysis.

The smoke test does not train a model and does not add OCR, table reconstruction, semantic
retrieval, a reasoning model, agents, or a user interface.

## 2. Frozen v0 baseline used in the smoke test

- Retrieval unit: one physical PDF page.
- Stored input: the complete normalized `text` field of each Page Record.
- Normalization: collapse Unicode whitespace only.
- Tokenization: Unicode letters and digits; case-folded; punctuation and underscores are token
  boundaries; stopwords, numbers, and repeated terms are retained; no stemming or synonym
  expansion.
- BM25 parameters: `k1 = 1.2`, `b = 0.75`.
- Evaluated cutoffs: `K = 1, 3, 5, 10`.
- Deterministic tie break: document ID, then 1-based physical PDF page.
- Evidence metrics include only answerable questions with at least one valid gold evidence page,
  following the frozen protocol.

## 3. Code-level verification

The retrieval/evaluation path has unit tests for:

- whitespace normalization and tokenization;
- Page Record construction and extraction-status boundaries;
- JSONL round-trip identity and order;
- deterministic BM25 ranking, rare terms, term frequency, empty pages, and ties;
- evidence-page metrics, multi-page partial recall, duplicates, and aggregation;
- the connection from a BM25 ranking to per-question and aggregate metrics;
- exclusion of unanswerable questions from answerable evidence-page metrics;
- locked-test access protection.

At the end of the smoke implementation, all 37 discovered tests passed.

## 4. Smoke document A - single eligible question

- Document ID: `urnuuid0812e9ac-6f30-4624-9c78-6f4176467918`
- Physical pages: 53
- Page Records: 53, all `ok`, sequential pages 1-53
- Benchmark questions: 2
- Eligible answerable questions: 1
- Protocol exclusions: 1 (`q1`, `is_answerable = false`)

### Eligible q2

Question:

> What specific age threshold does the document define for distinguishing between a child and an
> adult research participant under POPIA?

- Gold answer: `18 years old`
- Gold page: 12
- BM25 Top-3: pages 12, 18, 47
- Gold-page rank: 1

At every evaluated K, any-evidence recall, complete-evidence recall, evidence recall, reciprocal
rank, and nDCG are 1. Precision decreases from 1 at K=1 to 1/3, 1/5, and 1/10 as additional
non-gold pages are returned.

The excluded q1 was retained as a diagnostic example only. It has related pages 17, 20, and 23,
but the benchmark label is unanswerable and has no supported final answer, so it does not enter the
answerable evidence-retrieval denominator.

### Diagnostic ranking observation

For q2, page 18 nearly tied the correct page because the rare query term `adult` and repeated
`child` occurrences produced a high lexical score. The correct page remained first because the
combined contributions of `age`, `child`, `under`, and other matched terms were higher.

## 5. Smoke document B - six eligible questions

- Document ID: `urnuuid0a20b83c-2af0-4503-9220-c63470cdd214`
- Physical pages: 88
- Page Records: 88, sequential pages 1-88, unique `(doc_id, page)` identities
- Extraction statuses: 69 `ok`, 7 `low_text`, 12 `text_layer_missing`
- Benchmark questions: 6
- Eligible answerable questions: 6
- Protocol exclusions: 0

### Aggregate retrieval metrics

| K | Any evidence recall | Complete evidence recall | Mean evidence recall | Precision | MRR | nDCG |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.167 | 0.000 | 0.083 | 0.167 | 0.167 | 0.167 |
| 3 | 0.667 | 0.167 | 0.375 | 0.278 | 0.389 | 0.318 |
| 5 | 0.833 | 0.333 | 0.583 | 0.233 | 0.422 | 0.402 |
| 10 | 1.000 | 0.500 | 0.792 | 0.150 | 0.450 | 0.483 |

At K=10, every question retrieves at least one gold page, but only three of six retrieve every
required gold page. This demonstrates why any-evidence recall and complete-evidence recall must be
reported separately.

### Per-question K=10 result

| Question | Gold pages | Gold pages retrieved in Top-10 | Recall | Complete |
|---|---|---|---:|---:|
| q1 | 1, 76 | 76 | 0.50 | 0 |
| q2 | 68, 69, 71, 74 | 68, 69, 71 | 0.75 | 0 |
| q3 | 71 | 71 (rank 6) | 1.00 | 1 |
| q4 | 67, 68 | 67, 68 (ranks 2 and 3) | 1.00 | 1 |
| q5 | 15, 74 | 74 | 0.50 | 0 |
| q6 | 32 | 32 (rank 5) | 1.00 | 1 |

## 6. Manually verified cases and failure attribution

### q1 - extraction/representation failure

Question:

> How many years elapsed between the year the Convention on the Rights of the Child was opened
> for signature and the start year of Safe and Supported?

The visible cover contains the Safe and Supported start year `2021`, and page 76 contains the
Convention year `1989`; the answer is `2021 - 1989 = 32 years`.

The page-1 Page Record contains only `FIRST ACTION PLAN ... 2023-2026`. It contains neither
`Safe & Supported` nor `2021`. PDF content inspection found the missing visible title represented
as vector drawing rather than ordinary extractable text. BM25 therefore gave page 1 a score of
zero and ranked it 73rd; page 76 ranked third.

Attribution: the dominant failure occurs before BM25, in text extraction/page representation.

### q2 - lexical ambiguity and global set retrieval

Question:

> How many numbered 'Box' callout sections (with distinct titles) appear across the entire
> document?

The answer `4` requires retrieving Box 1, 2, 3, and 4 on pages 68, 69, 71, and 74, then counting
the distinct numbered callouts. Their BM25 ranks are 2, 7, 4, and 15.

Incorrect page 4 ranks first because `GPO Box 9820 Canberra` matches `box`, and `Enquiries
regarding this document` matches the rare query term `document`. BM25 does not distinguish a
numbered callout box from a postal box. Page 74 has an intact text layer containing `Box 4:
Enablers of change`, so its omission at K=10 is a ranking failure, not an extraction failure.

Attribution: lexical ambiguity plus a task requiring global set retrieval and counting.

### q3 - semantic paraphrase and query-framing weight

Question:

> Which focus area is described as depending on progress across all the others?

Gold page 71 contains `The achievement of Focus Area 2 will require efforts across the other 3
focus areas.` Its text layer is intact, but exact lexical matching misses `depending` versus
`require efforts`, `progress` versus the page wording, and `others` versus `other`.

Incorrect page 24 ranks first because it contains the rare query-framing word `described` twice.
Gold page 71 ranks sixth.

Attribution: a genuine text-present BM25 lexical-ranking failure.

### q4 - complete retrieval success with one noise page

Question:

> Which specific factor appears in both the list of risk factors for child abuse and neglect
> mentioned in the section on social determinants linked to risk, and the list of impacts of
> trauma mentioned in the box explaining intergenerational trauma?

Page 67 lists `family violence` as a risk factor. Page 68 lists `physical or emotional violence`
as an impact of trauma. The common factor and gold answer is `violence`.

BM25 ranks incorrect but topically related page 69 first, then gold pages 67 and 68 second and
third. Page 69 matches many topic terms and receives extra weight from the rare word `mentioned`,
which occurs twice in the query and once on the page. At K=3, evidence recall and complete-evidence
recall are 1, while precision is 2/3.

This is a retrieval success, not an answer-generation result. A later grounded reasoner must still
compare the two lists to produce `violence`.

## 7. Smoke-test conclusions

The smoke test verifies that:

1. Physical page identity is preserved from PDF through JSONL and retrieval output.
2. The deterministic BM25 implementation can rank page records and return reproducible Top-K
   results.
3. The evidence scorer correctly separates any evidence from complete multi-page evidence.
4. Unanswerable questions are reported and excluded from the answerable evidence denominator.
5. Both success and failure outputs were manually checked against page text and benchmark labels.
6. Failures can be attributed to distinct pipeline stages instead of being described only as a
   single end-to-end error.

The observed failure categories are:

- absent or incomplete machine-readable text;
- flattened table structure;
- lexical ambiguity;
- semantic paraphrase and morphological mismatch;
- global enumeration/multi-page set retrieval;
- irrelevant query-framing terms receiving high lexical weight;
- additional topically related noise pages even when complete evidence is retrieved.

These are smoke observations, not prevalence estimates. They do not yet justify an architectural
change.

## 8. Decision and next step

Keep the v0 page-level text-only BM25 baseline unchanged. Do not add OCR, stemming, semantic
retrieval, table reconstruction, or a reasoning model during smoke validation.

Next, produce a read-only dry-run inventory for the full `development_tune` split. After the user
verifies the document, page, question, answerability, and extraction-status counts, implement and
test a deterministic batch Page Record builder. Only then run the formal tune baseline and measure
the prevalence of each failure slice.

Detailed inspected examples remain in `experiments/day2_representation_observations.md`.
