# Day 4 Reliability Outcome Map v0

## What the map does

The frozen Reliability taxonomy contains seven possible outcomes. Existing manually audited
experiments provide a concrete representative for six. This is coverage of failure modes, not a
frequency or performance estimate, because the experiments are stratified and include targeted
diagnostic interventions.

| Outcome | Observed? | Representative | Meaning |
|---|---:|---|---|
| Grounded success | yes | smoke_01 C1 | correct answer and complete support |
| Correct answer, incomplete grounding | yes | smoke_03 C2 | answer correct but page 31 omitted |
| Incorrect answer | yes | smoke_09 rotated C3 | read `#1` instead of `#11` |
| Appropriate abstention | yes | smoke_03 C1 | required page 40 absent |
| Over-abstention | yes | smoke_06 contextual C3 | both exact facts supplied, but model abstained |
| Correct abstention | yes | smoke_10 C1 | unanswerable question resisted tempting context |
| False answer on unanswerable | no | none | no observed case yet |

## What this changes for the next pilot

1. Answer correctness and complete grounding must remain separate labels.
2. Every answerable abstention requires a post-hoc evidence-sufficiency audit; response status
   alone cannot distinguish appropriate from excessive abstention.
3. The pilot needs multiple benchmark-unanswerable questions. One correct `smoke_10` abstention
   cannot establish a benchmark-wide zero false-answer rate.
4. The pilot also needs sufficient-context answerable cases to measure over-abstention rather than
   rewarding a policy that refuses everything.
5. Diagnostic variants of one question must not be counted as independent population samples.

No inference threshold is selected by this map.
