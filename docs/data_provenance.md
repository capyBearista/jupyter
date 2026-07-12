# Data provenance

## Inherited material

`congressional-bills/` is inherited Brown University LUNAR Lab starter and
dataset-related source material. It is retained separately from independently
authored scaffolding. See `../NOTICE.md` and
`../congressional-bills/LEGACY.md`; this project makes no license claim over
that inherited material.

## Local audit and layout

The current local corpus contains **345,477 `data.json` records**. Numeric
directory shells run from **6 through 114**. Populated bill directories are
**6–11, 13–42, and 82–114**; Congress **12** and **43–81** are empty. This is a
local audit, not a completeness or coverage claim.

Within `congressional-bills/processing`, the observed nominal record layout is
`{congress}/bills/{bill_type}/{bill_type}{bill_number}/data.json` (for example,
`100/bills/hr/hr1/data.json`). Discovery audits every `data.json` recursively,
so files outside that layout are recorded as coverage-blocking layout issues
rather than omitted.

## Data handling

Raw source data are not committed. Future raw, interim, and processed data are
kept in ignored `data/raw/`, `data/interim/`, and `data/processed/` paths.
Only small metadata and approved annotations are intended for version control.
Every future analytic dataset must identify its source version, extraction time,
transformation steps, and inclusion/exclusion rules.
