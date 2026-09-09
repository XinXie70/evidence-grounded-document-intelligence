# Day 6 q3 Within-Page Localization Diagnostic v0

## Question

According to the weekday main-activity table by sex, how many more hours do
males spend on personal care than females spend on housework and family care?

The benchmark evidence pages are physical PDF pages 21 and 55. This diagnostic
uses those gold pages deliberately to isolate within-page localization from page
retrieval. It makes no paid API request and does not evaluate answer generation.

## Tested rule

The frozen 256-token, zero-overlap BGE chunks were reused. On each supplied page,
the highest-scoring dense chunk was selected. A bounded expansion then retained
up to two preceding chunks and one following chunk on the same physical page.

## Observations

- Page 21 contains one chunk. Its best chunk contains the male personal-care
  value `10.8` and the table headers.
- Page 55 contains three chunks. Dense selects chunk 2 because it contains the
  most semantically similar table/chart labels.
- Best-chunk-only selection on page 55 omits the required value `287.4`.
- Expanding backward by two chunks retains chunks 0, 1, and 2. This recovers the
  table header, the female-total column relationship, and `287.4`.
- Because all three page-55 chunks are retained, the expanded window is
  effectively the full page. Tokenizer decoding also adds spaces around decimal
  punctuation, so character count is not a fair compression gain and is slightly
  larger than the original text.

## Decision

Do not promote the fixed "best chunk plus two preceding chunks" rule. It repairs
the observed chunk-boundary failure but does not reduce the q3 evidence package.
The next experiment must be table-structure-aware or fact-oriented: it should
retain the table title/header, the relevant row or total, the units, and the
source page while excluding unrelated rows. That next method remains unimplemented.

