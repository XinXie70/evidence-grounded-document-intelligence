# V2 Final Report: Search-and-Read Agent vs Fixed Retrieval Pipelines

**Status:** Final evaluation run once, 2026-10-25, against the frozen system (`git tag v2-freeze`)
**Question:** On text/table questions over long PDFs, is an agent that can search again and read more pages more accurate than a pipeline that retrieves once, and what does it cost?
**Answer:** Yes on multi-page questions: **72.4% vs 28.1% (B0) and 41.9% (B1)**. Almost all of the gain comes from reading the right pages, not from better reasoning. The agent is clearly **worse at abstaining** on unanswerable questions and costs 2-3.5x more per question.

## 1. Setup

| | |
|---|---|
| Data | DocScope documents the archived V2 never touched: 103 documents (`locked_test` minus 32 excluded), text/table questions only |
| Questions | **370**: 343 answerable (203 multi-page, 140 single-page) + 27 unanswerable from the same documents |
| Model | `gpt-5.6-terra`, `reasoning_effort=low`, same for all systems |
| Retrieval | V1 hybrid: BM25 + BGE-small + RRF (top 10 each, k=60), per document |
| B0 | retrieve once, read top 3 pages, one call |
| B1 | same, top 6 pages (separates "searches again" from "just reads more") |
| A (agent) | LangGraph loop; tools `search_document`, `read_pages`, `calculate` (numbers must be quoted from pages already read), `finish`; at most 8 tool calls, 30k cumulative input tokens, $0.10, 120 s |
| Judging | V1 frozen semantic and evidence-support judges (`locked_test_*_judge_v0`) |
| Primary metric | task accuracy: answerable questions need a judged-correct answer (abstaining is wrong); unanswerable questions are correct only if the system abstains; system failures count as wrong |
| Statistics | paired comparison on shared questions; bootstrap over **documents**, 10,000 resamples, percentile 95% interval |

Pre-registered primary comparison (`V2_PLAN.md` section 5): A minus B0 on multi-page questions, success if the interval's lower bound is above 0.

## 2. Results

| system | task acc | multi-page (203) | single-page (140) | unanswerable abstained (27) | grounded acc | coverage | $/question | s/question | tool calls | pages read |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **A** | **71.9%** | **72.4%** | **81.4%** | 18.5% | **64.6%** | 93.2% | 0.0191 | 9.1 | 4.0 | 3.4 |
| B1 | 53.5% | 41.9% | 71.4% | 48.1% | 48.6% | 73.5% | 0.0099 | 2.3 | - | 6.0 |
| B0 | 44.1% | 28.1% | 67.1% | 44.4% | 39.2% | 62.7% | 0.0055 | 2.1 | - | 3.0 |

`grounded acc` = task-correct and the cited pages support the answer.

Paired differences (95% interval, bootstrap over 103 documents):

| comparison | metric | difference | 95% CI |
|---|---|---:|---|
| **A - B0** | **multi-page task accuracy (primary)** | **+44.3 pp** | **[+36.3, +52.4]** |
| A - B1 | multi-page task accuracy | +30.5 pp | [+23.1, +38.2] |
| A - B0 | task accuracy (all) | +27.8 pp | [+21.6, +34.0] |
| A - B1 | task accuracy (all) | +18.4 pp | [+12.4, +24.4] |
| A - B0 | single-page task accuracy | +14.3 pp | [+6.7, +21.3] |
| A - B1 | single-page task accuracy | +10.0 pp | [+1.7, +17.5] |
| A - B0 | grounded accuracy | +25.4 pp | [+19.1, +31.6] |
| A - B1 | grounded accuracy | +15.9 pp | [+10.0, +21.7] |
| B1 - B0 | multi-page task accuracy | +13.8 pp | [+9.0, +19.0] |
| B1 - B0 | task accuracy (all) | +9.5 pp | [+5.4, +13.6] |

The primary hypothesis holds, and every interval in this table excludes 0. (B1 - B0 on single-page questions is not listed: +4.3 pp, [-3.0, +11.2], which includes 0.)

## 3. Where the gain comes from (post-hoc, not pre-registered)

| | agent | B1 | B0 |
|---|---:|---:|---:|
| answerable questions where every gold evidence page was read/retrieved | **281 / 343 (82%)** | 203 / 343 (59%) | 156 / 343 (45%) |
| task accuracy among those questions | 83.3% | 81.3% | 84.6% |

