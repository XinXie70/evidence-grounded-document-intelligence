# Day 2 Representation Observations

## Observation 001 - Flattened table structure

- Date: 2026-08-28
- Split: `development_tune`
- Question ID: `urnuuid0f5d7a73-b0b9-49e8-a04e-89f2a02132fe::q1`
- Document ID: `urnuuid0f5d7a73-b0b9-49e8-a04e-89f2a02132fe`
- Physical PDF page: 44
- Gold evidence type: `table`
- Question: 2011 lodging-accommodations expenditure
- Gold answer: `$52,788,333`

### What was preserved

The pinned `pypdf` extraction retained the table title, group/column labels, row label,
currency values, percentages, and the gold answer value. The conservative whitespace
normalizer did not delete or alter those values.

### What was degraded

The two-dimensional table was flattened into a one-dimensional token sequence. The value order
was retained, but the association among the `Staying in Paid Accommodations` group, the `2011`
column, the `Lodging Accommodations` row, and `$52,788,333` was not represented explicitly.
Manual review found that recovering the correct cell from extracted text alone required counting
headers and values and was not immediately clear.

### Current interpretation

- The extracted text appears adequate for a lexical page-retrieval baseline because the query's
  discriminative terms and the table title/row label are present.
- The flattened representation may be inadequate for reliable table-cell reasoning after the page
  is retrieved.
- This is one inspected example, not evidence that table structure is the dominant dataset failure.

### Decision

Keep the v0 page-level BM25 representation simple: pinned text extraction plus whitespace-only
normalization. Do not add table reconstruction, OCR, or a visual path yet. Measure retrieval first,
then inspect a broader failure slice before proposing a representation change.

## Observation 002 - Image-only evidence page

- Date: 2026-08-28
- Split: `development_tune`
- Question ID: `urnuuida3024dbb-48a6-4849-bb2f-910722e335ba::q1`
- Document ID: `urnuuida3024dbb-48a6-4849-bb2f-910722e335ba`
- Physical PDF page: 14
- Gold evidence type: `table`
- Gold answer: `father of #11 and #12`

### Observation

The rendered page visibly contains a rotated bird-registration table, including the annotated
example in the `Bloodline/Relation Information` column. Pinned `pypdf` extraction returned an
empty string, so whitespace normalization also returned an empty string. The problem is absence
of a machine-readable text layer, not whitespace noise; rotation alone does not establish the
cause because rotated native text can still be extractable.

A subsequent full-document smoke extraction produced 51 sequential Page Records for physical
pages 1 through 51. All 51 records had empty text and `extraction_status = text_layer_missing`.
The JSONL round trip preserved every page, including pages 13, 14, and 15, without shifting page
identity. This document is therefore image-only under the pinned text extractor, not an isolated
single-page defect.

### Decision

Retain the page with `extraction_status = text_layer_missing`. Do not silently apply OCR and do
not delete the page. The text-only BM25 baseline should expose this limitation, and later metrics
must report the missing/low-text slice separately before any OCR or visual intervention is proposed.

## Observation 003 - Visible cover text absent from the text layer

- Date: 2026-08-31
- Split: `development_tune`
- Question ID: `urnuuid0a20b83c-2af0-4503-9220-c63470cdd214::q1`
- Document ID: `urnuuid0a20b83c-2af0-4503-9220-c63470cdd214`
- Gold physical PDF pages: 1 and 76
- Gold answer: `32 years`

### Observation

The question requires the `2021` start year visible in the cover title `Safe & Supported ...
2021-2031` and the `1989` Convention year on page 76. The answer is `2021 - 1989 = 32`.
Pinned `pypdf` extraction preserved `1989` on page 76 but extracted only `FIRST ACTION PLAN ...
2023-2026` from page 1. The page-1 Page Record has 48 non-whitespace characters, is classified
as `low_text`, and contains neither `Safe & Supported` nor `2021`.

Inspection of the page content stream found no `SAFE` or `2021` text string and found many vector
path operations. The visible cover title is therefore not represented as ordinary extractable
text; this is not whitespace-normalization loss.

BM25 ranked page 76 third but gave page 1 a score of zero and ranked it 73rd of 88 pages. At
`K=10`, any-evidence recall is 1, evidence recall is 0.5, and complete-evidence recall is 0.

### Decision

Count the result as a baseline retrieval failure because the answerable question remains in the
metric denominator, but attribute the dominant cause to extraction/representation rather than
BM25 ranking. Do not add OCR from this single example; quantify the failure slice first.

