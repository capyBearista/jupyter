"""Synthetic contracts for canonical top-level title selection."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
from pathlib import Path

import pytest

from bill_titles.audit import audit_candidates
from bill_titles.clean import canonicalize_candidates, validate_published_output

MULTIPLE_STAGE_SEMANTICS = (
    "records contribute once per unique matching stage; "
    "counts can sum above the denominator"
)

FIELDS = [
    "source_path",
    "bill_id",
    "congress",
    "bill_type",
    "number",
    "official_title",
    "short_title",
    "popular_title",
    "titles_json",
    "introduced_at",
    "updated_at",
    "subjects_top_term",
    "non_portion_official_titles_json",
    "non_portion_short_titles_json",
    "non_portion_popular_titles_json",
    "non_portion_display_titles_json",
]


def candidate(**overrides: object) -> dict[str, str]:
    row = {
        "source_path": "100/bills/hr/hr1/data.json",
        "bill_id": "hr1-100",
        "congress": "100",
        "bill_type": "hr",
        "number": "1",
        "official_title": "Official",
        "short_title": "Short",
        "popular_title": "Popular",
        "titles_json": json.dumps(
            [
                {"type": "official", "title": "Official", "as": "introduced"},
                {"type": "short", "title": "Short", "as": "introduced"},
            ]
        ),
        "introduced_at": "",
        "updated_at": "",
        "subjects_top_term": "",
        "non_portion_official_titles_json": '["Official"]',
        "non_portion_short_titles_json": '["Short"]',
        "non_portion_popular_titles_json": '["Popular"]',
        "non_portion_display_titles_json": "[]",
    }
    row.update(overrides)
    return row


def write_candidates(path: Path, rows: list[dict[str, str]]) -> None:
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def read_pairs(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_selects_exact_top_level_titles_and_calculates_stages(tmp_path: Path) -> None:
    source, output = tmp_path / "input.csv.gz", tmp_path / "pairs.csv.gz"
    write_candidates(
        source,
        [
            candidate(
                titles_json=json.dumps(
                    [
                        {"type": "official", "title": "Official", "as": "introduced"},
                        {"type": "official", "title": "Official", "as": "reported"},
                        {"type": "short", "title": "Short", "as": None},
                        {"type": "short", "title": "Short", "as": "reported"},
                        {"type": "popular", "title": "Popular", "as": "reported"},
                        {
                            "type": "official",
                            "title": "Official",
                            "is_for_portion": True,
                            "as": "enacted",
                        },
                    ]
                )
            )
        ],
    )
    summary = canonicalize_candidates(source, output)
    row = read_pairs(output)[0]
    assert row["canonical_official_title"] == "Official"
    assert row["canonical_short_title"] == "Short"
    assert row["official_title_source"] == row["short_title_source"] == "top_level"
    assert json.loads(row["official_matching_stages_json"]) == [
        "introduced",
        "reported",
    ]
    assert json.loads(row["short_matching_stages_json"]) == [None, "reported"]
    assert json.loads(row["shared_stages_json"]) == ["reported"]
    assert row["stage_alignment_status"] == "shared_stage"
    assert summary["eligible_pairs"] == 1


def test_null_stage_evidence_is_preserved_but_not_shared(tmp_path: Path) -> None:
    source, output = tmp_path / "input.csv.gz", tmp_path / "pairs.csv.gz"
    write_candidates(
        source,
        [
            candidate(
                titles_json=json.dumps(
                    [
                        {"type": "official", "title": "Official", "as": None},
                        {"type": "short", "title": "Short", "as": None},
                    ]
                )
            )
        ],
    )
    summary = canonicalize_candidates(source, output)
    row = read_pairs(output)[0]
    assert json.loads(row["official_matching_stages_json"]) == [None]
    assert json.loads(row["short_matching_stages_json"]) == [None]
    assert json.loads(row["shared_stages_json"]) == []
    assert row["stage_alignment_status"] == "no_shared_stage"
    assert summary["no_shared_stage"] == 1


def test_mixed_null_and_nonmatching_stage_is_not_shared(tmp_path: Path) -> None:
    source, output = tmp_path / "input.csv.gz", tmp_path / "pairs.csv.gz"
    write_candidates(
        source,
        [
            candidate(
                titles_json=json.dumps(
                    [
                        {"type": "official", "title": "Official", "as": None},
                        {"type": "short", "title": "Short", "as": "reported"},
                    ]
                )
            )
        ],
    )
    summary = canonicalize_candidates(source, output)
    row = read_pairs(output)[0]
    assert json.loads(row["shared_stages_json"]) == []
    assert row["stage_alignment_status"] == "no_shared_stage"
    assert summary["no_shared_stage"] == 1


def test_excludes_incomplete_pairs_and_never_falls_back_to_popular_or_portion(
    tmp_path: Path,
) -> None:
    source, output = tmp_path / "input.csv.gz", tmp_path / "pairs.csv.gz"
    write_candidates(
        source,
        [
            candidate(bill_id="hr1-100", official_title="", short_title="Short"),
            candidate(
                bill_id="hr2-100", number="2", official_title="Official", short_title=""
            ),
            candidate(bill_id="hr3-100", number="3", official_title="", short_title=""),
            candidate(
                bill_id="hr4-100",
                number="4",
                titles_json=json.dumps(
                    [
                        {
                            "type": "official",
                            "title": "Official",
                            "is_for_portion": True,
                            "as": "introduced",
                        },
                        {"type": "short", "title": "Short", "as": "reported"},
                    ]
                ),
            ),
        ],
    )
    summary = canonicalize_candidates(source, output)
    assert summary["eligible_pairs"] == 1
    assert summary["missing_official_only"] == 1
    assert summary["missing_short_only"] == 1
    assert summary["missing_both"] == 1
    row = read_pairs(output)[0]
    assert json.loads(row["official_matching_stages_json"]) == []
    assert row["stage_alignment_status"] == "no_shared_stage"


@pytest.mark.parametrize("titles", ["{bad", json.dumps({"not": "a list"})])
def test_rejects_malformed_titles_json_without_stale_outputs_or_temps(
    tmp_path: Path, titles: str
) -> None:
    source, output = tmp_path / "input.csv.gz", tmp_path / "pairs.csv.gz"
    write_candidates(source, [candidate(titles_json=titles)])
    summary_path = output.with_suffix(".summary.json")
    output.write_bytes(b"stale")
    summary_path.write_text("stale", encoding="utf-8")
    with pytest.raises(ValueError, match="titles_json"):
        canonicalize_candidates(source, output)
    assert not output.exists()
    assert not summary_path.exists()
    assert not list(tmp_path.glob(".*.tmp"))


def test_rejects_duplicate_ids_without_stale_outputs_or_temps(tmp_path: Path) -> None:
    source, output = tmp_path / "input.csv.gz", tmp_path / "pairs.csv.gz"
    write_candidates(source, [candidate(), candidate()])
    summary_path = output.with_suffix(".summary.json")
    output.write_bytes(b"stale")
    summary_path.write_text("stale", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate bill_id"):
        canonicalize_candidates(source, output)
    assert not output.exists()
    assert not summary_path.exists()
    assert not list(tmp_path.glob(".*.tmp"))


def test_normalizes_truncated_candidate_gzip_to_value_error(tmp_path: Path) -> None:
    source, output = tmp_path / "input.csv.gz", tmp_path / "pairs.csv.gz"
    source.write_bytes(b"\x1f\x8b\x08\x00")

    with pytest.raises(ValueError, match="malformed or truncated gzip payload"):
        canonicalize_candidates(source, output)

    assert not output.exists()
    assert not output.with_suffix(".summary.json").exists()
    assert not list(tmp_path.glob(".*.tmp"))


def test_is_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "input.csv.gz"
    write_candidates(source, [candidate()])
    first = canonicalize_candidates(source, tmp_path / "one.csv.gz")
    second = canonicalize_candidates(source, tmp_path / "two.csv.gz")
    assert first["output_gzip_sha256"] == second["output_gzip_sha256"]


def test_validates_published_output_and_returns_summary(tmp_path: Path) -> None:
    source, output = tmp_path / "input.csv.gz", tmp_path / "pairs.csv.gz"
    write_candidates(source, [candidate()])
    published = canonicalize_candidates(source, output)

    assert validate_published_output(output) == published


def test_published_validation_requires_exact_decision(tmp_path: Path) -> None:
    source, output = tmp_path / "input.csv.gz", tmp_path / "pairs.csv.gz"
    write_candidates(source, [candidate()])
    canonicalize_candidates(source, output)
    summary_path = output.with_suffix(".summary.json")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["decision"] = "synthetic"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    with pytest.raises(ValueError, match="schema"):
        validate_published_output(output)


def test_input_path_with_parent_component_is_cwd_independent(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source = source_dir / "input.csv.gz"
    output = tmp_path / "pairs.csv.gz"
    write_candidates(source, [candidate()])
    canonicalize_candidates(source, output)
    summary_path = output.with_suffix(".summary.json")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["input_path"] == "source/input.csv.gz"
    assert validate_published_output(output)["input_path"] == "source/input.csv.gz"


def test_published_validation_uses_summary_parent_not_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, output = tmp_path / "input.csv.gz", tmp_path / "pairs.csv.gz"
    write_candidates(source, [candidate()])
    canonicalize_candidates(source, output)
    monkeypatch.chdir(Path("/tmp"))

    assert validate_published_output(output.resolve())["output_path"] == output.name


def test_rejects_internal_parent_traversal_in_summary_path(tmp_path: Path) -> None:
    source, output = tmp_path / "input.csv.gz", tmp_path / "pairs.csv.gz"
    write_candidates(source, [candidate()])
    canonicalize_candidates(source, output)
    summary_path = output.with_suffix(".summary.json")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["input_path"] = "a/../input.csv.gz"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    with pytest.raises(ValueError, match="canonical"):
        validate_published_output(output)


def test_accepts_leading_ancestry_in_summary_input_path(tmp_path: Path) -> None:
    source_dir = tmp_path / "data"
    source_dir.mkdir()
    source, output = source_dir / "input.csv.gz", tmp_path / "pairs.csv.gz"
    write_candidates(source, [candidate()])
    canonicalize_candidates(source, output)
    summary_path = output.with_suffix(".summary.json")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["input_path"] = "../../data/input.csv.gz"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    assert validate_published_output(output)["input_path"] == "../../data/input.csv.gz"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("eligible_pairs", 0, "counts do not reconcile"),
        ("shared_stage", 0, "stage counts do not reconcile"),
        ("no_shared_stage", 1, "stage counts do not reconcile"),
        ("missing_both", -1, "counts are malformed"),
        ("eligible_pairs", True, "counts are malformed"),
        ("total_input", 99, "counts do not reconcile"),
    ],
)
def test_rejects_tampered_canonical_summary_counts(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    source, output = tmp_path / "input.csv.gz", tmp_path / "pairs.csv.gz"
    write_candidates(source, [candidate()])
    canonicalize_candidates(source, output)
    summary_path = output.with_suffix(".summary.json")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary[field] = value
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        validate_published_output(output)


@pytest.mark.parametrize("mutation", ["duplicate", "empty_title", "unknown_alignment"])
def test_rejects_semantically_forged_canonical_csv(
    tmp_path: Path, mutation: str
) -> None:
    source, output = tmp_path / "input.csv.gz", tmp_path / "pairs.csv.gz"
    write_candidates(source, [candidate(), candidate(bill_id="hr2-100", number="2")])
    canonicalize_candidates(source, output)
    with gzip.open(output, "rt", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if mutation == "duplicate":
        rows[1]["bill_id"] = rows[0]["bill_id"]
    elif mutation == "empty_title":
        rows[0]["canonical_official_title"] = ""
    else:
        rows[0]["stage_alignment_status"] = "unknown"
    with output.open("wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0])
                writer.writeheader()
                writer.writerows(rows)
    summary_path = output.with_suffix(".summary.json")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["output_gzip_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    from bill_titles.clean import sha256_gzip_payload

    summary["output_csv_sha256"] = sha256_gzip_payload(output)
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    with pytest.raises(ValueError):
        validate_published_output(output)


def test_rejects_regenerated_hash_forgery_with_boolean_numeric_evidence(
    tmp_path: Path,
) -> None:
    source, output = tmp_path / "input.csv.gz", tmp_path / "pairs.csv.gz"
    write_candidates(
        source,
        [
            candidate(
                titles_json=json.dumps(
                    [
                        {
                            "type": "official",
                            "title": "Official",
                            "as": "introduced",
                            "is_for_portion": 1,
                        },
                        {"type": "short", "title": "Short", "as": "introduced"},
                    ]
                )
            )
        ],
    )
    canonicalize_candidates(source, output)
    with gzip.open(output, "rt", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    evidence = json.loads(rows[0]["official_matching_evidence_json"])
    evidence[0]["is_for_portion"] = True
    rows[0]["official_matching_evidence_json"] = json.dumps(evidence)
    with output.open("wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0])
                writer.writeheader()
                writer.writerows(rows)
    summary_path = output.with_suffix(".summary.json")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["output_gzip_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    from bill_titles.clean import sha256_gzip_payload

    summary["output_csv_sha256"] = sha256_gzip_payload(output)
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    with pytest.raises(ValueError, match="evidence"):
        validate_published_output(output)


def test_rejects_forged_stage_status_with_consistent_summary_counts(
    tmp_path: Path,
) -> None:
    source, output = tmp_path / "input.csv.gz", tmp_path / "pairs.csv.gz"
    write_candidates(source, [candidate(), candidate(bill_id="hr2-100", number="2")])
    canonicalize_candidates(source, output)
    with gzip.open(output, "rt", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["stage_alignment_status"] = "no_shared_stage"
    with output.open("wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0])
                writer.writeheader()
                writer.writerows(rows)
    summary_path = output.with_suffix(".summary.json")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["shared_stage"] = 1
    summary["no_shared_stage"] = 1
    summary["output_gzip_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    from bill_titles.clean import sha256_gzip_payload

    summary["output_csv_sha256"] = sha256_gzip_payload(output)
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    with pytest.raises(ValueError, match="stage alignment"):
        validate_published_output(output)


def test_rejects_corrupt_gzip_even_with_updated_physical_hash(tmp_path: Path) -> None:
    source, output = tmp_path / "input.csv.gz", tmp_path / "pairs.csv.gz"
    write_candidates(source, [candidate()])
    canonicalize_candidates(source, output)
    output.write_bytes(b"not a gzip")
    summary_path = output.with_suffix(".summary.json")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["output_gzip_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    with pytest.raises(ValueError, match="malformed or truncated gzip payload"):
        validate_published_output(output)


def test_rejects_published_output_with_missing_summary(tmp_path: Path) -> None:
    source, output = tmp_path / "input.csv.gz", tmp_path / "pairs.csv.gz"
    write_candidates(source, [candidate()])
    canonicalize_candidates(source, output)
    output.with_suffix(".summary.json").unlink()

    with pytest.raises(ValueError, match="summary is missing"):
        validate_published_output(output)


def test_rejects_published_output_with_missing_data(tmp_path: Path) -> None:
    output = tmp_path / "pairs.csv.gz"
    output.with_suffix(".summary.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="data is missing"):
        validate_published_output(output)


@pytest.mark.parametrize("contents", ["{bad", "[]"])
def test_rejects_published_output_with_malformed_or_non_object_summary(
    tmp_path: Path, contents: str
) -> None:
    source, output = tmp_path / "input.csv.gz", tmp_path / "pairs.csv.gz"
    write_candidates(source, [candidate()])
    canonicalize_candidates(source, output)
    output.with_suffix(".summary.json").write_text(contents, encoding="utf-8")

    with pytest.raises(ValueError, match="summary"):
        validate_published_output(output)


@pytest.mark.parametrize("replacement", ["0" * 64, "not-a-checksum"])
def test_rejects_published_output_with_invalid_or_stale_checksum(
    tmp_path: Path, replacement: str
) -> None:
    source, output = tmp_path / "input.csv.gz", tmp_path / "pairs.csv.gz"
    write_candidates(source, [candidate()])
    canonicalize_candidates(source, output)
    summary_path = output.with_suffix(".summary.json")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["output_gzip_sha256"] = replacement
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    with pytest.raises(ValueError, match="output_gzip_sha256|checksum does not match"):
        validate_published_output(output)


def test_rejects_published_output_with_tampered_data(tmp_path: Path) -> None:
    source, output = tmp_path / "input.csv.gz", tmp_path / "pairs.csv.gz"
    write_candidates(source, [candidate()])
    canonicalize_candidates(source, output)
    output.write_bytes(output.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match="checksum does not match"):
        validate_published_output(output)


def test_stage_public_tables_reconcile_to_their_denominators(tmp_path: Path) -> None:
    source = tmp_path / "input.csv.gz"
    write_candidates(
        source,
        [
            candidate(),
            candidate(
                bill_id="hr2-100",
                number="2",
                titles_json=json.dumps(
                    [
                        {"type": "official", "title": "Official", "as": "introduced"},
                        {"type": "short", "title": "Short", "as": "reported"},
                    ]
                ),
            ),
            candidate(bill_id="hr3-100", number="3", official_title=""),
        ],
    )
    paths = audit_candidates(source, tmp_path / "tables")
    with paths["stage_distribution"].open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert sum(int(row["count"]) for row in rows if row["source"] == "official") == 3
    with paths["stage_alignment"].open(encoding="utf-8", newline="") as handle:
        alignment = {row["status"]: int(row["count"]) for row in csv.DictReader(handle)}
    assert alignment == {"shared_stage": 1, "no_shared_stage": 1}
    with paths["canonical_selection"].open(encoding="utf-8", newline="") as handle:
        selection = {row["metric"]: row["value"] for row in csv.DictReader(handle)}
    assert selection["eligible_pairs"] == "2"
    assert selection["missing_official_only"] == "1"


def test_stage_selection_table_uses_multiple_distinct_candidate_denominators(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.csv.gz"
    write_candidates(
        source,
        [
            candidate(
                titles_json=json.dumps(
                    [
                        {"type": "official", "title": "Official", "as": "reported"},
                        {
                            "type": "official",
                            "title": "Other official",
                            "as": "enacted",
                        },
                        {"type": "short", "title": "Short", "as": "introduced"},
                        {"type": "short", "title": "Short", "as": "reported"},
                        {"type": "short", "title": "Other short", "as": "enacted"},
                    ]
                ),
                non_portion_official_titles_json='["Official", "Other official"]',
                non_portion_short_titles_json='["Short", "Other short"]',
            )
        ],
    )
    paths = audit_candidates(source, tmp_path / "tables")
    with paths["multiple_distinct_stage_selection"].open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert rows == [
        {
            "source": "official",
            "matching_stage_json": '"reported"',
            "count": "1",
            "denominator_records_with_multiple_distinct_candidates": "1",
            "multiple_stage_semantics": MULTIPLE_STAGE_SEMANTICS,
        },
        {
            "source": "short",
            "matching_stage_json": '"introduced"',
            "count": "1",
            "denominator_records_with_multiple_distinct_candidates": "1",
            "multiple_stage_semantics": MULTIPLE_STAGE_SEMANTICS,
        },
        {
            "source": "short",
            "matching_stage_json": '"reported"',
            "count": "1",
            "denominator_records_with_multiple_distinct_candidates": "1",
            "multiple_stage_semantics": MULTIPLE_STAGE_SEMANTICS,
        },
    ]


def test_audit_does_not_treat_dual_null_stage_evidence_as_shared(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.csv.gz"
    write_candidates(
        source,
        [
            candidate(
                titles_json=json.dumps(
                    [
                        {"type": "official", "title": "Official", "as": None},
                        {"type": "short", "title": "Short", "as": None},
                    ]
                )
            )
        ],
    )
    paths = audit_candidates(source, tmp_path / "tables")
    with paths["stage_alignment"].open(encoding="utf-8", newline="") as handle:
        alignment = {row["status"]: int(row["count"]) for row in csv.DictReader(handle)}
    assert alignment == {"shared_stage": 0, "no_shared_stage": 1}
