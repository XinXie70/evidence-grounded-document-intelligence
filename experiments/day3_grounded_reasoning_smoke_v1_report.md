# Day 3 Grounded-Reasoning Smoke v1 — Completion Report

## Scope and status

The frozen 10-question development smoke set is complete. Each question was run under two
matched text-only conditions with the same reasoning configuration:

- **C1 Real Retrieval:** frozen BM25 Top-3 physical pages;
- **C2 Oracle Page (text adapter):** benchmark evidence pages represented by their pypdf text.

The run produced 20 successful immutable result files. One additional `smoke_07` Oracle attempt
returned no parseable output; its immutable failure record is retained. The runner was then fixed
so future response-processing failures preserve API status, output, usage, and cost metadata.

Three failure-driven cases were subsequently examined with targeted diagnostic ceilings rather
than a new population sample: C3 Oracle Region for `smoke_08` and `smoke_09`, contextual C3 plus
C4 Oracle Facts for `smoke_06`, and a one-variable upright-orientation C3 intervention for
`smoke_09`. These five additional successful calls are reported separately below and do not alter
the original C1/C2 smoke-set rates.

This is a deliberately stratified smoke test, not a random sample. Its proportions verify the
pipeline and identify diagnostic cases; they are not estimates of benchmark-wide performance.

## Result matrix

| Case | Evidence challenge | Oracle Page text | Real Retrieval | Main observation |
|---|---|---|---|---|
| 01 | Single-page text | Grounded success | Grounded success | Retrieved alternative page 47 was also valid evidence |
| 02 | Multi-page numerical reasoning | Grounded success | Grounded success | Extra retrieved page did not distract the model |
| 03 | Cross-page entity/location chain | Answer correct; citation chain incomplete | Appropriate abstention; required page missing | Retrieval-associated answer loss plus citation-chain weakness |
| 04 | Semantic paraphrase | Grounded success | Appropriate abstention; gold page missing | Clean BM25 semantic-retrieval failure candidate |
| 05 | Flattened table | Grounded success | Grounded success | Extracted table text retained enough structure |
| 06 | Cross-table arithmetic | Strict answer/citation failure | Appropriate abstention; facts missing | Representation/reasoning precision issue; C3/C4 needed |
| 07 | Flattened chart arithmetic | Grounded success | Grounded success | Gold page ranked first; distractors were ignored |
| 08 | Count photographs across a chapter | Appropriate abstention; pixels absent | Appropriate abstention; gold pages also missing | Visual representation bottleneck dominates |
| 09 | Scanned table with no text layer | Appropriate abstention; gold text empty | Appropriate abstention; wrong pages and empty text | Missing-text-layer representation bottleneck dominates |
| 10 | Benchmark-unanswerable, tempting related text | Correct abstention | Correct abstention | Strong selective-answering behavior in this case |

Using strict benchmark answer correctness, Oracle Page text was correct on 7/10 cases and Real
Retrieval on 5/10. Grounded correctness was 6/10 and 5/10 respectively. These counts include the
unanswerable case as correct only when the system abstained. Again, they are smoke-set descriptions,
not general performance estimates.

## What the smoke test established

1. The matched request, response-schema, citation-validation, immutable-output, and cost-log path
   works end to end.
2. BM25 Top-3 can be sufficient for straightforward text, flattened-table, and flattened-chart
   cases, but misses cross-page and semantic-paraphrase evidence in observed cases 03 and 04.
3. “Oracle Page” is currently only an **Oracle Page text adapter**. It cannot represent photographs
   and cannot recover scanned pages whose text layer is empty.
4. The model abstained whenever the supplied context was genuinely inadequate in this smoke set,
   including when related text could have tempted an unsupported answer.
5. Answer correctness and grounded correctness must remain separate: cases 03 and 06 show that a
   plausible or correct-looking answer can still have an incomplete evidence chain.

## Targeted C3/C4 diagnostic follow-up