## Observation 004 - Lexical ranking favors a rare framing word

- Date: 2026-08-31
- Split: `development_tune`
- Question ID: `urnuuid0a20b83c-2af0-4503-9220-c63470cdd214::q3`
- Document ID: `urnuuid0a20b83c-2af0-4503-9220-c63470cdd214`
- Gold physical PDF page: 71
- Gold answer: `Focus Area 2: Addressing the over-representation of Aboriginal and Torres Strait
  Islander children in child protection systems.`

### Observation

The page-71 text layer is present and includes: `The achievement of Focus Area 2 will require
efforts across the other 3 focus areas.` The benchmark question paraphrases this as `depending on
progress across all the others`. Exact lexical matching therefore misses `depending` versus
`require efforts`, `progress` versus the page wording, and `others` versus `other`.

BM25 ranked page 71 sixth with score `10.3329`. Incorrect page 24 ranked first with score
`12.6786`; it contains the rare query framing term `described` twice, contributing approximately
`5.2241` points despite not containing `focus area`. This is a ranking failure after successful
text extraction, not a missing-text failure.

### Decision

Keep the v0 tokenizer and BM25 parameters unchanged during the smoke test. Check whether query
framing terms, morphological mismatch, or semantic paraphrase recur across a broader failure
slice before testing a bounded retrieval intervention.

## Observation 005 - Lexical ambiguity and global set retrieval

- Date: 2026-08-31
- Split: `development_tune`
- Question ID: `urnuuid0a20b83c-2af0-4503-9220-c63470cdd214::q2`
- Document ID: `urnuuid0a20b83c-2af0-4503-9220-c63470cdd214`
- Gold physical PDF pages: 68, 69, 71, and 74
- Gold answer: `4`
- Question: `How many numbered 'Box' callout sections (with distinct titles) appear across the
  entire document?`

### Observation

The four gold pages have intact text layers containing `Box 1`, `Box 2`, `Box 3`, and `Box 4`
with distinct titles. Their BM25 ranks are 2, 7, 4, and 15 respectively. At `K=10`, three of four
gold pages are retrieved: any-evidence recall is 1, evidence recall is 0.75, and
complete-evidence recall is 0.

Incorrect page 4 ranks first. Its `GPO Box 9820 Canberra` postal address matches the query token
`box`, while `Enquiries regarding this document` matches the comparatively rare query token
`document`. BM25 does not distinguish a numbered callout box from a postal box. The benchmark
also describes the task using `numbered`, `callout`, `sections`, `distinct`, and `titles`, which
need not appear literally on each gold page.

The answer requires global set retrieval followed by counting: identify all four `Box + number +
title` instances across the document, reject unrelated senses of `box`, and count the distinct
callouts. No single page directly states the total.

### Decision

Keep this as a text-present retrieval failure. Do not change the baseline from one ambiguous term;
measure whether lexical ambiguity or global enumeration recurs in the larger tune evaluation.

## Observation 006 - Photograph counting is outside a text-only representation

- Date: 2026-08-31
- Split: `development_tune`
- Question ID: `urnuuid0d4da810-0b76-4979-a774-0f8bd6fae742::q1`
- Document ID: `urnuuid0d4da810-0b76-4979-a774-0f8bd6fae742`
- Gold physical PDF pages: 30, 31, 34, 35, 38, and 40
- Gold answer: `4`
- Question: `How many photographs of actual houses (not architectural diagrams or illustrations)
  appear across the entire chapter on building-integrated design?`

### Observation

The benchmark uses page 30 to establish the chapter start, pages 31, 34, 35, and 38 for the four
actual-house photographs, and page 40 to establish the next chapter boundary. All six Page Records
have `extraction_status = ok`, but ordinary extracted text does not encode whether a visible image
is an actual-house photograph or an architectural diagram.

BM25 Top-5 pages are 4, 10, 21, 22, and 30, retrieving only the chapter-start evidence. Top-10
also retrieves page 38 at rank 9, but still retrieves only two of six gold pages. The system runs
as designed; the incomplete result is an evaluation failure caused primarily by an unrepresented
visual distinction, not a BM25 implementation error.

### Decision

Do not tune BM25 parameters to address visual content that is absent from its input. Retain this as
a manually verified visual-representation limitation. Use aggregate modality results and later
Oracle Reasoning results before deciding whether a visual path is sufficiently valuable to add.
