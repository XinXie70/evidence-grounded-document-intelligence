# Day 2 Development-Tune Batch Dry Run

## Purpose

This read-only dry run fixes the expected scope of the formal page-level BM25 tune baseline before
batch PDF extraction begins. It reads the frozen split manifest, PDF audit, and guarded `dev`
benchmark records. It does not extract a new PDF page, run BM25, access locked-test labels, or
change a retrieval configuration.

## Split boundary

- Allowed split: `development_tune` only.
- Tune documents: 82.
- Development-calibration documents: excluded.
- Locked-test documents: excluded.
- Tune/calibration document overlap: 0.
- Tune/locked-test document overlap: 0.
- Calibration/locked-test document overlap: 0.
- Locked-test question IDs remain omitted from the manifest and are represented only by their
  frozen count and checksum.

The batch extractor must use the 82 tune document IDs as an explicit whitelist. It must not infer
scope from every PDF present in `data/raw/docscope/pdfs/`.

## Expected document and page scope

| Item | Count |
|---|---:|
| Tune documents in the split manifest | 82 |
| Matching documents in the PDF audit | 82 |
| Expected physical pages / Page Records | 3,858 |
| Page Records already produced during smoke tests | 192 |
| Page Records remaining | 3,666 |
| Per-document JSONL files already present | 3 |
| Per-document JSONL files remaining | 79 |

Existing smoke Page Record files:

| Document ID | Expected pages | Existing records | Sequential |
|---|---:|---:|---:|
| `urnuuid0812e9ac-6f30-4624-9c78-6f4176467918` | 53 | 53 | yes |
| `urnuuid0a20b83c-2af0-4503-9220-c63470cdd214` | 88 | 88 | yes |
| `urnuuida3024dbb-48a6-4849-bb2f-910722e335ba` | 51 | 51 | yes |

No existing Page Record JSONL file belongs to a non-tune document.

## Expected page extraction-status distribution

The counts below apply the exclusive Page Record thresholds to the frozen PDF audit character
counts:

| Page status | Rule | Expected pages |
|---|---|---:|
| `text_layer_missing` | 0-19 non-whitespace characters | 154 |
| `low_text` | 20-99 non-whitespace characters | 140 |
| `ok` | 100 or more non-whitespace characters | 3,564 |
| **Total** |  | **3,858** |

These are expected baseline inputs, not reasons to delete pages or silently apply OCR.

## Expected question scope

| Item | Count |
|---|---:|
| Tune question IDs in the manifest | 256 |
| Matching guarded dev records loaded | 256 |
| Eligible answerable evidence questions | 239 |
| Protocol exclusions | 17 |
| Exclusion reason: unanswerable | 17 |
| Eligible single-page evidence questions | 86 |
| Eligible multi-page evidence questions | 153 |

Only the 239 eligible questions enter answerable evidence-retrieval metrics. The 17 unanswerable
questions remain preserved for later reliability/selective-answering evaluation.

## Gold evidence text-layer risk

Across the 239 eligible questions there are 448 unique gold evidence pages:

| Gold-page status | Unique pages |
|---|---:|
| `ok` | 437 |
| `low_text` | 2 |
| `text_layer_missing` | 9 |
| **Total** | **448** |

- Eligible questions with at least one `text_layer_missing` gold page: 9.
- Eligible questions with at least one `low_text` gold page: 2.

These questions remain in the formal baseline denominator. Results must later be reported by
text-layer slice so that extraction/representation failures are not misattributed only to BM25.

## Batch-builder acceptance checks

Before the formal tune baseline can run, the deterministic batch Page Record builder must:

1. accept only the frozen 82-document tune whitelist;
2. refuse calibration, locked-test, unknown, duplicate, or missing document IDs;
3. require exactly one source PDF for every allowed document;
4. write one JSONL file per PDF with atomic replacement;
5. preserve 1-based physical page order and unique `(doc_id, page)` identity;
6. require the written record count to equal the frozen PDF-audit page count;
7. re-read every JSONL file and require an exact round trip;
8. report exclusive extraction-status counts per document and in aggregate;
9. distinguish verified existing smoke outputs from newly generated outputs;
10. produce a deterministic derived manifest containing scope, counts, and source/output
    identities.

The builder should be tested first in dry-run mode and against the three verified smoke outputs.
Only after those checks pass should it generate the remaining 79 files and 3,666 Page Records.

## Decision

The expected scope is internally consistent: 82/82 tune documents and 256/256 tune questions are
accounted for, the split has zero document overlap with calibration and locked test, and the three
existing smoke corpora match their audited page counts.

Proceed to implement the deterministic tune batch Page Record builder with tests. Do not run the
full extraction until its whitelist, page-count, existing-output, and dry-run behavior have been
verified.

## Batch execution result

- Execution date: 2026-08-31.
- Batch-builder tests before execution: 4/4 passed.
- Full discovered project tests before execution: 41/41 passed.
- Newly generated per-document JSONL files: 79.
- Previously generated and re-verified JSONL files: 3.
- Final per-document JSONL files: 82.
- Final Page Records: 3,858.
- Pending documents after independent re-planning: 0.
- Final status counts: 3,564 `ok`, 140 `low_text`, 154 `text_layer_missing`.
- Every output JSONL SHA-256 matches the batch manifest.
- Batch manifest SHA-256:
  `634705896e8e796fa15c44b3e22968b0806797ba115cf5b7d3bde9eb7c1c2556`.

Pinned `pypdf` emitted non-fatal warnings for unsupported advanced font encodings and a small
number of malformed object pointers. No document raised an extraction exception, and the process
exited successfully. These warnings do not justify silent repair; the retained low/missing-text
statuses remain the baseline representation signal.

The generated corpus manifest is `data/derived/page_records_manifest.json`. It records the frozen
source PDF SHA-256, derived JSONL SHA-256, audited page count, and exclusive extraction-status
counts for every tune document.
