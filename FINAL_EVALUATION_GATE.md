# Final Evaluation Gate

**Decision:** completed record; V1 was frozen before the explicitly authorized one-time locked test.
**Date:** 2026-09-14 to 2026-09-15
**Current release status:** evaluated research system with final held-out results; V1 remains immutable.

## What has been completed

- The question-conditioned visual retriever passed its preregistered 63-question tune-only gate.
- The frozen pipeline ran once on 132 questions from 35 document-isolated calibration documents.
- Automatic semantic/support judging was checked on a 50-case human sample.
- The final policy answers only when its deterministic eligibility checks pass. Calibration allowed
  74/132 answers: 87.84% task accuracy and 79.73% strict grounded accuracy among answered cases.
- A protocol audit caught that the earlier V0 file confused answer retention with total-question
  coverage. The corrected threshold is 0.3566666666666667 and retains all eligible answers; it is
  not claimed to be a calibrated probability.
- 68 runtime, evaluation, configuration, environment, and protocol files are SHA-256 frozen in
  `experiments/v1_system_freeze_manifest_v1.json`.
- 377 deterministic tests and the offline preflight passed. All 156 locked-test PDF checksums
  matched before access.
- The frozen system produced 730 final prediction records; all 849 required semantic/support judge
  results were completed and validated.
- Final coverage is 59.73%; task accuracy is 42.60% overall and 65.14% among answered questions;
  strict grounded accuracy is 39.86% overall and 60.55% among answered questions.
- Question and document-clustered bootstrap intervals were generated with 10,000 replicates.

## Completed gate

The following prerequisites were completed before or during the authorized evaluation:

1. create a clean pre-test Git commit and tag;
2. verify the 68-component freeze manifest again;
3. confirm API availability and review the first paid-batch estimate;
4. obtain explicit user authorization for the one-time final evaluation;
5. preserve operational failures and count them conservatively;
6. score and report every case without changing V1.

The exact execution order is frozen in [`V1_LOCKED_TEST_PROTOCOL.md`](V1_LOCKED_TEST_PROTOCOL.md).
Every paid batch had an independent hard cap of USD 1.00 and was shown to the user before execution.
The final results are documented in [`experiments/V1_LOCKED_TEST_REPORT.md`](experiments/V1_LOCKED_TEST_REPORT.md).

## No post-test tuning

Once opened, locked-test outcomes may be scored, bootstrapped, analyzed, and reported, but they may
not change V1 retrieval, routing, OCR, visual ranking, prompts, evidence budgets, confidence policy,
or threshold. Operational retries are allowed only for preserved transport/incomplete-output
failures and may not depend on whether an answer appears correct.
