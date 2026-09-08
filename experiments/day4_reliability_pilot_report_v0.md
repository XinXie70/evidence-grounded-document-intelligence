# Day 4 Reliability Pilot v0 Report

## Scope

This is a targeted 24-question `development_tune` pilot, not a population estimate and not a
locked-test result. The pilot contains 18 benchmark-answerable and 6 benchmark-unanswerable
questions from 24 distinct documents. All 72 logical C0/C1/C2 outputs were manually audited and
explicitly confirmed by the user.

## Conditions

- **C0 Closed Book:** question only, no document evidence.
- **C1 Real Retrieval:** question plus the frozen BM25 Top-3 pages.
- **C2 Oracle Page:** question plus the benchmark evidence pages; unanswerable questions receive
  empty context.

## Primary results

| Metric | C0 | C1 Real Retrieval | C2 Oracle Page |
|---|---:|---:|---:|
| Coverage | 0.0% | 50.0% | 66.7% |
| Benchmark task accuracy | 25.0% | 45.8% | 83.3% |
| Strict grounded task accuracy | 25.0% | 33.3% | 70.8% |
| Selective risk | null | 33.3% | 12.5% |
| Grounded selective risk | null | 58.3% | 31.3% |
| Contextual reliability accuracy | 100.0% | 70.8% | 79.2% |
| Unanswerable false-answer rate | 0.0% | 50.0% | 0.0% |
| Response-contract validity | 100.0% | 91.7% | 100.0% |

C0's 100% contextual reliability reflects universal abstention when no evidence was supplied; it
is not useful task performance. Its 25% benchmark accuracy comes only from correctly abstaining on
the six unanswerable questions.

## Outcome counts

### C1 Real Retrieval

- 5 grounded successes;
- 3 correct answers with incomplete grounding;
- 1 incorrect answer on an answerable question;
- 9 appropriate abstentions under insufficient retrieved context;
- 3 correct abstentions on unanswerable questions;
- 3 false answers on unanswerable questions.

Two C1 abstentions (`pilot_19` and `pilot_23`) were semantically correct but violated the response
contract by returning citations with `status=insufficient_evidence`. Contract-adjusted benchmark
task accuracy is therefore 37.5%, while the frozen semantic task accuracy is 45.8%.

### C2 Oracle Page

- 11 grounded successes;
- 3 correct answers with incomplete grounding;
- 2 incorrect answers;
- 2 appropriate abstentions because the correct pages had empty extracted text;
- 6 correct abstentions on unanswerable questions.

## Failure-grounded interpretation

Moving from C1 to C2 increased benchmark task accuracy and strict grounded task accuracy by 37.5
percentage points. This is strong pilot evidence that page retrieval is a major bottleneck in the
current system.

C2 did not reach the ceiling:

- `pilot_16` and `pilot_17` had correct Oracle page IDs but empty pypdf text, causing appropriate
  abstention under the text-only adapter;
- `pilot_06` selected the wrong percentage from a chart whose extracted text lost spatial
  alignment;
- `pilot_18` counted 12 rather than 13 stacked bar charts because linear text did not preserve
  chart boundaries;
- `pilot_02`, `pilot_05`, and `pilot_11` answered correctly but omitted necessary citations from
  their multi-page evidence chains.

The C1 unanswerable false-answer rate of 50% shows that strong topical overlap can induce unsupported
answers. `pilot_24`, the only high-BM25-signal unanswerable item, produced a confident false answer.
This reinforces the earlier finding that raw BM25 score or margin is not a sufficient reliability
signal.

## Next protocol decision

The observed failures support two bounded follow-ups before any locked-test use:

1. add a visual/page-image evidence adapter for the confirmed chart and missing-text cases;
2. evaluate a separately validated answer/grounding verifier before choosing selective-answering
   thresholds on `development_calibration`.

No calibration threshold is selected by this pilot, and no result here authorizes locked-test
access.
