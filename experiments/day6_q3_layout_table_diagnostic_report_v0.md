# Day 6 q3 Layout-Aware Table Diagnostic v0

## Purpose

Test whether the two facts needed by q3 can be recovered from PDF word positions
after fixed token windows failed to reduce the evidence. The benchmark pages 21
and 55 are used only to isolate within-page structure. No paid API request is made.

## Method

The original PDF pages were visually inspected and read with pdfplumber 0.11.9.
The diagnostic used text alignment for both vertical and horizontal table
boundaries. This mode groups words by their x/y positions rather than flattening
the page into reading-order text.

## Result

The page-21 table was not detected by the default line-based detector, but text
alignment recovered one table and preserved:

```text
unit: hours
row: Personal care
column: Males
value: 10.8
```

The page-55 text-alignment table preserved the multi-level column relationship:

```text
unit: minutes
row: Total
column: Females -> Total
value: 287.4
```

The evidence supports `10.8 - (287.4 / 60) = 6.01 hours`.

## Interpretation

The original PDF contains enough layout information to recover the exact facts.
The prior failure was caused by flattening and token chunking, not by missing page
evidence. A layout-aware table route is therefore justified for further testing.

This is not yet a general solution. Table detection depends on extraction settings,
and the experiment used known benchmark pages. The next bounded step is a
question-guided selector that receives a recovered table and returns only the
relevant headers, row, unit, value, and source page without using the gold answer.

