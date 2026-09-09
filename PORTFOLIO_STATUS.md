# Portfolio Status and Stop Line

**Status:** research MVP and portfolio packaging complete
**Primary benchmark:** DocScope  
**Development scope used so far:** document-isolated `development_tune`  
**Locked test status:** untouched for method development

## What the project now demonstrates

1. A pinned and audited long-document benchmark with document-level split isolation.
2. Deterministic evidence-page scoring with complete-evidence metrics.
3. Sparse BM25 and dense BGE retrieval baselines.
4. A failure-driven hybrid RRF intervention that improves Complete Evidence Recall@10 from
   70.71% (BM25) to 77.41% on 239 development-tune questions.
5. An Oracle Evidence experiment that separates retrieval failures from reasoning failures.
6. Explicit answer/abstain behavior and audited page citations.
7. A bounded OCR/visual fallback justified by observed missing-text and layout failures.
8. A reusable comparison pipeline that extracts grounded facts, performs arithmetic locally,
   validates numeric citations, and preserves abstentions.
9. Reproducible experiment identities, cost logging, preflight caps, and 286 passing tests.
10. An offline command-line replay that exposes successes and failures without another API call.

## Frozen headline results

| Result | Value | Scope |
|---|---:|---|
| BM25 Complete Evidence Recall@10 | 70.71% | 239 development-tune questions |
| Dense Complete Evidence Recall@10 | 74.06% | same 239 questions |
| RRF Complete Evidence Recall@10 | 77.41% | same 239 questions |
| Oracle-vs-real task accuracy gap | +37.5 points | 24-question reliability pilot |
| Eligible visual recoveries | 3/3 | diagnostic cases, not population estimate |
| Generic comparison exact match | 4/6 | frozen six-document validation |
| Generic comparison evidence match | 5/6 | frozen six-document validation |
| Verified citations among answered cases | 5/5 | frozen six-document validation |

## Remaining work before a public GitHub release

- [x] Replace the obsolete Day-1 README with the full project story.
- [x] Add a zero-cost offline result demo.
- [x] Run the full local test suite and secret scan.
- [x] Curate the experiment directory through a main-path index without deleting provenance.
- [x] Add a compact experiment index and architecture diagram.
- [x] Remove 92 benchmark page images from the complete `main` history while preserving ignored
      local copies and a verified recovery bundle.
- [x] Add a benchmark-usage notice and verify public history contains no PNG, JPG, or PDF files.
- [x] Create a clean portfolio commit and review the Git diff.
- [x] Release the repository's original source code under the MIT License while keeping dataset
      and third-party artifact terms separate.
- [x] Defer calibration and locked-test execution until a generic R1 visual route is frozen on
      tune-only evidence; document the one-iteration stop rule.
- [x] Run the single bounded R1 iteration, retain its negative result, and close the MVP without
      calibration or locked-test performance claims.

## Stop line

The portfolio MVP does **not** require another retriever, a trained custom model, an agent system,
MCP, multi-agent orchestration, or a frontend. New experiments are allowed only when they close a
specific unchecked release item or test a failure already documented above.

## Draft resume bullets

- Built a reproducible evidence-grounded QA pipeline for 273 long PDFs (14,014 pages), combining
  BM25 and BGE dense retrieval with reciprocal-rank fusion; improved Complete Evidence Recall@10
  from 70.71% to 77.41% on 239 document-isolated development questions.
- Designed Oracle Evidence, citation verification, selective answering, and OCR/visual fallback
  experiments to attribute retrieval, representation, and reasoning failures; shipped immutable
  experiment records, API cost controls, and 286 automated tests.

These bullets deliberately describe development results rather than claiming locked-test or
production performance.
