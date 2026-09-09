# Day 6 product-depth less-than comparison v0

## Question

How many millimetres less deep is the digital time-clock module with four front
buttons than the 5A unboxed power-supply unit?

## Label-free evidence chain

Hybrid RRF Top 10 contains all pages needed to build two product-specific chains:

- page 12 identifies the four-button digital time clock as `Art.701T`;
- page 14 contains `Art.701T Dimensions` and gives Depth `(D)` as 30 mm;
- page 10 identifies `UBPSU5.0` as the 5A unboxed PSU and starts its Dimensions
  section; and
- page 11 continues that section and gives Depth `(D)` as 40 mm.

The selector requires a unique description-to-product identity, an explicit
product Dimensions anchor, and an L/W/D specification. It rejects incomplete or
ambiguous chains instead of guessing from isolated numbers.

## Reliability result

The ordered calculation is `30 - 40 = -10`, so the expected answer magnitude is
10 mm and the expected direction is `less`/`fewer`.

- `10 millimeters less`: accepted;
- `10 millimeters more`: rejected for comparative polarity mismatch.

The first audit serialized integral Decimals as scientific notation. That v0 is
retained as provenance. The formatter was corrected and tested; v1 records plain
values `30`, `40`, `-10`, and `10`.

## Post-prediction score

After freezing the prediction, the development benchmark was opened:

- benchmark answer: `10mm`;
- normalized numeric-and-unit match: pass; and
- selected pages 10, 11, 12, 14 versus benchmark pages 10, 11, 12, 14: complete
  match.

This is a narrow product-identity-to-specification selector, not a general manual
understanding system. Paid API cost: `$0`.
