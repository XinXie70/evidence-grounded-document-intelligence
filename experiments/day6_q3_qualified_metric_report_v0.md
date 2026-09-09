# Day 6 qualified cross-page text metric comparison v0

## Question

How many million bales higher are China's projected ending stocks at the end of the
projection period than India's projected average annual cotton exports over the
next ten years?

## Observed ambiguity

The retrieved pages contain several plausible India values:

- 2.6 million bales: average cotton exports over the next ten years;
- 3.8 million bales: cotton exports at the end of the period; and
- 1.2 million bales: average cotton imports.

Entity and metric words alone are insufficient. The selector must also preserve
the requested statistic and time scope.

## Label-free selection

The selector binds four fields before accepting a number: entity, metric, statistic,
and time qualifier.

- China + cotton ending stocks + end value + end of projection period, page 11:
  30.4 million bales.
- India + cotton exports + average + next ten years, page 12: 2.6 million bales.

The page 19 end-of-period export value and average import value are retained as
retrieval candidates but rejected as fact matches.

## Reliability result

The ordered calculation is `30.4 - 2.6 = 27.8`, direction `higher`.

- `27.8 million bales higher`: accepted;
- `27.8 million bales lower`: rejected for comparative polarity mismatch.

## Post-prediction score

After freezing the prediction, the development benchmark was opened:

- benchmark answer: 27.8 million bales;
- value and unit match: pass; and
- selected pages 11 and 12 versus benchmark pages 11 and 12: complete match.

This is a narrow qualifier-aware selector for the observed cotton metric wording,
not a general information-extraction model. Paid API cost: `$0`.
