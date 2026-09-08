# Day 6 R1 Numbered Section-Span Recovery v0

## Outcome

A narrow, deterministic section-span rule recovered both tune questions whose
required evidence covered a numbered manual section.

The rule triggers only when the question explicitly contains `chapter` or
`across all listed`. It then finds page-number-anchored top-level section
headings, requires two meaningful title words to overlap the question, and
extends the candidate through the page before the next top-level heading.

| Question structure | Matched section | Selected range | Result |
|---|---|---|---|
| Compare supported-device tables across all listed PLC series | `6 Supported Device` | 46-51 | Complete evidence recovered |
| Count cable-diagram sections in the chapter | `5 Cable Diagram` | 25-35 | Complete evidence recovered |

Across the 63 questions that remain in R1 after router v1 moves document-global
questions to R3:

- Complete-evidence Recall rose from 57/63 (90.5%) to 59/63 (93.7%);
- mean candidate size became 15.9 pages;
- maximum candidate size was 23 pages;
- no question regressed;
- only two questions triggered the section rule.

## Remaining boundary

Four questions remain incomplete. Three require dispersed multi-hop retrieval.
The fourth describes an investment-holdings table, while the actual page heading
is `Schedule of Investments`; a lexical section matcher cannot safely infer that
semantic alias. This residual now justifies testing an off-the-shelf dense
retriever rather than hard-coding a one-document synonym.

No calibration label, locked-test content, or paid API request was used.
