---
description: Verify applicable study artifacts with safe serial repository checks
---

You are the active verification agent. Work from the repository root. Treat
`$ARGUMENTS` as an optional scope hint, and inspect applicable changed artifacts
before running checks.

Use only safe direct serial commands. Do not use `uv`, `uv run`, `py_compile`,
`compileall`, dependency installation, parallel tests, or a routine full-corpus
run. If `.venv` tools or required local artifacts are absent, stop and report
that fact; do not install, regenerate, or run the full corpus pipeline as a
fallback.

For applicable repository verification, run these commands with
`PYTHONDONTWRITEBYTECODE=1`:

- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest --cov=bill_titles --cov-report=term-missing -p no:cacheprovider`
- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/ruff check . --no-cache`
- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/ruff format --check .`
- `PYTHONDONTWRITEBYTECODE=1 git diff --check`

When canonical, metrics, or keyness artifacts are applicable, use this exact
serial procedure if the local ignored artifacts exist. Capture the repository
root before changing directories, verify these seven required files, then run
from the unrelated `/tmp` directory. If any file is absent, report lineage
skipped with every missing path and reason; do not generate or regenerate
artifacts.

    (
      ROOT="$(pwd -P)"
      CANONICAL="$ROOT/data/processed/title_pairs.csv.gz"
      CANONICAL_SIDECAR="$ROOT/data/processed/title_pairs.csv.summary.json"
      METRICS="$ROOT/data/processed/title_pairs_with_metrics.csv.gz"
      METRICS_SIDECAR="$ROOT/data/processed/title_pairs_with_metrics.csv.summary.json"
      SUMMARY="$ROOT/reports/tables/keyness_summary.json"
      KEYNESS_ALL="$ROOT/reports/tables/weighted_log_odds_unigrams.csv"
      KEYNESS_SHARED="$ROOT/reports/tables/weighted_log_odds_unigrams_shared_stage.csv"
      missing=0
      for path in \
        "$CANONICAL" \
        "$CANONICAL_SIDECAR" \
        "$METRICS" \
        "$METRICS_SIDECAR" \
        "$SUMMARY" \
        "$KEYNESS_ALL" \
        "$KEYNESS_SHARED"; do
        if [ ! -f "$path" ]; then
          printf 'lineage skipped: missing %s\n' "$path"
          missing=1
        fi
      done
      if [ "$missing" -ne 0 ]; then
        exit 0
      fi
      cd /tmp || exit 1
      PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$ROOT/src" "$ROOT/.venv/bin/python" - "$CANONICAL" "$METRICS" "$SUMMARY" <<'PY'
    from pathlib import Path
    import sys

    from bill_titles.clean import validate_published_output
    from bill_titles.keyness import validate_keyness_outputs
    from bill_titles.metrics import validate_metrics_lineage

    canonical, metrics, summary = map(Path, sys.argv[1:])
    canonical_result = validate_published_output(canonical)
    digest = canonical_result["output_csv_sha256"]
    metrics_result = validate_metrics_lineage(
        metrics,
        expected_input_path=canonical,
        expected_input_csv_sha256=digest,
    )
    keyness_result = validate_keyness_outputs(
        summary,
        expected_input_path=canonical,
        expected_input_csv_sha256=digest,
    )
    print(
        "lineage passed: "
        f"canonical rows={canonical_result['eligible_pairs']} "
        f"csv_sha256={digest}; "
        f"metrics rows={metrics_result['output_rows']} "
        f"csv_sha256={metrics_result['output_csv_sha256']}; "
        f"keyness rows={keyness_result['tables']['all']['row_count']} "
        f"shared_stage_rows={keyness_result['tables']['shared_stage']['row_count']}"
    )
    PY
    )

The lineage subshell can be skipped for missing artifacts without skipping
subsequent applicable notebook, Git, or ignored-boundary verification checks.

This procedure must use the public APIs and the runtime `output_csv_sha256`
returned by canonical validation. Do not hardcode a corpus digest or trust a
manifest input path to select the canonical input.

When notebooks changed or apply, execute each existing applicable notebook
directly with `.venv/bin/jupyter nbconvert --execute --inplace`. Do not execute
missing notebooks. Inspect notebook JSON afterward for error outputs and
`/home/...` host paths.

Verify Git status and ignored boundaries, including that ignored raw/interim/
processed artifacts and local-only files remain outside the intended change.
Report every exact command and result. Do not claim success from partial checks;
identify skipped checks and their reasons explicitly.
