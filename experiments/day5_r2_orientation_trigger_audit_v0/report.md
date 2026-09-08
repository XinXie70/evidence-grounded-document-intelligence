# R2 OCR Orientation Trigger Audit v0

## Purpose

Avoid running four-way OCR on every page. First measure original-orientation OCR
quality, then retry cardinal rotations only for suspicious retrieved candidate
pages.

## Audit scope

- Split: development tune only
- Documents: the two registered R2 scanned documents
- Candidate source: deterministic adjacent expansion around BM25 Top-10
- Logical candidate occurrences: 151 across nine questions
- Unique candidate pages after document-level deduplication: 57
- Labels used to select candidates or calculate OCR confidence: none

The original orientation of each unique candidate page was OCRed to Tesseract TSV.
Structural rows and empty text rows were excluded. Mean confidence was calculated
over recognized words with non-negative confidence.

## Observed lower tail

| Rank from lowest quality | Document | Physical page | Words | Mean confidence | Confidence mass | High-confidence ratio |
|---:|---|---:|---:|---:|---:|---:|
| 1 | bird registration | 14 | 105 | **35.73** | 3751.67 | 13.3% |
| 2 | groundwater | 37 | 496 | 48.25 | 23930.27 | 22.2% |
| 3 | bird registration | 50 | 69 | 56.06 | 3868.12 | 31.9% |
| 4 | groundwater | 19 | 164 | 63.52 | 10417.27 | 48.8% |

The known upside-down page is the unique worst page and is separated from the
next page by 12.52 mean-confidence points.

## Frozen v0 trigger

Retry 90, 180, and 270 degree OCR only when original-orientation mean word
confidence is strictly below 40.0. At equality, keep the original orientation.

On this audit set, the trigger selects 1/57 unique candidate pages (1.75%): bird
registration physical page 14. Four-way OCR then selects 180 degrees by recognized
word confidence mass and restores the relevant table text.

## Interpretation and limitation

The trigger sharply limits extra local OCR work while recovering the observed
orientation failure. The threshold is a tune-split candidate, not a universal OCR
constant. It must be validated without modification on later held-out R2 pages
before promotion.
