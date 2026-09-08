# Day 6 R1 Residual Failure Taxonomy v0

## Outcome

The strongest neighbour-supplement policy still leaves seven incomplete R1
tune questions. They are not one homogeneous failure and should not be addressed
by indefinitely enlarging a universal page radius.

| Failure type | Count | Required behaviour |
|---|---:|---|
| Dispersed multi-hop composition | 3 | Retrieve two semantically distinct sources before subtraction, intersection, or entity mapping. |
| Section or repeated-table coverage | 3 | Cover a named chapter or a repeated sequence of tables across several pages. |
| Missed document-global route | 1 | Inspect the complete document or abstain; local Top-K cannot prove an exhaustive count. |

## Concrete interpretation

### Dispersed multi-hop

One question needs a male personal-care value and a female housework value from
pages 21 and 55. Another intersects stone types in an image collection with a
mineral-resources table on pages 24 and 40. The third first identifies an entity
from a risk-management description and then maps it to a fee table on pages 28
and 33. Fixed neighbour expansion cannot reliably connect these distant sources.

### Section or repeated-table coverage

These questions compare several PLC-series tables, enumerate industry sectors
in a multi-page holdings table, or count diagram sections across a named wiring
chapter. The evidence forms a range or repeated sequence rather than one isolated
page.

### Missed document-global route

One question explicitly says `across the document`. Router v0 recognizes
`across the entire document` and similar forms but misses this shorter wording.
Because the question asks for the number of separate locations, a local R1
candidate set cannot certify that omitted pages contain no additional instance.

## Next changes allowed by the evidence

1. Add the observed `across the document` phrase to a versioned R3 routing
   wrapper, preserving the already frozen R2 v2 files.
2. Test one bounded section-span policy for the three range-based failures.
3. Compare a clause-aware or dense retriever only for the dispersed multi-hop
   hypothesis; this is now failure-driven rather than speculative.

No gold answer text, calibration label, locked-test content, or paid API request
was used.
