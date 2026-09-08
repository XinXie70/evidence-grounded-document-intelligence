# Evidence-Grounded Document Intelligence

Reliable retrieval, grounded reasoning, and selective answering over long professional documents.

## Current status

Day 0 and Day 1 are complete:

- primary benchmark: DocScope;
- fallback benchmark: MMLongBench-Doc-V2;
- project scope and stop criteria are frozen;
- data and evaluation protocol, including Oracle Evidence, is defined.
- DocScope data and official code revisions are pinned;
- all 273 PDFs and 14,014 pages are validated;
- clean document-level tune/calibration/locked-test manifests are frozen;
- annotation/text-layer audits and the deterministic page scorer pass validation.

Day 1 provides a reproducible data audit, document-isolated splits, a locked-test guard,
text-layer diagnostics, and a deterministic evidence-page scorer. Raw benchmark files remain
local and ignored.

## Reproduce Day 1

Use Python 3.11+ with the pinned dependencies in `pyproject.toml`, then run:

```bash
PYTHONPATH=src python -m egdi.day1 all --workers 4
PYTHONPATH=src python -m unittest discover -s tests -v
```

The downloader uses the immutable DocScope revision recorded in
`src/egdi/constants.py`. The audit writes non-content metadata under `data/manifests/`.

The official test split is unavailable through the normal loader. Final evaluation requires
the exact acknowledgement documented by `egdi.constants.LOCKED_TEST_ACK`; Day 1 integrity
auditing uses a separate narrowly named loader and does not expose test records to experiments.

See `DAY1_REPORT.md` for the acceptance record and observed data-quality findings. Baseline
retrieval work must remain driven by those observations and the frozen protocol.

## Project documents

- `PROJECT_PROPOSAL.md` — research questions, benchmark decision, scope, experiments, and completion criteria.
- `DATA_AND_EVAL_PROTOCOL.md` — data handling, splits, metrics, Oracle Evidence design, failure attribution, contamination controls, and cost gates.

## Directory layout

```text
configs/       Experiment configurations
data/          Local benchmark data and manifests; raw data is not committed
experiments/   Experiment records and analysis
results/       Generated metrics and model outputs
src/           Project source code
tests/         Automated tests
```

Raw benchmark PDFs and credentials must not be committed to version control.
