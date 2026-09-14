# V1 Completion Protocol

**Status:** visual retrieval and tune confidence gates passed; calibration preparation pending
**Date:** 2026-09-11
**Purpose:** close the reliability and held-out evaluation gap left by the portfolio MVP without
reopening unbounded visual-system development.

## Relationship to the portfolio MVP

The portfolio MVP and its reported results remain immutable. The generic visual page reranker
was correctly dropped after its preregistered tune-only experiment produced no net Complete
Evidence Recall improvement. This completion phase does not reinterpret that negative result or
claim that visual localization has been solved.

The new phase first gives a bounded, question-conditioned visual retriever one generic tune-only
evaluation. If it passes its preregistered gate, it joins V1; otherwise V1 falls back to the
text-first system with explicit abstention. Region-level visual reasoning beyond this bounded
candidate remains V2 work.

## Frozen objective

Complete the original evaluation chain:

```text
Evidence Retrieval -> Grounded Reasoning -> Confidence -> Selective Answering
                    -> Calibration -> One-time Locked Test
```

The primary new deliverables are:

1. one generic question-conditioned visual page retriever evaluated on the full R1 tune slice;
2. one scalar, inference-time confidence score with deterministic tie-breaking;
3. risk-coverage and grounded-risk-coverage curves;
4. operating points at 100%, 90%, 80%, and 60% target coverage;
5. thresholds selected only on `development_calibration`;
6. one immutable locked-test run after the entire pipeline is frozen;
7. document-clustered uncertainty intervals and a retained failure audit.

## Final V1 system boundary

### Retrieval

- Native-text documents use the already selected BM25 + BGE dense RRF retriever.
- The candidate budget remains RRF Top-10. The failed Top-2 dense reranker and failed generic
  visual-layout reranker remain dropped.
- The existing deterministic OCR route may be used only under its already frozen trigger and
  provenance rules.
- No gold evidence page, answer, fact, bbox, answerability label, calibration outcome, or locked
  test outcome may affect retrieval or routing.

### Visual and global questions

- Before calibration, one separately preregistered question-conditioned visual page retriever may
  be developed and evaluated using `development_tune` only.
- The candidate may join V1 only if it passes its frozen aggregate keep/drop rule; otherwise V1
  makes no claim that generic visual localization is solved.
- Questions routed as local-visual may always use the same label-free RRF/OCR evidence available
  to the text-first system, but receive no question-specific crop or hand-written page rule.
- Questions whose evidence cannot be supported by that package must abstain.
- Document-global questions keep the existing conservative abstention boundary unless a fully
  deterministic, tune-only implementation is frozen before calibration.

### Grounded reasoning

- The reasoner may use only the supplied evidence package.
- Answers must cite supplied physical pages.
- Invalid output contracts, out-of-context citations, missing required citations, or unsupported
  facts cannot be counted as grounded successes.
- Per-question prompts, hand-written facts, and question-ID-specific branches are forbidden.

## Confidence-policy rules

The confidence score must be available at inference time and must not use evaluation labels.
Permitted inputs include:

- BM25 and dense retrieval scores or ranks;
- sparse/dense rank agreement and RRF concentration or margins;
- query-token coverage and evidence-package stability;
- Page Record extraction status and OCR trigger/provenance;
- response status, response-contract validity, and citation-within-context validation;
- deterministic support checks that do not inspect benchmark answers.

Forbidden inputs include benchmark answerability, answers, gold pages, evidence recall, Oracle
condition identity, manual correctness, audited evidence sufficiency, and any locked-test label.

Feature definitions, score direction, weights, missing-value behavior, and tie-breaking must be
frozen using `development_tune` only. Numeric answer/abstain thresholds are reserved for
`development_calibration`.

## Data-access sequence

The following order is mandatory:

1. Implement and test the frozen visual-page candidate without reading gold evidence.
2. Evaluate it once on the full 63-question R1 `development_tune` slice and apply its keep/drop
   rule.
