# Methodology

## Canonical title selection (Gate 2)

The approved canonical pair uses the source-provided top-level `official_title`
and `short_title` fields exactly as extracted: no normalization, candidate
ranking, or fallback is applied. A record enters `title_pairs.csv.gz` only when
both fields are nonempty. Popular and display titles remain comparison-only and
are never canonical fallbacks. Entries marked `is_for_portion: true` remain in
`titles_json` for traceability but are never canonical candidates.

The selection preserves all corpus records in the audit. The pair table flags
whether non-portion entries matching the two top-level texts share an `as`
stage; null or unknown `as` values remain visible as evidence but cannot make a
pair shared-stage. Eligible pairs with no shared non-null stage are retained
and flagged; later analysis will include a shared-stage sensitivity subset.

The pair table is published as a data-and-summary pair. Exact decompressed CSV
bytes are the scientific identity (`output_csv_sha256`); the gzip digest
(`output_gzip_sha256`) is the physical blob identity. Compressor variance may
therefore change only the gzip digest, not the CSV identity. Gate 2 writes the
data first and publishes `title_pairs.csv.summary.json` last; the summary is
the completion marker and records gzip level 9, mtime zero, and nonempty
Python/zlib runtime provenance. Runtime metadata is explanatory and is not
compared with the current runtime during validation. Before any Gate 2 or
future in-package reader opens the canonical pair table, it must call
`bill_titles.clean.validate_published_output(output)`.
Serialized paths are canonical POSIX paths relative to the containing summary
directory. Output paths are exact filenames; provenance input paths may contain
`..` but are still interpreted relative to that directory, never relative to
the process working directory.
Data without a valid, matching summary is incomplete and must be rejected. This
assumes one batch writer; interrupted runs need not preserve a prior generation.
It detects and rejects incomplete or mismatched pairs, not joint multi-file
atomicity, and makes no claim about concurrent writers or power-loss durability.

Ordinary validation does not reopen the interim candidate input: missing-title
category counts are generation-reported provenance constrained by their types
and reconciliation arithmetic. Canonical validation streams the published gzip
CSV and recomputes its row and shared/no-shared-stage aggregates. This is an
empirical behavior of this local extraction, not a claim that
top-level fields are documented source authority. For records with multiple
distinct official candidates, the audit reports the observed `as` labels for
candidate text that exactly matches the top-level official field. The rerun
table has 2,783 such official records and reports 2 agreed-to, 791 amended-by-
House, 626 amended-by-Senate, and 1,366 enacted matching-stage labels; none is
`introduced`. These label counts use the table's multiple-stage semantics and
do not impose a stage ordering or infer a latest stage. The corresponding
short-title table is descriptive under the same semantics.

## Candidate extraction and audit

Run `python -m bill_titles.extract congressional-bills/processing` to discover
every `data.json` recursively and inspect the observed nominal layout
`{congress}/bills/{bill_type}/{bill_type}{bill_number}/data.json`. Unexpected
layouts, malformed/unreadable JSON, invalid or inconsistent identities, and
duplicate IDs are reported after the complete stream and result in a nonzero
exit. The extractor preserves duplicate title evidence separately. Required
identity is canonical integer or digit-string `congress` and `number`,
`bill_type`, and matching `bill_id`; it must also match the nominal path.
Missing titles and summaries are not errors; an invalid `subjects` type or
non-string `subjects_top_term` is an explicit nonblocking audit issue. Summary
`outcome_counts` assigns one primary outcome to each discovered file;
`secondary_issue_counts` lists nonblocking issues on emitted records; and
`issue_count` equals `blocking_issue_count + secondary_issue_count`. A
non-string `subjects_top_term` is preserved in `subjects_top_term_raw_json`.
The table
preserves top-level title fields and the full `titles` value, plus non-portion
official, short, popular, and display candidate sets. Popular and display are
comparison sources only, not canonical choices.

