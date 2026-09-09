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

The repository's original source code is released under the MIT License. This does not relicense
DocScope annotations, source PDFs, model outputs, or other third-party material; those remain
subject to their respective terms.

## Public release audit

The `main` branch tracks no PNG, JPG, or PDF files, and none occur anywhere in its commit history.
The 92 benchmark crops and rendered pages used during local experiments remain available as
ignored local files. A complete pre-cleanup repository bundle is retained under the ignored
`tmp/` directory for local recovery and is not part of a normal public push.
