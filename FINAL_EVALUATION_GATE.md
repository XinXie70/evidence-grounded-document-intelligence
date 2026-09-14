# Final Evaluation Gate

**Decision:** V1 is frozen; the locked test remains closed pending explicit one-time authorization.
**Date:** 2026-09-14
**Current release status:** calibrated research system; final held-out result not yet measured.

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
- 376 deterministic tests and the offline preflight pass. All 156 locked-test PDF checksums match;
  no locked-test result artifact exists and no paid request was made by preflight.

## Remaining gate

Before setting the locked-test access acknowledgement:

1. create a clean pre-test Git commit and tag;
2. verify the 68-component freeze manifest again;
3. confirm API availability and review the first paid-batch estimate;
4. obtain explicit user authorization for the one-time final evaluation.

The exact execution order is frozen in [`V1_LOCKED_TEST_PROTOCOL.md`](V1_LOCKED_TEST_PROTOCOL.md).
Every paid batch has an independent hard cap of USD 1.00 and is shown to the user before execution.

## No post-test tuning

Once opened, locked-test outcomes may be scored, bootstrapped, analyzed, and reported, but they may
not change V1 retrieval, routing, OCR, visual ranking, prompts, evidence budgets, confidence policy,
or threshold. Operational retries are allowed only for preserved transport/incomplete-output
failures and may not depend on whether an answer appears correct.
