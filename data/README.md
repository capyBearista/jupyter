# Data policy

This directory tracks small, reviewable project metadata and intended
annotations. Raw source files and derived datasets belong in `data/raw/`,
`data/interim/`, and `data/processed/`; those directories are ignored and are
not to be committed.

`data/annotations/` is intentionally trackable when a documented annotation
protocol is approved. See `../docs/data_provenance.md` before adding data.

## Reproducible source archive procedure

The expected archive details are recorded in `source_manifest.json`. From the
repository root, download the exact `canonical_url` in that manifest as
`congressional-bills.tgz`. Before extracting, verify both the SHA-256 digest and
byte count against `source_archive.sha256` and `source_archive.byte_size`:

```bash
curl -L "https://cs.brown.edu/people/epavlick/congressional-bills.tgz" -o congressional-bills.tgz
sha256sum congressional-bills.tgz
wc -c < congressional-bills.tgz
```

Only if both values match the manifest, extract from the repository root:

```bash
tar -xzf congressional-bills.tgz
test -d congressional-bills/processing
```

Confirm that the extraction has the root
`congressional-bills/processing` and JSON files under the expected relative
layout `{congress}/bills/{bill_type}/{bill_number}/data.json`. The archive and
raw corpus remain untracked. If the source archive changes, locally observed
audit values may differ from those in the manifest; do not treat those values as
universal corpus claims.
