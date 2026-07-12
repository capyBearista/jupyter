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

## WSL execution safety

- Use direct serial `.venv/bin/python`, `.venv/bin/ruff`, and `.venv/bin/jupyter` commands.
- Do not use `uv run`, `py_compile`, or `compileall` during verification.
- Do not install dependencies as a fallback during verification; stop and report missing tools or artifacts.

## Completion evidence

- Before closing a research gate, invoke `verification-before-completion` and freshly run applicable synthetic tests with coverage, Ruff lint/format, `git diff --check`, artifact completion/lineage validators, and executed-notebook error/host-path checks.

## Review contract

- Reviewers evaluate against the frozen documented contract and identify the exact violated criterion.
- Stronger guarantees, including full row-by-row derivation proof, reopening discarded upstream inputs, authenticity, multi-file transactional snapshots, concurrency, and power-loss durability, are optional hardening rather than defects unless explicitly required.
- If a review demand conflicts with frozen scope, challenge it and seek a bounded decision before editing.

## Research interpretation

- Invoke a fresh independent research review before interpreting ranked or discovered results publicly.

## Strict JSON agents

- Avoid Markdown-fenced JSON examples. Enforce exact packet/output schemas and bare-object first- and last-character boundaries.
