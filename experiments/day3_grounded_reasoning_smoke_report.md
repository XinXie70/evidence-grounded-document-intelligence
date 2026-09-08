# Day 3 Grounded-Reasoning Paired Smoke Report

## 1. Scope

This report records the first paired grounded-reasoning smoke item. It compares the same
answerable `development_tune` question under:

- **C1 Real Retrieval:** frozen BM25 Top-3 physical pages;
- **C2 Oracle Page:** the full benchmark-annotated evidence page.

This is one question, not the protocol's complete 10-question smoke test. It verifies the API
path and supports manual inspection, but it does not estimate general answer accuracy or the
real-retrieval/Oracle gap.

No benchmark final answer was included in either model input. Both conditions used the same
reasoning configuration and answer contract.

## 2. Question and reference data

- Question ID: `urnuuid0812e9ac-6f30-4624-9c78-6f4176467918::q2`
- Document ID: `urnuuid0812e9ac-6f30-4624-9c78-6f4176467918`
- Question: `What specific age threshold does the document define for distinguishing between a
  child and an adult research participant under POPIA?`
- Benchmark answer: `18 years old`
- Benchmark evidence page: physical PDF page 12
- Benchmark answerability: `true`

Page 12 states that POPIA defines a child as a person under age 18 who is not legally competent
to act or decide without assistance from a competent person.

## 3. Frozen call configuration

- Provider: OpenAI
- Endpoint: Responses API
- Model ID: `gpt-5.6-terra`
- Reasoning effort: `low`
- Maximum output tokens: `512`
- Structured output: strict JSON schema
- Response storage: disabled
- Configuration SHA-256:
  `588437edd7c82dd879a7c071bc48edfb248231e65d9f953b227acdc9eb492b22`

The configured model ID is a smoke candidate, not yet a dated formal model snapshot. A formal
pilot must either pin an available snapshot or explicitly record the alias-stability limitation.

## 4. Paired results

| Field | C2 Oracle Page | C1 Real Retrieval |
|---|---|---|
| Supplied physical pages | 12 | 12, 18, 47 |
| Answer status | `answerable` | `answerable` |
| Core answer | 18 years old | 18 years old |
| Cited pages | 12 | 12, 47 |
| Contract validation | valid | valid |
| Input tokens | 562 | 1,324 |
| Cache-write tokens | 0 | 1,321 |
| Cached-input tokens | 0 | 0 |
| Output tokens | 76 | 79 |
| Total tokens | 638 | 1,403 |
| Response ID | `resp_0d712665747ac216016a97b57838b887d0b4cdc14491adfded` | `resp_0bd941520c0da1f9016a97b62d8d1887d0a0d5b506679a8efd` |

### C2 Oracle Page

The answer correctly identifies 18 as the threshold and cites only page 12. It matches the
benchmark answer and is supported by the supplied page.

- Input SHA-256:
  `a9093e28b7e1e184365f5f8ace5e5492c12ce25d1c1d2e3539ec7c434b19512b`
- Request SHA-256:
  `7df464f393fed83cf70cc078d3c4637b9b1c538626465f201c553583ce458f2c`

Manual verdict: answer correct, answerable decision correct, and citation supported.

### C1 Real Retrieval

The answer again correctly identifies 18 as the threshold. The additional context causes the
answer to mention exceptions for emancipated minors or minors empowered by legislation, citing
pages 12 and 47. Page 47 genuinely states both the age definition and these exceptions. Page 18
is supplied but not cited.

- Input SHA-256:
  `3702c2409cef7d953e4d15a9be4fe46a4d83429e55f937be1ff0c6afd65696b8`
- Request SHA-256:
  `63ba23f68ae20b2ecd073d92b8f87e306e08e23145ec0e9635053f17b487219e`

Manual verdict: answer correct, answerable decision correct, and both citations supported. The
answer is more expansive than the question requires, but the added claim is grounded.

## 5. Evidence-annotation observation

The benchmark annotates page 12 as the gold evidence page, while retrieved page 47 independently
supports the threshold and the model's additional exception clause. A strict gold-page-only
citation metric could treat page 47 as an extra citation even though it is semantically valid.

For this item, page 47 is therefore a candidate **alternative valid evidence** page, not an
unsupported citation. This agrees with the protocol requirement to manually inspect alternative
evidence and possible annotation incompleteness before assigning a failure label.

No benchmark annotation is changed by this observation. It remains an audit note.

## 6. Cost estimate

Pricing snapshot date: 2026-09-02. The public GPT-5.6 Terra page listed USD 2.00 per million
uncached input tokens, USD 0.20 per million cached input tokens, USD 12.00 per million output
tokens, and cache writes at 1.25 times the uncached input rate.

| Condition | Estimated input cost | Estimated output cost | Estimated total |
|---|---:|---:|---:|
| C2 Oracle Page | $0.001124 | $0.000912 | $0.002036 |
| C1 Real Retrieval | $0.003309 | $0.000948 | $0.004257 |
| **Pair** | **$0.004433** | **$0.001860** | **$0.006293** |

These are estimates from logged token counts and the pricing snapshot, not an invoice total.

## 7. Integration observations

Before the successful calls, the live API rejected the initial strict response schema because
`uniqueItems` is not permitted in that structured-output context. The unsupported schema keyword
was removed, while duplicate citations remain rejected by local post-response validation. All 54
local tests passed after the change.

The rejected schema request did not produce a model response and is not counted as an experiment
result.

## 8. Logging gaps discovered by the smoke call

The immutable result files record question and document IDs, condition, model ID, response ID,
tokens, validation, input/config/request hashes, and context page IDs. They do not yet record:

- call timestamp;
- wall-clock latency;
- SDK retry count;
- provider and endpoint as explicit result fields;
- estimated cost and pricing-snapshot identifier;
- a separate terminal status for rejected or failed calls.

These omissions prevent the present runner from satisfying every call-log field frozen in the
evaluation protocol. They must be corrected before the remaining smoke calls or any pilot.

### Resolution after the first pair

The first pair remains immutable under `reasoning_smoke_v0.json`; its configuration SHA-256 was
rechecked after the logging change and still matches both saved results. A new
`reasoning_smoke_v1.json` supersedes v0 for future calls and adds:

- an explicit experiment ID, provider, and Responses API endpoint;
- UTC request time and measured wall-clock latency;
- `max_retries = 0`, making the recorded retry count exactly observable;
- success/error terminal status, with failed attempts written to separate immutable metadata
  files without occupying the intended successful-result path;
- a versioned pricing snapshot, its checksum, and an automatic token-category cost estimate;
- a prompt hash and physical-page context IDs matching the frozen call-log schema.

The v1 dry runs for both paired inputs sent no paid request and wrote no output. All 58 local tests
passed after the logging change.

## 9. Decision and next step

This pair verifies the smallest successful C1/C2 answer-generation path. It does not justify a
retrieval, prompt, model, or architecture change.

Next:

1. define the remaining stratified questions needed to reach the 10-question smoke gate;
2. estimate and explicitly cap the remaining smoke cost before further paid calls;
3. generate and locally validate all matched inputs before any additional API execution;
4. run the matched conditions under `reasoning_smoke_v1.json` only after the selection and budget
   are recorded.
