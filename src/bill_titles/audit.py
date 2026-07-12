"""Streaming, descriptive audit tables for extracted title evidence."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
from collections import Counter
from pathlib import Path

from bill_titles.clean import _matching_evidence, _stages, _titles

SOURCES = ("official", "short", "popular")
CANDIDATE_SOURCES = (*SOURCES, "display")
COMPARISON_STATES = (
    "exact_single_match",
    "match_with_distinct_alternatives",
    "disagrees_with_candidates",
    "top_level_only",
    "candidate_only",
    "absent_from_both",
)
EQUAL_OFFICIAL_SHORT_EXAMPLE_CAP = 50
MULTIPLE_STAGE_SEMANTICS = (
    "records contribute once per unique matching stage; "
    "counts can sum above the denominator"
)


def _values(row: dict[str, str], source: str) -> list[str]:
    return json.loads(row[f"non_portion_{source}_titles_json"])


def _comparison(top: str, candidates: list[str]) -> str:
    if top and candidates:
        if top not in candidates:
            return "disagrees_with_candidates"
        return (
            "exact_single_match"
            if len(set(candidates)) == 1
            else "match_with_distinct_alternatives"
        )
    if top:
        return "top_level_only"
    if candidates:
        return "candidate_only"
    return "absent_from_both"


def _write(path: Path, fields: list[str], rows: list[dict[str, object]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _evidence(row: dict[str, str], source: str) -> list[dict[str, object]]:
    titles = json.loads(row["titles_json"])
    if not isinstance(titles, list):
        return []
    return [
        entry
        for entry in titles
        if isinstance(entry, dict)
        and entry.get("type") == source
        and entry.get("is_for_portion") is not True
        and isinstance(entry.get("title"), str)
        and entry["title"]
    ]


def audit_candidates(candidate_path: Path, output_dir: Path) -> dict[str, Path]:
    """Write deterministic source-comparison, multiplicity, and coverage tables."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    total = 0
    disagreements: Counter[str] = Counter()
    coverage: Counter[str] = Counter()
    missing: Counter[str] = Counter()
    pairs: Counter[str] = Counter()
    multiplicity: Counter[tuple[str, int, int]] = Counter()
    display: Counter[str] = Counter()
    example_counts: Counter[str] = Counter()
    examples: list[dict[str, object]] = []
    equal_total = 0
    equal_rows: list[dict[str, object]] = []
    stage_distributions: Counter[tuple[str, str]] = Counter()
    multiple_stage_matches: Counter[str] = Counter()
    alignment: Counter[str] = Counter()
    no_shared_patterns: Counter[tuple[str, str]] = Counter()
    stage_examples: list[dict[str, object]] = []
    selection: Counter[str] = Counter()
    multiple_distinct_candidates: Counter[str] = Counter()
    multiple_distinct_stage_selection: Counter[tuple[str, str]] = Counter()
    with gzip.open(candidate_path, "rt", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            total += 1
            titles = _titles(row, total + 1)
            coverage[row["congress"]] += 1
            for source in SOURCES:
                candidates = _values(row, source)
                disagreements[
                    f"{source}_{_comparison(row[f'{source}_title'], candidates)}"
                ] += 1
                missing[f"{source}_title"] += not bool(row[f"{source}_title"])
            official, short = row["official_title"], row["short_title"]
            if not official and not short:
                selection["missing_both"] += 1
            elif not official:
                selection["missing_official_only"] += 1
            elif not short:
                selection["missing_short_only"] += 1
            matching_stages: dict[str, list[str | None]] = {}
            for source in SOURCES:
                title = row[f"{source}_title"]
                evidence = (
                    _matching_evidence(titles, source, title, total + 1)
                    if title
                    else []
                )
                stages = _stages(evidence)
                matching_stages[source] = stages
                stage_distributions[
                    (source, json.dumps(stages, ensure_ascii=False))
                ] += 1
                if len(stages) > 1:
                    multiple_stage_matches[source] += 1
            if official and short:
                shared = [
                    stage
                    for stage in matching_stages["official"]
                    if stage is not None and stage in matching_stages["short"]
                ]
                status = "shared_stage" if shared else "no_shared_stage"
                alignment[status] += 1
                if status == "no_shared_stage":
                    no_shared_patterns[
                        (
                            json.dumps(matching_stages["official"], ensure_ascii=False),
                            json.dumps(matching_stages["short"], ensure_ascii=False),
                        )
                    ] += 1
                if len(stage_examples) < 50:
                    stage_examples.append(
                        {
                            "bill_id": row["bill_id"],
                            "status": status,
                            "official_matching_stages_json": json.dumps(
                                matching_stages["official"], ensure_ascii=False
                            ),
                            "short_matching_stages_json": json.dumps(
                                matching_stages["short"], ensure_ascii=False
                            ),
                            "shared_stages_json": json.dumps(
                                shared, ensure_ascii=False
                            ),
                        }
                    )
            pairs[
                "official_and_short_both_missing"
                if not official and not short
                else "official_and_short_equal"
                if official and official == short
                else "official_and_short_distinct_or_one_missing"
            ] += 1
            if official and official == short:
                equal_total += 1
                if len(equal_rows) < EQUAL_OFFICIAL_SHORT_EXAMPLE_CAP:
                    equal_rows.append(
                        {
                            "bill_id": row["bill_id"],
                            "official_title": official,
                            "short_title": short,
                        }
                    )
            display_values = _values(row, "display")
            if not display_values:
                display["display_absent"] += 1
            elif not row["official_title"]:
                display["display_present_official_absent"] += 1
            elif row["official_title"] in display_values:
                display["display_present_matches_official_top"] += 1
            else:
                display["display_present_does_not_match_official_top"] += 1
            for source in CANDIDATE_SOURCES:
                entries = _evidence(row, source)
                texts = _values(row, source)
                multiplicity[(source, len(entries), len(set(texts)))] += 1
                if source in ("official", "short") and len(set(texts)) > 1:
                    multiple_distinct_candidates[source] += 1
                    for stage in matching_stages[source]:
                        multiple_distinct_stage_selection[
                            (source, json.dumps(stage, ensure_ascii=False))
                        ] += 1
                if len(set(texts)) > 1 and example_counts[source] < 50:
                    examples.append(
                        {
                            "source": source,
                            "bill_id": row["bill_id"],
                            "top_level_value": row.get(f"{source}_title", ""),
                            "candidate_texts_json": json.dumps(
                                texts, ensure_ascii=False, separators=(",", ":")
                            ),
                            "candidate_evidence_json": json.dumps(
                                entries, ensure_ascii=False, separators=(",", ":")
                            ),
                        }
                    )
                    example_counts[source] += 1
    paths = {
        "data_audit": _write(
            output_dir / "data_audit.csv",
            ["metric", "value"],
            [
                {"metric": "records", "value": total},
                {"metric": "unique_congresses", "value": len(coverage)},
                {
                    "metric": "denominator_note",
                    "value": "record-level counts use all emitted records",
                },
                {"metric": "equal_official_short_total", "value": equal_total},
                {
                    "metric": "equal_official_short_example_cap",
                    "value": EQUAL_OFFICIAL_SHORT_EXAMPLE_CAP,
                },
            ],
        ),
        "disagreement": _write(
            output_dir / "title_source_disagreement.csv",
            ["category", "count", "denominator"],
            [
                {
                    "category": f"{source}_{state}",
                    "count": disagreements[f"{source}_{state}"],
                    "denominator": total,
                }
                for source in SOURCES
                for state in COMPARISON_STATES
            ],
        ),
        "coverage": _write(
            output_dir / "coverage_by_congress.csv",
            ["congress", "emitted_records", "denominator_all_records"],
            [
                {
                    "congress": congress,
                    "emitted_records": coverage[congress],
                    "denominator_all_records": total,
                }
                for congress in sorted(coverage, key=int)
            ],
        ),
        "missingness": _write(
            output_dir / "title_missingness_and_pairs.csv",
            ["diagnostic", "count", "denominator"],
            [
                {
                    "diagnostic": f"missing_{field}",
                    "count": missing[field],
                    "denominator": total,
                }
                for field in sorted(missing)
            ]
            + [
                {"diagnostic": key, "count": pairs[key], "denominator": total}
                for key in (
                    "official_and_short_both_missing",
                    "official_and_short_equal",
                    "official_and_short_distinct_or_one_missing",
                )
            ],
        ),
        "candidate_multiplicity": _write(
            output_dir / "non_portion_candidate_multiplicity.csv",
            [
                "source",
                "candidate_entry_count",
                "distinct_text_count",
                "count",
                "denominator",
            ],
            [
                {
                    "source": source,
                    "candidate_entry_count": entries,
                    "distinct_text_count": distinct,
                    "count": count,
                    "denominator": total,
                }
                for (source, entries, distinct), count in sorted(multiplicity.items())
            ],
        ),
        "multiple_candidates": _write(
            output_dir / "multiple_distinct_candidates_examples.csv",
            [
                "source",
                "bill_id",
                "top_level_value",
                "candidate_texts_json",
                "candidate_evidence_json",
            ],
            examples,
        ),
        "display_relationship": _write(
            output_dir / "display_title_presence_relationship.csv",
            ["diagnostic", "count", "denominator"],
            [
                {"diagnostic": key, "count": display[key], "denominator": total}
                for key in (
                    "display_absent",
                    "display_present_official_absent",
                    "display_present_matches_official_top",
                    "display_present_does_not_match_official_top",
                )
            ],
        ),
        "equal_official_short": _write(
            output_dir / "equal_official_short_titles.csv",
            ["bill_id", "official_title", "short_title"],
            equal_rows,
        ),
        "stage_distribution": _write(
            output_dir / "top_level_matching_stage_distributions.csv",
            ["source", "matching_stages_json", "count", "denominator_all_records"],
            [
                {
                    "source": source,
                    "matching_stages_json": stages,
                    "count": count,
                    "denominator_all_records": total,
                }
                for (source, stages), count in sorted(stage_distributions.items())
            ],
        ),
        "multiple_matching_stages": _write(
            output_dir / "multiple_matching_stages.csv",
            [
                "source",
                "records_with_multiple_matching_stages",
                "denominator_all_records",
            ],
            [
                {
                    "source": source,
                    "records_with_multiple_matching_stages": multiple_stage_matches[
                        source
                    ],
                    "denominator_all_records": total,
                }
                for source in SOURCES
            ],
        ),
        "multiple_distinct_stage_selection": _write(
            output_dir / "multiple_distinct_candidate_stage_selection.csv",
            [
                "source",
                "matching_stage_json",
                "count",
                "denominator_records_with_multiple_distinct_candidates",
                "multiple_stage_semantics",
            ],
            [
                {
                    "source": source,
                    "matching_stage_json": stage,
                    "count": count,
                    "denominator_records_with_multiple_distinct_candidates": (
                        multiple_distinct_candidates[source]
                    ),
                    "multiple_stage_semantics": MULTIPLE_STAGE_SEMANTICS,
                }
                for (source, stage), count in sorted(
                    multiple_distinct_stage_selection.items()
                )
            ],
        ),
        "stage_alignment": _write(
            output_dir / "shared_stage_distribution.csv",
            ["status", "count", "denominator_eligible_pairs"],
            [
                {
                    "status": status,
                    "count": alignment[status],
                    "denominator_eligible_pairs": sum(alignment.values()),
                }
                for status in ("shared_stage", "no_shared_stage")
            ],
        ),
        "no_shared_patterns": _write(
            output_dir / "no_shared_stage_patterns.csv",
            [
                "official_matching_stages_json",
                "short_matching_stages_json",
                "count",
                "denominator_no_shared_stage",
            ],
            [
                {
                    "official_matching_stages_json": official_stages,
                    "short_matching_stages_json": short_stages,
                    "count": count,
                    "denominator_no_shared_stage": alignment["no_shared_stage"],
                }
                for (official_stages, short_stages), count in sorted(
                    no_shared_patterns.items()
                )
            ],
        ),
        "stage_examples": _write(
            output_dir / "stage_alignment_examples.csv",
            [
                "bill_id",
                "status",
                "official_matching_stages_json",
                "short_matching_stages_json",
                "shared_stages_json",
            ],
            stage_examples,
        ),
        "canonical_selection": _write(
            output_dir / "canonical_selection_summary.csv",
            ["metric", "value"],
            [
                {"metric": "rule", "value": "top-level official_title and short_title"},
                {"metric": "total_input", "value": total},
                {"metric": "eligible_pairs", "value": sum(alignment.values())},
                {
                    "metric": "missing_official_only",
                    "value": selection["missing_official_only"],
                },
                {
                    "metric": "missing_short_only",
                    "value": selection["missing_short_only"],
                },
                {"metric": "missing_both", "value": selection["missing_both"]},
                {"metric": "shared_stage", "value": alignment["shared_stage"]},
                {"metric": "no_shared_stage", "value": alignment["no_shared_stage"]},
                {
                    "metric": "popular_display_policy",
                    "value": "comparison-only; never canonical fallbacks",
                },
                {
                    "metric": "portion_policy",
                    "value": "preserved in titles_json; never canonical candidates",
                },
            ],
        ),
    }
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit extracted title evidence without selecting a title source."
    )
    parser.add_argument("candidate_path", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("reports/tables"))
    args = parser.parse_args()
    print(
        json.dumps(
            {
                key: str(value)
                for key, value in audit_candidates(
                    args.candidate_path, args.output_dir
                ).items()
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
