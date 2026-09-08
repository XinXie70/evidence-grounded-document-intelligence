# Day 6 R3 Short Global Phrase Fix v1

## Outcome

Router v0 recognized phrases such as `across the entire document` but missed the
shorter `across the document`. A versioned v1 wrapper now treats the shorter
phrase as a document-global signal with priority over R0, R1, and R2.

Across all 256 development-tune questions, only three routes changed:

- a count of QR-code competition divider sections across the document;
- a count of locations displaying a total-assets figure across the document;
- a count of named personal case studies across the document.

Manual review of question text confirmed that all three require exhaustive
document coverage. There were no unexpected route changes.

| Route | v0 count | v1 count |
|---|---:|---:|
| R0 native text | 178 | 176 |
| R1 local visual | 64 | 63 |
| R2 scanned document | 9 | 9 |
| R3 document global | 5 | 8 |

The original v0 router was not edited. All 13 frozen R2 v2 artifacts retained
their recorded checksums. The R3 execution boundary remains conservative: use a
separately frozen document-complete method or abstain rather than answer from an
incomplete local candidate set.

No calibration labels, locked-test content, or paid API request were used.