Run `python -m bill_titles.audit data/interim/all_bill_title_candidates.csv.gz`
to write public descriptive tables to `reports/tables/`. The audit streams the
candidate CSV and reports candidate entry/distinct-text distributions,
deterministic multiple-candidate examples with title-entry metadata, display
relationships, equal official/short diagnostics, and source-comparison counts
with explicit record denominators. Comparisons describe agreement or
disagreement only; they do not establish source precedence.
`multiple_distinct_candidate_stage_selection.csv` is the public empirical
table for the official and short observations above. Its denominator is records
with multiple distinct candidates for that source; a record contributes once
per unique matching `as` label, so label counts may sum above that denominator.
`equal_official_short_titles.csv` has at most 50 deterministic examples;
`data_audit.csv` reports the exact equal-title total and the cap. See data
provenance for local coverage gaps that limit all coverage descriptions.

## Planned protocol

Before analysis, the project will document: a frozen source manifest; record
selection and deduplication rules; title-field definitions; missing-data
handling; text normalization; and the exact descriptive measures and software
versions used. Synthetic fixtures will exercise transformations before they are
applied to raw material.

## Transparent metrics and lexicons (Gate 3)

`python -m bill_titles.metrics data/processed/title_pairs.csv.gz` validates the
canonical data-and-summary completion marker before streaming one metric row per
canonical pair. It preserves every input field and appends metrics, then writes
`title_pairs_with_metrics.csv.gz` deterministically (gzip timestamp zero) and
publishes its `.summary.json` last. `validate_metrics_output` is a bounded,
self-contained output consistency validator and does not prove derivation from
its input. `validate_metrics_lineage` additionally
anchors the output to a caller-supplied canonical path and CSV digest, checking
both canonical identities and the metrics input gzip identity. It requires both
files, the exact Gate 3 sidecar schema, a matching SHA-256 checksum, reconciled
integer row counts, and bounded integer eligibility/candidate/stage-alignment
count maps. It also reads the compressed data to verify its row count; unknown
or missing sidecar fields, malformed data, and tampering are rejected. Failed
runs remove partial output and summary files.

The shared tokenizer is Unicode-aware and resource-free: tokens are runs of
Unicode letters or digits, retaining internal apostrophes (straight or smart),
hyphens, and dotted acronym periods. A terminal period is discarded as ordinary
punctuation (`Act.` becomes `Act`), while a full dotted acronym retains its
terminal period (`U.S.` and `U.S.A.` are canonical tokens). Other punctuation
separates tokens;
numbers are tokens but are excluded from alphabetic-token measures. Capitalized
tokens are not automatically acronyms: acronym tokens contain at least two
letters and all their letters are uppercase. Character counts include all
Unicode characters, including whitespace. `word_count` includes all tokens;
mean token length and densities use alphabetic tokens. Deltas are named
`*_delta_official_minus_short`; `compression_ratio_official_over_short` is
official word count divided by short word count and is null if the denominator
is zero.

`lexicons.py` contains versioned, exact curated forms only: no stemming or
lemmatization is performed. The values and threat lexicons have core and
contextual tiers. `American`, `community`, and the constituency/group nouns
`children`, `family`/`families`, `veteran(s)`, `worker(s)`, and `taxpayer(s)` are
contextual. They remain counted and reportable, but constituency/group nouns are
not sufficient evidence of a values frame and cannot themselves trigger a values
candidate. `border` and `security` are contextual in the threat lexicon for the
same candidate rule. A values or threat candidate requires a strictly
positive core-category `short minus official` count delta. A
`mechanism_obscuring_candidate` requires a short broad-action count above zero
and an official concrete-mechanism count strictly greater than the short count.
Matched forms are emitted as deterministic JSON arrays for each title/category.

The programmatic `surface_simplification_candidate` is a surface proxy, not a
claim about accessibility or comprehension. It requires fewer short-title
words and at least two strict improvements among lower mean alphabetic-token
length, lower legalese density, lower acronym density, and higher Flesch
Reading Ease. Per-proxy availability and improvement fields are emitted. Flesch
Reading Ease and Flesch-Kincaid grade use deterministic `textstat` calls only
when a title has at least five alphabetic tokens; the sidecar records the actual
installed `textstat` distribution version, and score deltas require both
titles to be eligible. The stricter ten-token both-title sensitivity flag is
also emitted. Library calculation failures are recorded by named reason rather
than silently replaced. These formulae are unstable on title fragments and do
not measure reader understanding.

