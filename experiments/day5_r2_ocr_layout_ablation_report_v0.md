# Day 5 R2 OCR Layout-Preservation Ablation v0

## Question

- Question ID: `urnuuida3024dbb-48a6-4849-bb2f-910722e335ba::q3`
- Question: How many specific items are listed in the section describing enhancements that are still being worked on?
- Benchmark answer: `5`
- Gold evidence page: physical PDF page 12

## Failure-driven hypothesis

Full-document Tesseract OCR recovered the relevant words and BM25 ranked physical
page 12 first. However, the original Page Record normalization collapsed every
whitespace run, including line breaks. This flattened five visually separate list
items into prose and may have caused the reasoning model to count only four items.

The ablation changes only the representation supplied to grounded reasoning:

- Retrieval continues to use the normalized OCR Page Records.
- Reasoning receives the same ranked pages in the same order, but with the raw OCR
  line structure preserved.
- Model, reasoning effort, instructions, output schema, Top-K, and retry policy are
  unchanged.

## Results

| Condition | Retrieved pages | Page 12 rank | Evidence representation | Answer | Correct |
|---|---:|---:|---|---:|---:|
| Native-text C1 | 1, 2, 3 | not retrieved | empty native text | abstain | no |
| OCR C1, flattened | 12, 10, 30 | 1 | whitespace-collapsed OCR | 4 | no |
| OCR C1, layout-preserved | 12, 10, 30 | 1 | OCR line breaks preserved | 5 | yes |
| Oracle-region visual diagnostic | 12 | oracle | page image | 5 | yes |

## Paid-call audit

- Model snapshot: `gpt-5.6-terra`
- Retries: `0`
- Conservative preflight: `$0.0117365`
- Approved hard cap: `$1.00`
- Actual estimated cost: `$0.005951`
- Input tokens: `2237`
- Output tokens: `30`
- Response validation: valid; citation remained within supplied page 12
- Input SHA-256: `bcd09c340a7bd7da32d00a58818ff6650a7a8652b595be1c3ed4404b4e380fdf`
- Request SHA-256: `534fbccb7099810f8b1ab453314ebedcd1789d3bd778ee3ea2696fac37f46ad5`

## Conclusion

This case demonstrates an end-to-end recovery for the R2 scanned-document route:

`scanned PDF -> deterministic OCR -> BM25 page retrieval -> layout-preserved OCR context -> grounded correct answer`

The observed failure was caused by representation loss between OCR and reasoning,
not by page discovery. The evidence supports retaining two views of OCR output:

1. normalized text for deterministic lexical retrieval; and
2. layout-preserved text for grounded reasoning.

This is a single-case causal validation. It justifies retaining the design as a
candidate, but does not yet establish a corpus-wide performance improvement.
