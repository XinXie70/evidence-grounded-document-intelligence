# Day 6 directional-comparison candidate audit v0

## Scope

This audit covers the eight answerable `development_tune` questions in the bounded
directional wording family that remain after the two strict `more ... than`
questions were validated. Calibration and locked test data remain untouched.

## Retrieval result

Hybrid RRF Top 10 retrieves every benchmark evidence page for all eight questions.
Complete evidence recall is therefore 8/8 (100%) on this diagnostic subset.

This does not mean the questions are answered. It means the observed bottleneck has
moved from page retrieval to evidence interpretation and fact extraction.

## Document structures

| Structure | Questions |
|---|---:|
| Table or table plus text | 4 |
| Chart | 2 |
| Text or list | 2 |

## Next bounded experiment

Use the Fall 2008 part-time female-versus-male enrolment question as the next
representative. Its evidence is table-based and RRF already finds both pages 5 and
7. It is the closest safe test of whether the existing question-guided table path
can extend from strict `more ... than` wording to directional `compared to`
wording.

Benchmark labels in this audit are used only for post-retrieval measurement and
structure classification. They must not enter the fact selector or reasoning
input.

Paid API cost: `$0`.
