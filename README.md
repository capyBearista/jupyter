# Congressional Bill Titles Study

This repository is at the **scaffolding stage** of an independently authored
research pipeline for describing congressional bill-title text. It publishes
Gate 2 local descriptive audit and canonicalization evidence, but not analysis
results or completed-coverage claims.

## Status and boundaries

The planned work will describe text in bill titles and record transparent data
handling decisions. It will not make claims about bias detection, authorial
intent, reader comprehension, or policy quality. Results, coverage, and
inferences will be documented only after the relevant audit and analysis are
complete.

No raw corpus is committed to this repository. The local source audit is
recorded in [`data/source_manifest.json`](data/source_manifest.json), and the
provenance policy is in [`docs/data_provenance.md`](docs/data_provenance.md).

## Repository layout

- `src/bill_titles/`: independently authored Python package scaffold.
- `tests/`: synthetic, corpus-independent tests.
- `data/`: tracked metadata and future annotations; raw and derived datasets
  are intentionally ignored.
- `docs/`: research design, provenance, methodology, and AI-assistance notes.
- `reports/` and `notebooks/`: Gate 2 descriptive audit outputs and future
  authored outputs.
- `congressional-bills/`: inherited Brown LUNAR Lab starter material and local
  dataset-related source material; see
  [`congressional-bills/LEGACY.md`](congressional-bills/LEGACY.md).

## Development

Python 3.11 or newer is recommended. Install the project with its development
dependencies, then run the lightweight checks:

```bash
python -m pip install -e ".[dev]"
ruff check .
ruff format --check .
pytest
```

These checks use no full raw corpus and do not run a corpus pipeline.

## Attribution and licensing

The inherited `congressional-bills/` material is distinct from the new work in
this scaffold and remains attributed to its original source. This repository
does not make a repo-wide license grant or license claim over inherited
material. See [`NOTICE.md`](NOTICE.md) and
[`congressional-bills/LEGACY.md`](congressional-bills/LEGACY.md).

## Documentation

- [Research design](docs/research_design.md)
- [Data provenance](docs/data_provenance.md)
- [Methodology](docs/methodology.md)
- [AI assistance](docs/ai_assistance.md)
