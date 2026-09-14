# Question-Conditioned Visual Retrieval Protocol v1

**Status:** preregistered before implementation and scoring
**Split:** `development_tune` only
**Eligible population:** the same 63 R1 questions selected by frozen visual router v1
**Paid OpenAI API budget:** USD 0 for retrieval development and evaluation

## Observed failure

The previous generic layout reranker asked only whether a candidate page contained a table,
raster image, or vector object. Those signals were saturated across visually rich documents and
did not improve Complete Evidence Recall at Top-3 or Top-5.

Targeted Oracle-image diagnostics separately showed that a visual reasoner can recover answers
when the correct page or region is already known. The unresolved step is therefore label-free,
question-conditioned visual page selection.

## Hypothesis

A visual document retriever that jointly represents the question and the rendered PDF page can
rank the page containing the requested entities, metric, period, table, or chart above visually
similar distractors more effectively than binary page-layout signals.

## Frozen candidate

1. Candidate pool remains the selected equal-weight BM25 + BGE RRF Top-10.
2. Render each candidate as a full physical-page RGB image with reversible `doc_id` and page
   provenance.
3. Use the off-the-shelf `vidore/colSmol-256M` visual document retriever at revision
   `c79b633e17e060cc109b11aa2bf92a1517d3bd6f`, whose resolved base checkpoint is
   `vidore/ColSmolVLM-Instruct-256M-base` revision
   `99ca96f1f6b95b3a69e6abef74a2416cb738fed0`, with no task-specific training.
4. Encode the original English benchmark question as the query and each full page image as a
   visual document.
5. Score query-page relevance using the model's ColBERT-style late interaction.
6. Sort by descending visual score; exact ties preserve original RRF order.
7. Do not use benchmark answers, answerability, gold pages, evidence boxes, facts, manual labels,
   calibration data, or locked-test data during rendering, encoding, scoring, or ranking.

The compatibility smoke may use synthetic pages only. It may change device or numerical dtype to
make the frozen model run on the available machine, but it may not inspect DocScope labels or
select hyperparameters from benchmark outcomes.

## Evaluation

After all 63 rankings have been generated and made immutable, load gold evidence only in a
separate scorer. Report:

- Any Evidence Recall at 1, 3, 5, and 10;
- Complete Evidence Recall at 1, 3, 5, and 10;
- MRR and nDCG at 10;
- per-question gains and losses versus original RRF;
- multi-page versus single-page slices;
- rendering, indexing, and query latency;
- page-embedding storage size.

## Keep/drop gate

Keep the candidate only if all conditions hold:

1. Complete Evidence Recall improves by at least four of 63 questions at Top-3 or Top-5;
2. Complete Evidence Recall does not decrease at the other of Top-3 or Top-5;
3. Any Evidence Recall decreases by no more than one question at either Top-3 or Top-5;
4. all 63 questions are processed by one generic code path with no question-ID-specific rule;
5. every selected page retains valid physical-page provenance.

Four additional complete-evidence questions correspond to a 6.35 percentage-point absolute gain
on the frozen R1 slice. This gate prevents a one-case fluctuation from being presented as a useful
system improvement.

If the gate fails, preserve the result as a negative experiment, retain original RRF order, and
move to calibrated abstention. Do not tune another visual weight, cutoff, prompt, or model after
viewing this evaluation.

## Safety and reproducibility boundaries

- Model files are stored only in an ignored local cache and are never committed.
- Source PDFs and rendered benchmark pages remain ignored and are never redistributed.
- Dependency and model revisions, renderer version, image settings, device, dtype, hashes,
  latencies, and failures are recorded.
- The candidate is an off-the-shelf zero-shot retriever. Unknown overlap between its public
  pretraining mixture and source documents must be reported as a limitation; no DocScope-specific
  fine-tuning is performed.
- No calibration or locked-test labels may be accessed in this phase.
