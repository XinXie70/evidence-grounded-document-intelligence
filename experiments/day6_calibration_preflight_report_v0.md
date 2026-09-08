# Day 6 Development-Calibration Preflight v0

**Date:** 2026-09-08  
**Status:** not ready for calibration execution

## What this step did

This was a label-free readiness check, not a benchmark evaluation. It used only
the calibration question ID, question text, document ID, frozen split metadata,
and Day 1 PDF/text-layer audit metadata. It did not use answers, evidence pages,
evidence boxes, facts, or locked-test content.

All 35 calibration PDFs exist, remain openable according to the Day 1 audit,
and match their recorded SHA-256 checksums. They contain 1,832 physical pages.
No calibration Page Record JSONL has been generated yet.

## Frozen router inventory

| Route | Questions | Distinct documents | Meaning |
|---|---:|---:|---|
| R0 native text | 99 | 32 | Extract native text and run the frozen sparse retrieval path. |
| R1 local visual | 29 | 13 | The question explicitly asks about a chart, table, image, map, or similar local visual structure. |
| R2 scanned document | 1 | 1 | The document has zero native-text pages and requires the frozen full-document OCR route. |
| R3 document-global | 3 | 3 | The question asks for coverage across the whole document. |

Distinct-document counts overlap because different questions in one PDF can use
different routes.

## Local preparation workload

- Generate deterministic native Page Records for 1,832 pages.
- Only one document requires full-document OCR: 50 pages.
- This preparation is local and has no OpenAI API cost.

## Why calibration does not start yet

R0 is implemented and R2 candidate v2 is frozen. R3 has a conservative
abstention boundary. R1, however, accounts for 29 of 132 questions and is not
yet a frozen batch pipeline: prior tune experiments proved that visual input can
recover answers, but they did not freeze a deterministic method for locating and
packaging the relevant visual region for an unseen question.

Running calibration now would create an incomplete-system score. Worse, fixing
R1 after inspecting those outcomes would turn calibration into another tuning
set. Therefore the gate remains closed.

## Next permitted step

Use only `development_tune` observations to define and test the smallest
deterministic R1 candidate, freeze it, and explicitly freeze the R3 abstention
policy. Then:

1. generate and checksum all calibration Page Records;
2. build evidence packages without labels;
3. calculate a real token and dollar budget;
4. remind the user of the paid budget and request approval;
5. execute calibration once;
6. score only after all predictions are immutable.

The standing safety rule remains a maximum of USD 1.00 per paid request, with a
reminder before each paid run. No paid request was made in this preflight.
