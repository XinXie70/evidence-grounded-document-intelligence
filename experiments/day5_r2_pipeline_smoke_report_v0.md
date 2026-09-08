# Day 5 R2 Retrieval-Pipeline Smoke Report v0

## Scope

This smoke test connects the previously validated R2 components through evidence retrieval:

`native Page Records -> label-free route -> full-document OCR corpus -> frozen BM25 -> Top-K evidence package -> reasoning-ready input`

It does not call an answer-generation model and does not score answer correctness.

## Case

- Case: `pilot_17`
- Question ID: `urnuuida3024dbb-48a6-4849-bb2f-910722e335ba::q3`
- Native text coverage: 0/51 pages
- Route: `r2_scanned_document`
- OCR: Tesseract 5.5.3, English, OEM 1, PSM 3
- Rendering: pdftoppm at 200 DPI
- Retrieval: frozen page BM25, `k1=1.2`, `b=0.75`, repeated query tokens retained
- Top-K: 3

## Output

The ranked evidence pages were:

1. page 12, score 16.458741404724304;
2. page 10, score 11.803762192222678;
3. page 30, score 10.434034081489298.

The benchmark gold page is page 12, used only after retrieval for this report. It ranked first.

The audit package preserves rank, score, extraction status, and page text. The separate
reasoning-ready record preserves the identical page order but exposes only `page` and `text` to the
model. It contains no gold page, benchmark answer, or retrieval score.

Artifacts:

- evidence package SHA-256:
  `eaca1fae51d83bd2fea7496ea27530ab9d536f58fd3ea24658874842ffc38776`;
- real-retrieval input SHA-256:
  `6c03905a0d3b31809e21069732d327775bcd8456695dbcb66d96ae01b316b8cb`.

## Result

The R2 path is now connected through evidence retrieval for a real fully scanned document. The
pipeline correctly avoids meaningless all-zero native BM25 ranking, creates a verified OCR corpus,
and returns the answer-supporting page at rank 1 without label access during inference.

The result establishes retrieval readiness, not final QA success. A paid reasoning call is a
separate next-stage decision and must use the standing per-request cost preflight and reminder.

## Verification

- Full local suite: 123 tests passed.
- Paid API cost: USD 0.