| Case | Diagnostic contrast | Result | Attribution supported by the contrast |
|---|---|---|---|
| 06 | C3 contextual table regions -> C4 normalized facts | C3 over-abstained; C4 produced exactly `6.01 hours` and cited pages 21 and 55 | The model can do the conversion, subtraction, and cross-page citation. The residual failure is associated with table perception, cross-region value association, or table-conditioned over-abstention rather than arithmetic inability. |
| 08 | C2 text-only pages -> C3 six gold regions | C3 correctly counted four house photographs and cited their four pages, but omitted chapter-boundary pages 30 and 40 | Pixels resolve the answer-level visual representation failure. Strict grounded correctness still fails because the evidence chain for “across the entire chapter” is incomplete. |
| 09 | C2 empty page text -> rotated C3 crop -> same crop upright | C2 abstained; rotated C3 read `#1` instead of `#11`; the upright version exactly returned `father of #11 and #12` | The missing text layer is a real adapter failure, and exact transcription is orientation-sensitive. A deterministic orientation intervention fixed this reviewed case. |

These are controlled case studies, not additional benchmark-rate estimates. In particular, the
successful orientation intervention on one crop does not establish a benchmark-wide effect.

## Frozen failure taxonomy after C3/C4

| Observed failure | Direct evidence | Smallest justified next intervention |
|---|---|---|
| Missing or wrong pages from BM25 | Cases 03, 04, 08, and 09 | Preserve BM25 v0; formulate a separate retrieval ablation only after choosing a single observed failure class. |
| Scanned page has no machine-readable text | Case 09 C2 versus visual C3 | Add a visual/OCR fallback decision at inference time; do not train OCR or a VLM. |
| Rotated small text is transcribed inaccurately | Case 09 rotated versus upright C3 | Deterministic orientation canonicalization before visual inference, with the unmodified crop retained for audit. |
| Flattened or multi-region tables do not reliably yield exact facts | Case 06 C3 failure versus C4 success | Test layout-preserving table serialization or deterministic row-column association; do not change the reasoning model first. |
| Correct answer has incomplete evidence chain | Cases 03 and 08 | Keep answer correctness separate from grounded correctness and add explicit required-chain coverage checks before reliability calibration. |
| Model abstains despite sufficient evidence | Case 06 contextual C3 | Treat as over-abstention, distinct from the appropriate C1/C2 abstentions; measure it explicitly in selective-answering evaluation. |

## Failure-driven next decision

The diagnostic adapter and selected C3/C4 contrasts are now working. No benchmark-wide
architecture change is justified by these targeted examples. The next step is an offline design
checkpoint, not another paid call:

1. Freeze BM25 v0 and the current reasoning prompt as comparison baselines.
2. Define answer correctness, required evidence-chain coverage, appropriate abstention, and
   over-abstention as separate evaluation outputs.
3. Select one minimal input-side ablation at a time. Orientation canonicalization is the smallest
   observed intervention; table-aware serialization is a separate, larger ablation.
4. Add C0 Closed-book before a formal pilot for contamination control.
5. Only after those definitions are frozen, design the calibration slice for Reliability /
   Selective Answering.

Do not yet add OCR/VLM training, agents, MCP, a frontend, or an unbounded retrieval stack. Dense
retrieval or reranking remains a hypothesis for a later, separately scoped retrieval ablation.

## Accounting and reproducibility

- Successful result files: 20
- Successful v1 calls with direct cost logs: 18
- Known v1 cost: **USD 0.082289**
- Legacy first-pair estimate from the earlier report: **USD 0.006293**
- Successful-call estimated total: **USD 0.088582**
- Additional failed `smoke_07` attempt: cost metadata unavailable in the historical runner
- Conservative failed-attempt ceiling using the same observed input size and the configured
  512-token output cap: approximately **USD 0.006924**
- Conservative combined estimate: **USD 0.095506**, below the approved USD 1.00 cap
- Successful-call tokens: 26,999 input; 1,906 output; 28,905 total

Targeted diagnostic follow-up (reported separately from the original approved smoke scope):

- Successful additional calls: 5
- Additional estimated cost: **USD 0.014206**
- Additional tokens: 3,350 input; 515 output; 3,865 total
- Successful-call cumulative estimate: **USD 0.102788**
- Conservative cumulative estimate including the historical failed-attempt ceiling:
  **USD 0.109712**
- Successful-call cumulative tokens: 30,349 input; 2,421 output; 32,770 total

The cost figures are estimates under the pinned pricing snapshot, not invoice totals. The complete
manual record is `experiments/day3_reasoning_smoke_manual_audit_v1.json`; raw immutable responses
are under `results/day3_reasoning_smoke/`, `results/day3_reasoning_smoke_v1/`, and the targeted
`results/day3_oracle_*` directories.
