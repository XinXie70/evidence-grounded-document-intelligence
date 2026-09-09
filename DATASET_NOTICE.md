# Dataset and Artifact Notice

This repository's primary benchmark is DocScope, pinned at dataset revision
`4326db57d779829a44e46849fed0ebbe782f2e16`.

- DocScope annotations are identified by the source as **CC BY-NC-SA 4.0**.
- The collected PDFs retain their original source copyrights and are used for non-commercial
  research; they are not redistributed in this repository.
- Raw PDFs, downloaded benchmark content, newly generated page renders/crops, generated API
  outputs, model caches, and credentials are excluded from future version-control additions.
- Committed manifests contain checksums and non-content metadata needed to audit the local copy.
- [`data/fixtures/end_to_end_synthetic.json`](data/fixtures/end_to_end_synthetic.json) is synthetic
  and contains no DocScope benchmark content.

See [`data/manifests/source.json`](data/manifests/source.json) for the pinned source, official code
revision, observed corpus counts, and licensing metadata.

No separate license for the repository's original source code has been declared yet. A public
release should add one only after the project owner chooses the intended reuse terms.

## Public-release blocker found during audit

The local Git history currently contains 92 benchmark-derived PNG crops/renders (about 27.4 MiB)
from early visual experiments. They are retained locally for research provenance, but must be
removed from the public Git history before this repository is pushed. No Git remote is configured
at the time of this audit. The ignore rules now prevent new experiment images from being added;
history cleanup is intentionally deferred because it rewrites existing commits.
