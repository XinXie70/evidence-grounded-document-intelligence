# R2 Explicit-Clause Multi-Hop Retrieval Ablation v0

## Observed failure

Groundwater q4 asks for a two-stage evidence chain: compare `TPH as Gasoline`
values across laboratory tables, identify the monitoring well, then locate that
well on a site map and report the nearest street.

Under the orientation-recovered R2 candidate, full-query BM25 ranked physical
pages 12, 13, and 19 at 17, 16, and 10 respectively. The three centered windows
selected the map page 19 but omitted table pages 12 and 13.

## Diagnostic observation

The question contains an explicit em dash separating the table comparison from
the map lookup. Splitting only on that visible delimiter changed the ranks:

| Page | Role | Full query rank | Relevant clause rank |
|---:|---|---:|---:|
| 12 | laboratory table | 17 | 11 |
| 13 | laboratory table | 16 | 9 |
| 19 | site map | 10 | 5 |

No semantic parser or LLM generated these clauses.

## Frozen v0 intervention

1. Select three centered, non-overlapping windows from the full question.
2. If and only if the literal em dash is present, run the same retrieval for each
   explicit clause.
3. Add at most one clause window that is fully non-overlapping with all selected
   full-query pages.
4. Use at most 12 physical pages.

All window selection is complete before benchmark evidence pages are read.

## Result on the nine-question R2 tune inventory

| Method | Minimum pages | Maximum pages | Mean pages | Any evidence | Complete evidence | Macro recall |
|---|---:|---:|---:|---:|---:|---:|
| Orientation recovery + centered windows | 9 | 9 | 9.00 | 9/9 | 8/9 | 92.59% |
| + explicit-clause novel window | 9 | 12 | 9.33 | **9/9** | **9/9** | **100.00%** |

Only groundwater q4 changed. Its full-query windows selected pages 3--5, 6--8,
and 18--20. The first table clause contributed the fully novel pages 12--14,
thereby covering all gold evidence pages 12, 13, and 19. The other eight questions
remained at nine pages.

## Interpretation and limitation

The result supports a bounded multi-query retrieval mechanism for explicitly
segmented multi-hop questions. It does not establish general multi-hop retrieval:
only one of the nine R2 tune questions contains the frozen separator, and the rule
was designed after observing this failure. Do not report 100% as held-out
performance or broaden clause inference without new failures.

The next step is a single grounded-reasoning smoke test on q4 using these 12
layout-preserved OCR pages. That test will determine whether complete page recall
is sufficient for the answer model to execute the table-to-map reasoning chain.

## Grounded-reasoning smoke result

The frozen 12-page input was sent once to `gpt-5.6-terra` with low reasoning
effort, no retries, and the same grounded-answer contract used by prior R2
experiments. The model answered:

> MW3 consistently had the highest TPH as gasoline concentrations, and it is
> located closest to Davis Street.

The benchmark answer is `Davis Street`. The response cited physical pages 12,
13, and 19, exactly matching the full gold evidence chain. Validation passed,
the request used 5,857 input tokens and 95 output tokens, and the actual estimated
cost was USD 0.015781 under the USD 1.00 hard cap.

This result supports the causal diagnosis: once retrieval supplied both laboratory
tables and the map, the unchanged reasoning model completed the cross-page chain.
The earlier q4 failure was a retrieval-coverage failure, not evidence that the
reasoning model required training or replacement.
