# Evidence-Grounded Document Intelligence

**Subtitle:** Reliable Retrieval, Grounded Reasoning, and Selective Answering over Long Professional Documents

**Status:** Project Proposal v1.0 — Day 0 benchmark decision

**Decision date:** 2026-08-27

**Primary benchmark:** DocScope

**Fallback benchmark:** MMLongBench-Doc-V2

## 1. Executive decision

This project will study a narrow but consequential question:

> When an AI system answers questions over long professional documents, how much failure comes from retrieving the wrong evidence, how much remains after the correct evidence is supplied, and when should the system abstain rather than produce an unsupported answer?

The core chain is fixed:

```text
Evidence Retrieval → Grounded Reasoning → Reliability / Selective Answering
```

V1 is an evaluation-led, reproducible AI system project—not a PDF chatbot. It must stand alone as the first project on a 2027 graduate-recruitment résumé for Applied AI / NLP / Retrieval / LLM Evaluation roles in mainland China.

The benchmark decision is:

1. Use **DocScope** as the primary benchmark because it provides the strongest available supervision for the complete chain: gold evidence pages, bounding boxes, atomic facts, final answers, answerability, and long professional PDFs.
2. Keep **MMLongBench-Doc-V2** as a true fallback, not a second tuning target. It is used only if DocScope becomes unusable because of access, licensing, evaluator, or data-quality blockers.
3. Do not add a second benchmark to V1 merely to claim breadth. A generalisation benchmark may be added only after the core stop criteria are met.

## 2. Research questions

### RQ1 — Retrieval

How well do sparse and dense baselines retrieve all human-annotated evidence pages for questions that often require evidence from multiple pages?

### RQ2 — Retrieval versus downstream failure

How large is the answer-quality gap between real retrieval and oracle evidence, and which errors persist even when gold evidence is supplied?

### RQ3 — Reliability

Can a confidence policy derived from observable system signals reduce incorrect or unsupported answers at an acceptable loss of coverage?

### RQ4 — Architecture decisions

Which, if any, additional component—hybrid fusion, reranking, or visual representation—is justified by measured failure patterns?

RQ4 is deliberately conditional. The project does not pre-commit to a complex architecture.

## 3. Pre-registered hypotheses

- **H1:** Sparse and dense retrieval will have complementary failure slices; hybrid retrieval is adopted only if this is observed on development data.
- **H2:** Oracle evidence will materially outperform real retrieval, but will remain below perfect answer accuracy, demonstrating both retrieval and downstream bottlenecks.
- **H3:** Answer accuracy alone will overstate reliability because some correct answers will not be supported by the retrieved/cited evidence.
- **H4:** A calibrated abstention policy will improve answered-question reliability as coverage decreases.
- **H5:** Visually anchored questions (tables, charts, images) will account for a disproportionate share of failures under a text-only representation. A visual path is added only if this failure is both large and actionable.

These are hypotheses, not promised outcomes. Negative results remain valid project results if the experiment is controlled and reproducible.

## 4. Day 0 benchmark audit

| Candidate | Access and licence | Scale / format | Answer and evidence supervision | Retrieval–reasoning decomposition | Cost / contamination | Decision |
|---|---|---|---|---|---|---|
| **DocScope (2026)** | Public annotations and 273 PDFs; annotations are CC BY-NC-SA 4.0; PDFs originate from FinePDFs/ODC-By, with underlying document copyright retained | 1,124 QA; 273 PDFs; 205 MB observed repository size; official dev/test only | Gold answer, answerability, evidence pages, bboxes, element types, and 5,613 linked atomic facts | **Excellent.** Supports real retrieval, oracle page/region/fact, answer verification, grounding, and abstention | New QA reduces direct QA contamination, but public source PDFs may have appeared in pretraining. Official fact/answer/bbox scoring uses API judges | **Primary** |
| **MMLongBench-Doc-V2 (2026 correction of 2024 benchmark)** | Public; repository declares Apache-2.0; source PDFs are obtained from upstream and should not be redistributed by this project | 1,071 corrected QA over 134 PDFs; answer formats and evidence pages | Gold answer and evidence pages; no linked region/fact chain comparable to DocScope | Good for page-retrieval versus answer analysis; weaker for fine-grained grounding | Questions have been public and widely benchmarked since 2024, so contamination risk is materially higher | **Fallback** |
| **XL-DocBench (2026)** | Public 2.71 MB annotations; licence field is `other`; PDFs are not bundled, only 331 public URLs | 1,519 QA: 1,354 single-doc and 165 cross-doc; 219 empty-evidence questions | Answers, evidence pages, evidence snippets, 12 reasoning types | Strong in principle | Fragile URL acquisition, unclear licence, anonymous release, and no bundled PDFs create reproducibility risk | Reject for V1 |
| **GDP.pdf (2026)** | Public; MIT dataset card; 100 PDFs/tasks; about 468 MB | Test-only, 100 expert-authored professional tasks across 10 domains | Atomic grading rubrics, prompts, domains, and PDFs; no canonical page/bbox evidence field comparable to DocScope | Weak for clean retrieval-versus-reasoning attribution | High API/judge cost per small test set; all items selected because frontier models failed | Defer as a possible post-V1 challenge set |
| **ACORD (2025)** | Public CC BY 4.0 | 114 legal retrieval queries and 126,662 explicitly rated query–clause pairs in BEIR format | Graded retrieval relevance only | Excellent retrieval benchmark, but no downstream QA/reasoning target | Narrow legal domain; does not answer the project’s full causal chain | Reject as primary/fallback |

