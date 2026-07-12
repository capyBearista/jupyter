# Research design

## Stage

This is the frozen Gate 2 design for a future descriptive study of congressional
bill-title text. No results are reported here, and no analysis is represented as
complete.

## Approved question and analysis unit

The primary question is: **How do congressional short titles transform official
legislative language, and can transparent NLP methods surface changes in
compression, specificity, and rhetorical framing for human review?**

The analysis unit is one uniquely identified bill with one canonical official
title and one canonical short title. The canonical pair is chosen under an
audited, deterministic rule recorded with the analytic table, including any
inclusion, exclusion, deduplication, and missing-data decisions.

For Gate 2, canonical titles are the source-provided top-level `official_title`
and `short_title` values, preserved exactly, and only records with both values
are paired. Popular/display values are comparison-only; portion titles are not
candidates. Pair records retain matching stage evidence and flag whether the
two selected texts share a stage. A planned sensitivity analysis will restrict
to the shared-stage subset; no metrics, keyness, or lexicons are part of this
gate.

## Measures and interpretation limits

Direct measures are counts, ratios, exact lexical matches, corpus term
distributions, and human final annotation labels. Candidate signals may surface
surface simplification, values/threat framing, mechanism obscuring, and
review-worthiness for human review; they are not findings or automated labels.

The project will not measure or infer legislative intent, objective bias,
persuasion effects, citizen comprehension, or policy quality. Textual
descriptions and comparisons must not be interpreted as evidence for those
claims.

## Reporting and coverage

The canonical narrative report path is `reports/pilot_report.md`. Future
coverage statements must follow a reproducible source audit. The only current
coverage facts are the local-extraction audit recorded in
`data/source_manifest.json`; they are not universal corpus claims.
