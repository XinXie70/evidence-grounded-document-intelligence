# Day 6 q3 Question-Guided Layout Fact Selection v0

## Objective

Test whether a deterministic, local selector can convert position-aware PDF table
content into the two facts required by q3. The diagnostic uses the benchmark pages
21 and 55 to isolate fact selection from page retrieval, but it does not read the
gold answer or the manually prepared Oracle Facts input.

## Selection process

1. Read word text and x/y coordinates from the original PDF pages.
2. Recover the first hours/minutes table section, population headers, optional
   subgroup headers, row labels, units, and numeric cells.
3. Split the explicit comparison question at `than`.
4. Match each side to population, activity, table scope, row, and column.
5. When two measurements are numerically consistent after unit conversion,
   prefer the one with finer measurement resolution.

The two pages produced 45 candidate cell facts before question-guided selection.

## Selected evidence

```text
page 21
table: Table 5. Distribution of average time spent on main activity per weekday by sex
unit: hours
row: Personal care
column: Male
value: 10.8

page 55
table: Table 40. Distribution of average time spent on housework and family care per weekday by sex and marital status
unit: minutes
row: Total
column: Female -> Total
value: 287.4
```

The page-21 summary also exposes `4.8 hours` for female housework and family care.
After conversion, `287.4 minutes = 4.79 hours`, which is consistent with the
rounded summary. The selector keeps `287.4 minutes` because its resolution is
finer; it does not use the benchmark answer to make this decision.

## Decision

The bounded q3 diagnostic succeeds and justifies one paid reasoning smoke test
with these automatically selected facts. It does not establish general table
performance: extraction has been tested on one question and known evidence pages,
and the current selector supports only an explicit `than` comparison with
hours/minutes tables. Do not promote it to the formal pipeline before broader
development-tune testing.