3. Freeze the resulting V1 retrieval and routing path.
4. Implement and test the label-free feature extractor and risk-coverage evaluator.
5. Pair features with existing tune-only outcome labels for offline signal analysis.
6. If existing labels are insufficient, preregister and run one bounded tune-only reasoning batch;
   freeze its automatic and manual scoring protocol before inspecting its outcomes.
7. Either freeze one confidence formula or stop with a documented negative result.
8. Generate calibration predictions once with no answer/evidence labels available to the runner.
9. Freeze predictions before scoring them.
10. Select numeric thresholds only from calibration outcomes.
11. Freeze retrieval, routing, prompts, evidence budget, confidence formula, thresholds, evaluators,
   and cost configuration.
12. Execute the locked test exactly once.
13. Report all results, including failures and abstentions; do not tune after locked-test access.

## Tune gate for opening calibration

Calibration remains closed until all of the following are true:

- confidence features are deterministic and free of forbidden fields;
- every feature used by the policy is available for an unseen question;
- the same formula applies to every question without question-ID-specific logic;
- higher confidence is directionally associated with better grounded outcomes on tune-only data;
- the curve implementation and tie-breaking pass synthetic tests;
- the complete prediction and scoring path can be replayed without accessing locked-test labels;
- expected API cost is recorded and each paid run is capped at USD 1.00 with a user reminder.

Failure to obtain a useful generic confidence ordering closes V1 completion without opening
calibration. It does not authorize another visual reranker, agent framework, frontend, custom model
training, or per-case patch.

## Calibration policy

- Calibration may choose thresholds but may not change features, weights, retrievers, routing,
  prompts, evidence packaging, or evaluators.
- Target operating points are 100%, 90%, 80%, and 60% coverage. When exact target coverage is
  impossible because of ties, use the deterministic conservative boundary at or below the target
  and report achieved coverage.
- Primary risk is incorrect answers among answered questions.
- Grounded risk additionally treats incomplete or invalid grounding as an error.
- AURC is computed from the full deterministic ranking, with tied scores ordered by stable
  `question_id` only for reproducibility; tied groups must also be reported so this ordering is not
  mistaken for extra confidence information.

## Locked-test release rule

The locked test may be opened only after the calibration artifact records hashes for the complete
system and all selected thresholds. The locked-test run is evaluation-only. Any newly observed
failure becomes future-work evidence and cannot change V1.

## Explicit non-goals

- no new Agent, MCP, LangChain, LangGraph, or multi-agent layer;
- no custom OCR, embedding, VLM, or LLM training;
- no full-document vision by default;
- no per-question hard coding;
- no frontend work before the evaluation chain is closed;
- no replacement of the primary DocScope benchmark.

## Completion checklist

- [x] Freeze the completion scope and data-access order.
- [x] Inventory reusable RRF, dense, OCR, reasoning, and validation artifacts.
- [x] Implement and evaluate the frozen question-conditioned visual page retriever (gate passed).
- [x] Implement generic inference-time confidence features.
- [x] Implement risk-coverage, grounded-risk-coverage, AURC, and operating-point evaluation.
- [x] Add deterministic unit and integration tests (334 passing).
- [x] Run the tune-only confidence gate (directional ordering passed; see
  `experiments/V1_CONFIDENCE_TUNE_REPORT.md`).
- [ ] Prepare and checksum calibration Page Records and prediction inputs (Page Records and
  label-free selection complete; evidence packages pending).
- [ ] Remind the user of cost and receive approval for each paid calibration batch.
- [ ] Freeze and score calibration predictions; select thresholds.
- [ ] Freeze the complete system manifest.
- [ ] Remind the user of cost and receive approval for each paid locked-test batch.
- [ ] Run and score the locked test once.
- [ ] Update English/Chinese README, portfolio status, and resume claims.
