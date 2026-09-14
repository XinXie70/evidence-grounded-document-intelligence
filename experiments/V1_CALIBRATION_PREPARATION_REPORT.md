# V1 Calibration Preparation Report

**Status:** Page Records and label-free question selection complete; evidence packaging pending
**Split:** `development_calibration`
**Date:** 2026-09-11

## Completed local preparation

- Projected 132 calibration questions from 35 documents into a label-free selection containing
  only `pilot_id`, `question_id`, `doc_id`, and question text.
- Generated deterministic Page Records for all 35 calibration PDFs and all 1,832 physical pages.
- Replayed the corpus planner after generation: 35 existing outputs verified and 0 documents
  remained pending.
- Ran baseline full-document Tesseract OCR for the only wholly scanned calibration document (50
  pages). OCR produced non-empty text on every page: 47 `ok` and 3 `low_text` pages.
- No OpenAI API request was made and no benchmark answer, answerability label, gold evidence page,
  fact, or bounding box entered retrieval input.

## Text-layer inventory

| Status | Pages |
|---|---:|
| Native text `ok` | 1,705 |
| Native text `low_text` | 66 |
| Native text missing | 61 |
| Total | 1,832 |

The 61 missing native-text pages are distributed across the PDFs. The frozen R2 trigger is not a
per-page fallback: it activates only when the entire document has zero native-text pages. Exactly
one 50-page document meets that condition.

## Frozen artifacts and checksums

- Label-free selection: `experiments/v1_calibration_selection_v0.json`
  (`dd314c1ff37a71e745956799b05fcd15f9c95d1e286c796aa35b93c404f046f4`)
- Calibration Page Record manifest: `data/derived/page_records_calibration_v1_manifest.json`
  (`8e4d11227c35336ed0eb1594bae5025fef65669b584762269fb89635cb696ec3`)
- Scanned-document baseline OCR manifest:
  `data/derived/ocr_calibration_v1/urnuuide2916fd0-fcb8-4318-bd65-bea7666aad5c/manifest.json`
  (`a809af1bc33a6924c1106b49e7d1bd752ec622477ff342756f62aa07adc9069b`)

Derived Page Records, OCR text, and page renders remain local and ignored by Git. The manifest and
this report retain their provenance.

## Next local step

Apply the frozen R2 orientation-confidence trigger to its retrieved candidate pages, then run the
frozen R0/R1/R2/R3 retrieval paths to produce calibration evidence packages and label-free
confidence inputs. Only after those inputs are immutable will an API token and cost budget be
calculated and shown to the user for approval.

The deterministic suite passes 334 tests.