Primary sources: [DocScope paper](https://arxiv.org/abs/2605.08888), [DocScope code](https://github.com/MiliLab/DocScope), [DocScope data](https://huggingface.co/datasets/MiliLab/DocScope), [MMLongBench-Doc-V2](https://github.com/VectifyAI/MMLongBench-Doc-V2), [XL-DocBench](https://huggingface.co/datasets/anonymous12123/XL-DocBench), [GDP.pdf](https://huggingface.co/datasets/surgeai/GDP.pdf), and [ACORD](https://huggingface.co/datasets/theatticusproject/acord).

## 5. Why DocScope wins

DocScope is the only audited candidate that gives V1 all of the following in one coherent schema:

- complete professional PDFs rather than isolated passages;
- final-answer supervision;
- answerability / unanswerable cases;
- gold evidence pages;
- gold evidence regions as bounding boxes;
- evidence-to-fact links and atomic fact descriptions;
- official page, region, fact, and answer evaluation stages;
- enough questions for development, calibration, slicing, and a locked final test.

The audit also found real constraints that must remain visible:

- the annotations are non-commercial and ShareAlike;
- individual PDF copyrights are not transferred by the dataset release;
- the official dev and test sets share six document IDs, so the project must remove those documents from development to prevent document-level leakage;
- the official README’s short `extract_class` description is stale relative to the released data, which contains classes 1–8;
- two records contain no evidence, including one answerable record with answer `0`; these require manual audit before metric computation;
- official region/fact/answer evaluation introduces judge-model cost and variance.

These are manageable protocol issues, not reasons to reject the benchmark.

## 6. Experimental programme

### Phase A — Data and deterministic retrieval baselines

1. Validate PDFs, annotations, page numbering, and the two zero-evidence records.
2. Build one fixed, traceable document representation.
3. Run BM25 and one off-the-shelf dense retriever.
4. Measure page Recall@K, complete-evidence Recall@K, MRR/nDCG, latency, and storage.
5. Produce retrieval failure slices by evidence type, number of evidence pages, answerability, and extraction class.

### Phase B — Grounded answering and Oracle Evidence

Use one pinned reasoning model and the same answer prompt across conditions:

- question only / closed-book control;
- real retrieved context;
- Oracle Page;
- Oracle Region;
- Oracle Fact as a separate upper-bound diagnostic.

The main result is the gap between real retrieval and Oracle Region/Page, not a single leaderboard number.

### Phase C — One failure-driven retrieval improvement

Adopt at most one major improvement before re-evaluation:

- hybrid fusion, if sparse and dense errors are complementary;
- reranking, if candidate recall is high but top-rank placement is poor;
- visual/page-image representation, if visually anchored evidence dominates otherwise unsolved failures.

No improvement is added without an observed failure, a written hypothesis, and an ablation against the baseline.

### Phase D — Selective answering

Fit a confidence/abstention policy on calibration data using only signals available at inference time. Report risk–coverage curves and the trade-off between automation coverage and grounded correctness.

### Phase E — Thin demonstration layer

Only after the experimental stop criteria are met, create a minimal demonstration that shows:

- the question;
- answer or abstention;
- cited page/region;
- confidence/reliability signal;
- a concise explanation of why the system abstained.

This is a showcase, not the project core.

## 7. Scope boundary

V1 does **not** include:

- Agent, MCP, multi-agent orchestration, memory, tool ecosystems, or autonomous workflows;
- custom OCR, PDF parser research, VLM training, embedding-model training, or LLM fine-tuning;
- simultaneous optimisation on multiple benchmarks;
- knowledge graphs or graph RAG;
- a complex frontend, authentication, multi-user deployment, or production-scale backend;
- legal advice or a domain-specific legal product;
- unmotivated combinations of BM25, dense retrieval, hybrid fusion, reranking, verifier models, and query rewriting.

## 8. Reproducible deliverables

V1 is complete only when it contains:

1. versioned dataset manifest, licence notes, checksums, and document-level split files;
2. reproducible sparse and dense retrieval baselines;
3. retrieval metrics plus failure slices;
4. real-retrieval versus Oracle Evidence results under a pinned reasoning model;
5. a retrieval/reasoning/grounding failure matrix with manually audited samples;
6. one failure-driven intervention and an ablation, even if the result is negative;
7. selective-answering risk–coverage evaluation;
8. cost and latency accounting;
9. README, experiment table, and concise thin demo;
10. at least two defensible quantitative résumé bullets based on measured results.

## 9. Stop criteria

The project stops at V1 when all mandatory deliverables above are reproducible and the following questions can be answered with data:

- Which retrieval baseline wins, on which slices, and why?
- What fraction of answer error is retrieval-associated versus persistent under oracle evidence?
- How often is a correct answer unsupported by the retrieved/cited evidence?
- What reliability improvement is obtained at 90%, 80%, and 60% answer coverage?
- Which one architecture decision was justified by failure analysis?
- What did the improvement cost in latency, storage, and API usage?

Anything beyond these criteria is V2 work.

## 10. Fallback trigger

Switch from DocScope to MMLongBench-Doc-V2 only if one of these conditions is met before baseline completion:

- required PDFs or annotations cannot be reproducibly downloaded;
- project publication goals conflict with DocScope’s non-commercial ShareAlike terms;
- page/bbox alignment defects prevent reliable evidence scoring on more than 2% of audited records;
- the required official evaluation cannot be made stable within the agreed API budget;
- a material benchmark defect invalidates retrieval–reasoning decomposition.

The fallback must be documented as a decision record. Poor baseline performance is not a fallback trigger.

## 11. Immediate next action

Day 1 should implement only a **data audit and benchmark harness skeleton**: immutable manifests, clean document-level splits, PDF/page validation, and a deterministic evidence-page scorer. System architecture work begins only after that harness passes.
