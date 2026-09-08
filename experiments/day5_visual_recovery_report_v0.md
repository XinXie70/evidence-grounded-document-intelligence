# Day 5 Visual Evidence Recovery Pilot Report v0

## 1. Question addressed

This pilot asks whether a bounded visual evidence input can recover answerable questions that fail
under the text-only Oracle Page condition. It does not test a general visual retrieval system and
does not use the locked test split.

The single changed variable in the eligible comparisons is the evidence representation:

- **C2 Oracle Page:** native text extracted from the correct benchmark evidence page;
- **C3 Oracle Region/Image:** a manually verified image of the same evidence area or page.

The question, model, response contract, evidence page identity, reasoning effort, and zero-retry
policy remain fixed within each comparison.

## 2. Results

| Case | Observed text-only failure | C2 result | C3 visual result | Eligible comparison? | Interpretation |
|---|---|---|---|---|---|
| `pilot_06` | Chart labels and values lost their spatial association in linearized text | Incorrect: `30%` | Correct: `20%` | Yes | Visual layout recovered the correct series-to-value mapping |
| `pilot_16` | Both evidence pages had empty native text | Abstained | Correct: `1.05 feet` | Yes | Images recovered two measurements and cross-page subtraction |
| `pilot_17` | The evidence page had empty native text and list structure was unavailable | Abstained | Correct: `5` | Yes | Images recovered list-item boundaries and supported counting |
| `pilot_18` | Linearized text did not preserve stacked-chart boundaries | Incorrect: `12` | Abstained | No | The question was document-global, but C3 supplied only 6 of 42 pages, so absence on omitted pages could not be established |

Among the three eligible, evidence-complete comparisons, C3 recovered the benchmark-supported
answer in **3/3 cases**. This is a small diagnostic sample, not a population-level accuracy claim.

## 3. Failure attribution

The three eligible recoveries represent two concrete upstream failure types:

1. **Missing text layer:** evidence exists visually, but the PDF text extractor returns no usable
   text (`pilot_16`, `pilot_17`).
2. **Lost two-dimensional structure:** words and numbers are extracted, but their chart
   relationships are destroyed by linearization (`pilot_06`).

These failures occur in the evidence representation presented to the reasoning model. They are not
evidence that arithmetic training or language-model fine-tuning is required.

`pilot_18` exposes a different limitation: an exhaustive document-level question requires both
positive evidence and document-wide negative coverage. Supplying only benchmark-positive pages is
not a valid Oracle condition for proving a whole-document count. Its C3 abstention is therefore a
reliability success under incomplete evidence, not a visual-perception failure.

## 4. Decision

**Keep a bounded visual evidence path as a justified project component.**

The decision is supported only for pages or regions where:

- native text is empty or unusable; or
- the answer depends on visual structure that linear text does not preserve.

Do not yet claim that every PDF page should be sent to a visual model. Do not use `pilot_18` as
evidence of visual counting accuracy. A document-complete and non-leaking design would be required
before rerunning that global-count case.

## 5. Cost and execution audit

The four C3 diagnostic requests recorded a combined estimated cost of **USD 0.045973**:

- `pilot_06`: USD 0.001844;
- `pilot_16`: USD 0.005343;
- `pilot_17`: USD 0.001562;
- `pilot_18`: USD 0.037224.

`pilot_18` exceeded its then-approved USD 0.03 request cap by USD 0.007224 because the old runner
checked cost only after execution. The incident is retained in the experiment record. The runner
now performs a multimodal input-token preflight and blocks answer generation when the conservative
maximum exceeds the active USD 1.00 single-request cap. The full local test suite passes.

## 6. Next bounded step

Translate the observed failure types into a simple routing hypothesis before adding more model
calls:

> Use native text by default; consider a page-image fallback only when the page text is missing or
> when the question/evidence requires two-dimensional visual structure.

This hypothesis must next be expressed as observable, testable routing signals. It is not yet a
finished production policy.
