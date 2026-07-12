# Project conventions

- Keep new pipeline code under `src/bill_titles/` and tests under `tests/`.
- Use Python 3.11+ syntax and type annotations for new Python code.
- Keep tests synthetic and independent of the raw corpus.
- Do not commit files in `data/raw/`, `data/interim/`, or `data/processed/`.
  Intended annotation files under `data/annotations/` are trackable.
- Treat `congressional-bills/` as inherited legacy/source material. Do not
  modify it except for its provenance notice unless explicitly authorized.
- Do not change `docs/local/`; it is local working material outside this public
  scaffold.
- Run `ruff check .`, `ruff format --check .`, and `pytest` for applicable
  changes. Do not run a full corpus pipeline as part of routine checks.
