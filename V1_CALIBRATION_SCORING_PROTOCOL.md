# V1 Calibration Scoring Protocol

Status: **frozen before opening `development_calibration` answer or evidence labels**
Frozen date: 2026-09-11 (Australia/Sydney)

## Purpose

This protocol converts the already-frozen V1 predictions on 132
`development_calibration` questions into task-correctness, evidence-support, and grounded-correctness
labels. Calibration may select numeric confidence thresholds only. It may not change retrieval,
routing, OCR, visual retrieval, prompts, answer generation, confidence features, or this evaluator.

## Immutable prediction input

- Normalized predictions: `results/v1_calibration_normalized_v1/`
- Selection: `experiments/v1_calibration_selection_v0.json`
- Confidence policy: `configs/confidence_policy_v1_tune_v0.json`
- The normalized copy may only clear citations attached to a null `insufficient_evidence` output; it
  may not change answer text or answerability status.

## Semantic task correctness

The project follows DocScope's official semantic-answer principle: compare factual meaning rather
than exact wording, require all material components, reject contradictory additions, and do not use
outside knowledge. The official implementation uses an OpenAI-compatible model judge and treats
`Unanswerable` as the reference answer for unanswerable questions.

Deterministic cases are resolved locally:

1. gold unanswerable + system abstention -> correct;
2. gold answerable + system abstention -> incorrect;
3. gold unanswerable + system answer -> incorrect.

Only gold-answerable questions with a non-null system answer are sent to the pinned semantic judge.
The judge receives the question, gold answer, and system answer, but no document context.

## Evidence support and grounded correctness

For every non-null system answer with at least one cited page, a separate support judge receives
only the question, system answer, and the exact cited-page evidence that was supplied to answer
generation. It does not receive the gold answer or gold evidence labels. It must decide whether all
material claims needed for the answer are supported by those citations. Answers without citations
are unsupported. Abstentions contain no answer claim and are treated as supported for this field.

`grounded_correct = task_correct AND evidence_supported`.

Gold-page precision/recall and complete-evidence recall remain separate deterministic diagnostics;
they do not replace the support judgment because a valid alternative evidence page may exist.

## Pinned judge configuration

- Provider/API: OpenAI Responses API
- Model: `gpt-5.6-terra`
- Reasoning effort: `low`
- Temperature: omitted and therefore pinned to the model/API default
- Storage: disabled
- Retry policy: zero automatic retries; a failed request is preserved and explicitly rerun
- Semantic schema: `{consistent: boolean, reason: string}`
- Support schema: `{supported: boolean, reason: string}`
- Prompt/config files and their SHA-256 hashes are recorded in every result and batch manifest
- Judge results are cached; a different judge model may not be mixed into this calibration run

### Operational amendment: repeated empty output

`calibration_026/support` exhausted all 192 output tokens on internal reasoning twice and returned no
JSON. The first occurrence predated failure-response persistence; the second is preserved with
`incomplete_details.reason=max_output_tokens` and 192/192 reasoning tokens. Repeating the identical
request again is therefore stopped. For this request only, a frozen fallback keeps the model,
instructions, input, schema, reasoning effort, temperature behavior, storage, and retry policy
unchanged, while raising only `max_output_tokens` from 192 to 384. This is an operational completion
fix triggered by an observed API failure, not by a correctness label or judge decision. Both failed
attempts remain separately accounted for.

The same fallback may be registered for a later support request only after its preserved API response
shows `incomplete_details.reason=max_output_tokens` and invalid/incomplete JSON. Each activation is
recorded by request ID and separately budgeted; it is never selected from the judge's apparent
decision or from benchmark correctness.

### Support-judge V1 supersession

A second independent support request (`calibration_041/support`) then reached the same 192-token
limit and returned truncated JSON. This establishes that 192 is not a reliable output budget for the
support task generally. Before any calibration metrics or thresholds were computed, support-judge
V0 was superseded. All 74 support judgments are rerun from the identical immutable inputs using the
identical model, prompt, schema, reasoning effort, temperature behavior, storage, and retry policy,
with only `max_output_tokens` raised to 1024. V0 support outputs remain preserved for audit but are
excluded from official calibration scoring. Before metrics were computed, the user then approved a
USD 2.00 total cap and requested removal of the too-tight output constraint. To avoid mixing
192-token and 1024-token semantic configurations, all 74 semantic judgments are likewise rerun from
identical immutable inputs at 1024 tokens. Semantic V0 outputs remain auditable but are excluded
from official calibration scoring. The combined historic and replacement-call hard cap is USD 2.00.

This is a project-pinned compatible implementation of DocScope's official semantic criterion. It
does not claim identity with the repository's default `gpt-4o-mini` judge snapshot.

## Human agreement audit

After automatic judging, select a deterministic stratified sample of at least 50 records across:

- answerable/unanswerable;
- answer/abstention;
- R0/R1/R2/R3 routes;
- judge pass/fail and evidence-supported/unsupported outcomes;
- single-page and multi-page evidence where available.

The human reviewer independently labels semantic correctness and evidence support. Report raw
agreement and disagreements. The sample audits judge reliability; it is not used to change prompts,
features, routes, or thresholds.

## Threshold selection

Apply the already-frozen confidence formula, then report task risk and grounded risk at conservative,
tie-respecting target coverages of 100%, 90%, 80%, and 60%. Select and freeze the numeric operating
threshold(s) on calibration once. Only then may the one-time locked test be opened.

## References

- DocScope evaluation README: https://github.com/MiliLab/DocScope/blob/main/code/README.md
- DocScope answer scorer: https://github.com/MiliLab/DocScope/blob/main/code/eval/score_answer.py
- DocScope answer-verification prompt: https://github.com/MiliLab/DocScope/blob/main/code/prompts/answer_verification.txt
