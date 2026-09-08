# Day 1 Acceptance Record

**Project:** Evidence-Grounded Document Intelligence  
**Protocol date:** 2026-08-27  
**Status:** Accepted; retrieval baselines may begin under the frozen protocol.

## Frozen sources

- DocScope dataset revision: `4326db57d779829a44e46849fed0ebbe782f2e16`
- DocScope official code revision: `ac0de26b050d4f51de0407c45b5cf3fdf245e1bd`
- Raw benchmark annotations and PDFs are local-only under `data/raw/` and are ignored.
- SHA-256 coverage: `benchmark.json`, 273 PDFs, and the generated split manifest.

## Acceptance results

| Check | Result |
|---|---:|
| Benchmark questions | 1,124 |
| PDFs present and openable | 273 / 273 |
| Total PDF pages | 14,014 |
| Evidence page range errors | 0 |
| Duplicate question IDs | 0 |
| Malformed evidence bboxes | 0 |
| Orphan fact-to-evidence links | 0 |
| Text extraction document failures | 0 |
| Evidence regions / linked facts | 4,482 / 5,613 |
| Automated tests | 12 passed |
| SHA-256 entries independently verified | 275 / 275 |

Thirty PDFs report encryption metadata, but all 30 open and their text layers extract without a
document-level failure. They are retained and flagged in the PDF audit rather than altered.

## Frozen development split

The six official-dev questions whose documents occur in official test are excluded. The remaining
388 questions over 117 documents were greedily stratified with seed `20260827`:

| Partition | Documents | Questions |
|---|---:|---:|
| `development_tune` | 82 | 256 |
| `development_calibration` | 35 | 132 |
| locked official test | 156 | 730 |

Document overlap between every pair of partitions is zero. Locked-test question IDs are omitted
from the manifest; only their count, document IDs, and a hash of the sorted question IDs are stored.
Normal benchmark loading rejects test access unless the exact final-test acknowledgement is set.

## Text-layer observation

Using pinned `pypdf==6.10.0`, with non-whitespace character counts:

- 498 / 14,014 pages (3.55%) have fewer than 20 characters and are flagged
  `text_layer_missing`;
- 914 / 14,014 pages (6.52%) have fewer than 100 characters and are flagged `low_text`;
- among 2,235 unique gold evidence pages, 43 are `text_layer_missing` and 79 are `low_text`;
- 34 questions have at least one `text_layer_missing` gold page; 55 have at least one `low_text`
  gold page.

These are registered failure slices. Day 1 does not add OCR, a visual retriever, or VLM training.
Such a component remains conditional on later measured baseline failures.

## Zero-evidence resolution

Both released zero-evidence records were recorded. The answerable anomaly
`urnuuidbf633ee6-28ba-460f-b6c6-fcd694f24284::q2` (gold answer `0`) is excluded from evidence
retrieval denominators, retained in answer metrics with an audit flag, and must be reported with
sensitivity both including and excluding it.

## Day 1 artifacts

- `data/manifests/source.json` — revisions, licence notes, and source identity
- `data/manifests/checksums.sha256` — immutable file hashes
- `data/manifests/pdf_audit.json` — per-document/page validation metadata
- `data/manifests/text_layer_audit.json` — text coverage and evidence-page impact
- `data/manifests/annotation_audit.json` — bbox and fact-link integrity
- `data/manifests/split_manifest.json` — exact document-grouped partitions
- `data/manifests/anomaly_resolution.json` — zero-evidence handling
- `data/fixtures/end_to_end_synthetic.json` — non-benchmark end-to-end schema fixture
- `configs/experiment_log.schema.json` — generation/judge cost and latency log contract
- `src/egdi/scoring.py` — deterministic page-evidence scorer

No BM25, dense retriever, agent, MCP, multi-agent system, OCR/VLM training, or frontend was
implemented in Day 1.
