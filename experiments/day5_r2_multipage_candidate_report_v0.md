# Day 5 R2 Multi-Page Candidate Validation v0

## Question

- Question ID: `urnuuid45a0a8e5-e31b-4e74-9663-f27ab82db68f::q5`
- Question: For well MW3, what is the difference in depth to water (in feet)
  between the earliest monitoring date and the latest monitoring date recorded in
  the monitoring data summary?
- Benchmark answer: `1.05 feet`
- Gold evidence pages: physical PDF pages 10 and 11

## Observed retrieval failure

The scanned document had no usable native text. Full-document Tesseract OCR restored
searchable text on all 37 pages, but the frozen BM25 query policy ranked the two gold
pages at 6 and 11. Consequently, Top-10 contained only one of the two required pages.

The previously retained, label-free query-token deduplication candidate moved the
gold pages to ranks 4 and 9. This produced complete evidence recall at Top-10. The
same candidate had already improved complete evidence recall at 10 by 3.35 percentage
points over 239 eligible development-tune questions, so it was not selected solely
for this example.

## End-to-end candidate

The evaluated R2 candidate used:

1. deterministic full-document Tesseract OCR;
2. BM25 with repeated question tokens deduplicated while preserving first-occurrence
   order;
3. Top-10 page retrieval;
4. layout-preserved OCR text for grounded reasoning; and
5. the frozen reasoning model, instructions, schema, and zero-retry policy.

Retrieved pages, in rank order:

`6, 5, 7, 11, 4, 3, 1, 8, 10, 2`

## Result

- Model answer: `1.05 feet`
- Supporting values: `17.77 feet` and `16.72 feet`
- Cited pages: `10, 11`
- Status: `answerable`
- Structured-output validation: valid
- Citations within supplied context: true

The model selected both relevant pages from a ten-page context, ignored eight
distractor pages, aligned the two dates and measurements, and computed the correct
difference.

## Paid-call audit

- Model snapshot: `gpt-5.6-terra`
- Retries: `0`
- Conservative preflight: `$0.020314`
- Approved hard cap: `$1.00`
- Actual estimated cost: `$0.0154885`
- Input tokens: `5668`
- Output tokens: `110`
- Input SHA-256: `b51e7e8a437988cd30e293ba25bbf5aa888c8aa6c28f5bad430372f2cceeeef8`
- Request SHA-256: `806806ee89ceb459a1eb3843ce7c5ceb8991c9aa5c7840d0b960a0e1d7cc6095`

## Conclusion

This experiment demonstrates successful multi-page recovery for a scanned document:

`scanned PDF -> deterministic OCR -> complete Top-10 evidence retrieval -> layout-preserved context -> grounded multi-page calculation`

Together with the pilot 17 list-counting recovery, this provides two positive R2
case studies: one structure-sensitive single-page question and one multi-page table
calculation. These cases justify freezing an R2 candidate specification for broader
development evaluation, but they do not establish corpus-wide effectiveness by
themselves.