## Interpretation limits

Outputs will describe observed text under the documented protocol. They will
not support claims about bias detection, speaker or author intent, reader
comprehension, or policy quality.

## Keyness discovery contract (Gate 3)

Before any ranked-term interpretation, `python -m bill_titles.keyness
data/processed/title_pairs.csv.gz` validates the canonical published output and
writes `reports/tables/weighted_log_odds_unigrams.csv`, the prespecified
`shared_stage` sensitivity table, and `keyness_summary.json`. The primary
denominator is all eligible pairs; the sensitivity denominator is exactly the
eligible pairs whose `stage_alignment_status` is `shared_stage`. No-shared-stage
pairs remain in the primary denominator. Malformed or unknown alignment values
are rejected.

Independent validation calls must explicitly supply the trusted canonical path
and its runtime-computed decompressed CSV digest:
`validate_keyness_outputs(summary, expected_input_path=trusted_path,
expected_input_csv_sha256=trusted_digest)`. Input paths are compared after
`Path.resolve(strict=False)` normalization; the published manifest remains an
untrusted artifact and cannot choose the input to trust. This is
caller-anchored integrity checking, not a signature, authenticity, or
immutable-storage guarantee. Gate 2 validation still supplies its single-writer
completion consistency check. A valid alternate level-9 gzip representation of
the same CSV is accepted after regenerating its sidecar; keyness does not pin
the physical gzip blob.
Keyness schema 4 uses the same summary-relative path rule. Its single writer
removes the summary first, writes both tables to same-directory temporary files,
replaces both tables, and publishes the summary last. Validation failure removes
the generation. This detects completion, but does not provide joint atomicity,
concurrency control, or power-loss durability.

The unit is token frequency, not document frequency. The exact public Unicode
tokenizer above is reused, then output is casefolded and exact standard English
stopwords from scikit-learn's `ENGLISH_STOP_WORDS` are removed, except for the
predeclared domain-term retention set `{act, bill, law, resolution}`. No other
domain stopwords are added. The manifest records the installed scikit-learn
version, base count and SHA-256, exact sorted exceptions, and effective count
and SHA-256 of the sorted newline-delimited effective stopword set. Dotted acronyms and internal straight/smart
apostrophes retain the tokenizer's documented behavior; numeric tokens are
already absent from this tokenizer's alphabetic title stream. Legislative terms
including `act`, `bill`, `law`, and `resolution` are not excluded.

For token *i*, let `o_i` and `s_i` be official and short frequency counts,
`N_o` and `N_s` their post-stopword totals, and `p_i=o_i+s_i`. The frozen
informative Dirichlet prior is `alpha_i=p_i`, with `alpha_0=sum(p_i)` and no
tuned scaling parameter. The reported direction is short minus official:

```
delta_i = log((s_i+alpha_i)/(N_s+alpha_0-s_i-alpha_i))
          - log((o_i+alpha_i)/(N_o+alpha_0-o_i-alpha_i))
V_i = 1/(s_i+alpha_i) + 1/(N_s+alpha_0-s_i-alpha_i)
    + 1/(o_i+alpha_i) + 1/(N_o+alpha_0-o_i-alpha_i)
z_i = delta_i / sqrt(V_i)
```

Positive values are relatively more common in short titles and negative values
are relatively more common in official titles. Only unigrams with pooled
frequency at least 25 are published; this is a discovery filter, not a
significance threshold. Tables expose pre-stopword totals, analyzed totals,
excluded stopword tokens, pair counts, vocabulary sizes, and eligible-term
counts in the machine-readable manifest. Counts, arithmetic, finite statistics,
ordering, ranks, headers, row counts, and SHA-256 checksums are validated.
These outputs are corpus-discovery evidence only and do not measure importance,
bias, intent, or comprehension.

## Reproducibility

CI runs linting, formatting checks, and synthetic tests only. It does not
download, require, or process the local raw corpus.
