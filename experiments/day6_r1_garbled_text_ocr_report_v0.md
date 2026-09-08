# Day 6 R1 Garbled-Text OCR Recovery v0

## Outcome

The label-free garbled-text detector selected one 36-page tune document. Local
OCR recovered readable English and fixed both of that document's R1 retrieval
failures.

| Question | Native-text gold ranks | OCR-text gold ranks | Complete at Top 10 |
|---|---|---|---|
| Oven probe plus cooking guide | 21, 22 | 2, 7 | Yes |
| Multi-page troubleshooting table | 30, 31, 32 | 3, 2, 1 | Yes |

Across all 64 eligible R1 tune questions, conditionally replacing native text
only for the detected document changed:

- Any-evidence Recall@10 from 90.6% to 93.8%;
- Complete-evidence Recall@10 from 79.7% to 82.8%;
- two questions gained complete evidence;
- zero questions regressed.

The OCR corpus contains 36 sequential Page Records: 35 `ok`, one `low_text`,
and zero `text_layer_missing`. Pages 21 and 29 were visually inspected to
confirm page identity, orientation, and legibility.

## Interpretation

This is an input-decoding repair, not model training. Native extraction exposed
many characters, but embedded-font mapping made the content lexically
unsearchable. A greater-than-5-percent Unicode control-character ratio detected
the failure before retrieval, and Tesseract restored searchable text.

The result justifies keeping this narrow OCR fallback in the R1 candidate. It
does not justify OCR for every PDF. Only one of 82 tune documents triggered the
rule.

## Boundary and next step

No OpenAI API request was made. Calibration labels and locked-test content were
not accessed. Eleven R1 tune questions still lack complete evidence at Top 10;
their observed failures must be analysed before another change is proposed.
