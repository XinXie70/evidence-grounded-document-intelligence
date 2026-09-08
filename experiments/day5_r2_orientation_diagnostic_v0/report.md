# R2 OCR Orientation Diagnostic v0

## Failure under investigation

Bird-registration q1 retrieves physical page 14 after adjacent-page expansion,
but the baseline OCR text is upside down and mostly unreadable. This prevents a
later lexical line selector from reliably finding the evidence even though the
correct page is present in the candidate pool.

## Label-free intervention

The same rendered page was OCRed at 0, 90, 180, and 270 degrees. The selector
uses the sum of Tesseract confidence across recognized words. It does not use the
benchmark answer, evidence text, or gold page labels. Ties use mean confidence,
then recognized word count, then the configured rotation preference.

| Clockwise rotation | Recognized words | Mean confidence | Confidence mass | Words with confidence >= 80 |
|---:|---:|---:|---:|---:|
| 0 | 105 | 35.73 | 3751.67 | 14 |
| 90 | 104 | 75.32 | 7832.87 | 71 |
| 180 | 111 | 74.43 | **8261.37** | **77** |
| 270 | 31 | 49.09 | 1521.88 | 5 |

The deterministic selector chose 180 degrees. That OCR output visibly restores
`Bloodline/ Relation Information` and
`Example: (father of #11 and #12)`.

## Conclusion

This case is an OCR-orientation failure, not a reasoning failure. Orientation
recovery is a justified R2 input-side candidate because it repairs the observed
representation error without model training or benchmark-label access.

Do not yet apply four-way OCR to every page. This is a one-page diagnostic. The
next step is to define a conservative trigger and evaluate it on retrieved R2
candidate pages so ordinary upright pages remain unchanged whenever possible.
