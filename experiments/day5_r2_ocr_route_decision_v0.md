# Day 5 R2 Full-Document OCR Route Decision v0

## Decision

For a document whose native Page Records contain zero nonempty text pages, route retrieval
preparation to deterministic full-document OCR before page-level BM25. Do not treat the native
BM25 ordering of all-zero pages as evidence retrieval.

The route is inference-time and label-free. It uses only the question and native document text
coverage. Gold pages and benchmark answers are not available to the router or OCR builder.

## Evidence

Two R2 cases were present in the 24-question reliability pilot, and both were evaluated with the
same pinned OCR settings: Poppler rendering at 200 DPI followed by Tesseract 5.5.3 with English,
OEM 1, and PSM 3.

| Case | Document pages | Native retrieval | Full-document OCR retrieval |
|---|---:|---|---|
| pilot16 | 37 | all-zero scores; pages 1/2/3 returned by tie order | gold page 11 at rank 6 and page 10 at rank 11; query-token dedup moves them to ranks 4 and 9 |
| pilot17 | 51 | all-zero scores; pages 1/2/3 returned by tie order | gold page 12 at rank 1 under both query-token policies |

Full-document OCR therefore restores label-free page discovery in both observed R2 cases. It does
not guarantee complete evidence within every K: pilot16 retains a lexical-ranking and multi-page
evidence-completeness problem after text recovery.

## Implemented boundary

- R0 continues with native Page Records.
- R1 requests images of retrieved candidate pages; it does not trigger full-document OCR.
- R2 plans or explicitly executes the full-document OCR corpus builder.
- R3 requires document-complete processing or abstention; it does not silently reuse the R2 path.
- OCR execution is opt-in. Planning is the default.

The OCR builder refuses to overwrite outputs, verifies physical page continuity and counts, records
per-page and corpus checksums, round-trips Page Records, and publishes a final output directory only
after success. Interrupted work remains distinguishable as partial output.

## Verification

- The real pilot17 builder run produced 51 `ok` Page Records.
- Its Page Record SHA-256 exactly matched the earlier manual pipeline:
  `4b99fcb1baad65d82efea74339976239af3ba2caa7161af217d7183ee7ca3d78`.
- The real pilot17 preparation plan selected `r2_scanned_document` from 0/51 nonempty native pages
  without executing OCR or accessing labels.
- The full local suite passed 119 tests.
- Paid API cost: USD 0.

## Remaining limitation

The current trigger covers the observed zero-native-text R2 slice. It does not yet define a
threshold for partially scanned documents. Any such threshold must be motivated by observed
development failures and evaluated separately rather than inferred from these two cases.