Given the right pages, all three systems are about equally accurate. The agent wins because it reads every needed page far more often (searching again, following the document's own references), not because it reasons better. Among questions where it missed a gold page the agent is correct 43.5% of the time.

Other post-hoc numbers:

- Answerable questions only: A 76.1%, B1 53.9%, B0 44.0% (A - B1 +22.2 pp, [+16.4, +28.0]).
- **Unanswerable questions: the agent abstains correctly on 5 of 27, B1 on 13, B0 on 12** (A - B1 -29.6 pp, [-43.6, -13.6]). It finds something plausible and answers. Labels on these questions are noisy, so treat this as a real weakness of unknown size, not a precise rate.
- Wrong answers that were given: A 84, B1 87, B0 81. The agent's gain is fewer wrong abstentions on answerable questions (20 vs 84 and 126), not fewer wrong answers.
- Agent behaviour: 328 finished on their own, 35 hit the tool limit, 6 the token limit, 1 failed. Tool use: 785 searches, 611 page reads, 88 calculations (13 rejected for a quote not found on a page read). Only 4 repeated searches.
- Cost per correct answer (answering only): A $0.027, B1 $0.019, B0 $0.013.

## 4. Deviations and incidents

1. **Agent run interrupted once.** An `APIConnectionError` at model call 4 of one question (`...6a555f41...::q5`, after 197 questions) killed the process because the runner did not catch Agent exceptions, although it already did for B0/B1. That question was recorded as a failed question (counted wrong, its $0.0097 of spend counted) and not retried; the remaining 173 questions were run in a second invocation. `run.py` was then changed to record any Agent exception as a failed question. Between the freeze tag and the end of the evaluation the only changed file under `src/` and `configs/` is `src/egdi/v2/eval/run.py` (sha256 `c02014ca...`); the agent, tools, prompts, index, baselines and judges are byte-identical to `data/fixtures/v2_freeze_manifest.json`.
2. **One B1 question failed** (model output could not be parsed); counted wrong, not retried. B0 had no failures.
3. Judging was run as three parallel processes, one per system; this does not affect results.
4. Seven agent questions exceeded the $0.10 per-question limit (maximum $0.131) because the forced final turn after a limit is not itself capped.
5. The dry run that counted the final questions read the final labels after the freeze; only counts and a hash of the question ids are stored (`data/fixtures/v2_final_selection.json`).

## 5. Limitations

- **One run per system.** The intervals reflect which documents were sampled, not run-to-run model variance, which was not measured.
- **Not a clean unseen set.** V1 was evaluated on this split; the archived V2 touched 32 other documents, which were excluded. The 103 documents were never used to develop V2.
- **Unequal tuning.** The agent's prompt and tools had two rounds of development-time fixes (visible tool budget, free repeated searches, tool limit 6 to 8, query-focused snippets). B0 and B1 prompts were not tuned. A tuned baseline might narrow the gap.
- **Judge.** The judge model is the same model as the systems. Agreement with a 30-case check was 29/30, but that check was done by the assistant that built the system, not an independent human.
- **Abstention.** Only 27 unanswerable questions, with noisy labels.
- **Scope.** English documents, text and tables only (no charts, images or OCR); single model.
- **Held-out check before freezing:** on a 50-question validation sample the agent scored 80.0% vs 56.0% (B1) and 52.0% (B0); on the tuning sample it was level with B1 overall (77.1% vs 78.6%). The final result is consistent with the validation result.

## 6. Cost

| | USD |
|---|---:|
| B0 / B1 / Agent answering (370 questions each) | 2.04 / 3.66 / 7.08 |
| Judging (B0 / B1 / Agent) | 0.69 / 0.78 / 1.35 |
| **Final evaluation total** | **15.60** (cap 25) |
| Development and validation | about 7.7 |

## 7. Reproduce

Code is frozen at tag `v2-freeze`; file hashes are in `data/fixtures/v2_freeze_manifest.json`. Reading the final labels needs the V1 locked-test acknowledgement.

```bash
PYTHONPATH=src python -m egdi.v2.eval.run --system A --split final --max-usd 10.5 --execute
PYTHONPATH=src python -m egdi.v2.eval.judge --split final --input A=results/v2_final/final_all_A.jsonl \
    --output results/v2_final_judge/judged_A.jsonl --max-usd 2.2 --execute
PYTHONPATH=src python -m egdi.v2.eval.report --judged results/v2_final_judge/final_judged.jsonl
```

Raw per-question results, judgments and the request log are under `results/v2_final/` and `results/v2_final_judge/` (not tracked by git).
