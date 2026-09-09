# Day 6 Q1 cross-page list-count selection v1

## Question

Compare the numbered practices in the article about building resilience with the
numbered mental-health competencies in the article about keys to resilience.

## Retrieval diagnosis

- Hybrid RRF Top 10 found physical pages 15 and 19 but missed page 16.
- Deterministic radius-1 adjacent-page expansion recovered all three relevant
  pages, but expanded the candidate pool from 10 to 25 pages.
- The expanded pool is candidate generation only; it is not sent wholesale to a
  reasoning model.

## v0 observed failure

The first selector used topic overlap plus a contiguous numbered sequence. It
mistook the numbered bibliography on page 38 for a six-step resilience list.
This failure was retained in `day6_q1_list_count_selection_v0.json`.

## Failure-driven v1 change

Numbered markers after an explicit `References` heading are excluded from
instructional-list candidates. This rule follows the observed document structure
and does not depend on the benchmark answer.

## v1 selected facts

- `building resilience`: pages 15-16, numbered items 1-7, count 7.
- `keys to resilience`: page 19, `Step 1`-`Step 2`, count 2.

The selector input contains the question and label-free retrieval candidates. It
does not contain the benchmark answer or gold evidence-page labels.

## Post-prediction benchmark score

After the prediction and consistency result were frozen, the development label was
opened for scoring:

- predicted signed difference: 5 more steps;
- benchmark answer: 5;
- answer exact match: pass; and
- selected pages 15, 16, 19 versus benchmark pages 15, 16, 19: complete match.

## Scope and decision

This is a narrow deterministic selector for a question that explicitly describes
two articles with numbered lists. It is evidence that list-aware, cross-page
localization can recover this observed failure class; it is not yet a general list
understanding system. The next stage is deterministic comparison and polarity
checking before any optional LLM answer generation.

Paid API cost: `$0`.
