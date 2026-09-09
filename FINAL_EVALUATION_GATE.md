# Final Evaluation Gate

**Decision:** calibration and locked-test execution are deferred.  
**Date:** 2026-09-09  
**Current release status:** credible portfolio MVP; not a final benchmark submission.

## Why the gate is closed

The label-free calibration preflight found 132 questions across 35 documents:

| Frozen route | Questions | Current readiness |
|---|---:|---|
| R0 native text | 99 | implemented |
| R1 local visual structure | 29 | not frozen for unseen batch use |
| R2 scanned document | 1 | tune candidate frozen |
| R3 document-global | 3 | conservative abstention boundary available |

The R1 tune diagnostics established that page images can recover missing text and lost
two-dimensional structure. They did not establish a deterministic, label-free method for locating
and packaging the relevant visual region for a previously unseen question. Running calibration
before this route is frozen would measure an incomplete system. Changing R1 after seeing those
outcomes would misuse calibration as a second tuning split.

The current BM25 score and margin features are also insufficient as a standalone confidence
policy: successful and failed tune examples overlap on both signals. No numeric abstention
threshold has therefore been selected.

## What is already valid to claim

- document-isolated development results for BM25, dense retrieval, and RRF;
- the 24-question C0/C1/C2 reliability pilot and its Oracle Evidence gap;
- the 3/3 eligible visual-recovery diagnostic, explicitly labelled as a small pilot;
- the frozen six-document generic-comparison validation;
- deterministic evidence metrics, citation checks, cost logging, and test coverage.

## Single next research gate

Use only `development_tune` observations to define and freeze one generic R1 policy that:

1. identifies candidate pages without gold evidence;
2. produces page or region images deterministically;
3. records reversible page/region provenance;
4. has a bounded evidence and token budget;
5. either supplies adequate visual context or abstains explicitly.

After that policy passes a predeclared tune-only test, calibration may be generated and executed
once. It may select the abstention threshold but must not change the retriever, router, prompts,
or evidence packaging. The locked test may run once only after calibration freezes the entire
system.

## Stop rule

If a generic R1 policy cannot be frozen within one bounded tune-only iteration, publish the MVP
without calibration or locked-test claims. Do not add a new agent framework, train a custom model,
or inspect calibration labels to compensate.
