"""Synthetic contracts for candidate extraction and descriptive audits."""

from __future__ import annotations

import csv
import gzip
import json
from pathlib import Path

import pytest

from bill_titles.audit import audit_candidates
from bill_titles.extract import extract_candidates


def write_record(
    root: Path, congress: int, bill_type: str, number: int, data: object
) -> Path:
    path = (
        root
        / str(congress)
        / "bills"
        / bill_type
        / f"{bill_type}{number}"
        / "data.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def valid_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "bill_id": "hr1-100",
        "congress": "100",
        "bill_type": "hr",
        "number": "1",
        "official_title": "Official title",
        "short_title": "Short title",
        "popular_title": None,
        "titles": [
            {"type": "official", "title": "Official title", "is_for_portion": False},
            {"type": "short", "title": "Short title", "is_for_portion": False},
        ],
    }
    record.update(overrides)
    return record


def read_csv(path: Path, compressed: bool = False) -> list[dict[str, str]]:
    opener = gzip.open if compressed else Path.open
    with opener(
        path, "rt" if compressed else "r", encoding="utf-8", newline=""
    ) as handle:
        return list(csv.DictReader(handle))


def test_actual_layout_numeric_order_metadata_and_candidate_sources(
    tmp_path: Path,
) -> None:
    root, output, issues = (
        tmp_path / "source",
        tmp_path / "candidates.csv.gz",
        tmp_path / "issues.csv",
    )
    write_record(root, 100, "hr", 10, valid_record(bill_id="hr10-100", number=10))
    write_record(
        root,
        100,
        "hr",
        2,
        valid_record(
            bill_id="hr2-100",
            number=2,
            official_title="Café",
            popular_title="People's Bill",
            titles=[
                {
                    "type": "official",
                    "title": "Café",
                    "is_for_portion": False,
                    "as": "introduced",
                },
                {"type": "popular", "title": "People's Bill", "is_for_portion": False},
                {"type": "display", "title": "Display", "is_for_portion": False},
                {"type": "short", "title": "Partial", "is_for_portion": True},
            ],
            sponsor={
                "name": "Renée",
                "bioguide_id": "X1",
                "state": "CA",
                "thomas_id": "T1",
                "party": "D",
            },
            subjects=["Taxation"],
            subjects_top_term="Taxation",
            policy_area="Ignored",
        ),
    )
    result = extract_candidates(root, output, issues)
    rows = read_csv(output, compressed=True)
    assert result["emitted"] == 2
    assert [row["bill_id"] for row in rows] == ["hr2-100", "hr10-100"]
    row = rows[0]
    assert json.loads(row["non_portion_popular_titles_json"]) == ["People's Bill"]
    assert json.loads(row["non_portion_display_titles_json"]) == ["Display"]
    assert row["title_entry_count"] == "4"
    assert row["sponsor_name"] == "Renée" and row["sponsor_thomas_id"] == "T1"
    assert (
        row["subjects_top_term"] == "Taxation"
        and "sponsor_party" not in row
        and "policy_area" not in row
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("congress", True),
        ("congress", 100.0),
        ("congress", "0100"),
        ("number", False),
        ("number", 1.0),
        ("number", "1.0"),
    ],
)
def test_identity_rejects_noncanonical_numeric_values(
    tmp_path: Path, field: str, value: object
) -> None:
    root, output, issues = (
        tmp_path / "source",
        tmp_path / "out.csv.gz",
        tmp_path / "issues.csv",
    )
    data = valid_record()
    data[field] = value
    write_record(root, 100, "hr", 1, data)
    with pytest.raises(SystemExit, match="blocking"):
        extract_candidates(root, output, issues)
    assert read_csv(issues)[0]["outcome"] == "missing_identity"


def test_all_discovered_paths_are_accounted_for_with_secondary_issues(
    tmp_path: Path,
) -> None:
    root, output, issues = (
        tmp_path / "source",
        tmp_path / "out.csv.gz",
        tmp_path / "issues.csv",
    )
    write_record(root, 100, "hr", 1, valid_record())
    write_record(
        root,
        100,
        "hr",
        2,
        valid_record(
            bill_id="hr1-100",
            number=1,
            official_title="Duplicate",
            titles=[{"type": "official", "title": "Duplicate", "as": "reported"}],
        ),
    )
    unexpected = root / "100" / "wrong" / "hr1" / "data.json"
    unexpected.parent.mkdir(parents=True)
    unexpected.write_text(json.dumps(valid_record()), encoding="utf-8")
    bad_subjects = write_record(
        root,
        100,
        "s",
        3,
        valid_record(bill_id="s3-100", bill_type="s", number=3, subjects={"bad": True}),
    )
    with pytest.raises(SystemExit, match="blocking"):
        extract_candidates(root, output, issues)
    issue_rows = read_csv(issues)
    assert {row["outcome"] for row in issue_rows} == {
        "inconsistent_identity",
        "unexpected_layout",
        "subjects_not_list_of_strings",
    }
    assert read_csv(output.with_name("ignored_duplicate_evidence.csv")) == []
    summary = json.loads(
        output.with_suffix(".summary.json").read_text(encoding="utf-8")
    )
    assert summary["discovered"] == sum(summary["outcome_counts"].values()) == 4
    assert summary["issue_count"] == 3
    assert summary["blocking_issue_count"] + summary["secondary_issue_count"] == 3
    assert bad_subjects.exists()


def test_inconsistent_identity_non_dict_and_malformed_json_are_blocking(
    tmp_path: Path,
) -> None:
    root, output, issues = (
        tmp_path / "source",
        tmp_path / "out.csv.gz",
        tmp_path / "issues.csv",
    )
    write_record(root, 100, "hr", 1, valid_record(bill_id="hr1-101"))
    write_record(root, 100, "s", 2, [])
    malformed = root / "100" / "bills" / "s" / "s3" / "data.json"
    malformed.parent.mkdir(parents=True)
    malformed.write_text("{broken", encoding="utf-8")
    with pytest.raises(SystemExit, match="blocking"):
        extract_candidates(root, output, issues)
    assert [row["outcome"] for row in read_csv(issues)] == [
        "inconsistent_identity",
        "missing_identity",
        "malformed_json",
    ]


def test_path_payload_identity_mismatch_is_blocking_and_not_emitted(
    tmp_path: Path,
) -> None:
    root, output, issues = (
        tmp_path / "source",
        tmp_path / "out.csv.gz",
        tmp_path / "issues.csv",
    )
    write_record(
        root,
        100,
        "hr",
        1,
        valid_record(bill_id="s2-101", congress=101, bill_type="s", number=2),
    )
    with pytest.raises(SystemExit, match="blocking"):
        extract_candidates(root, output, issues)
    assert read_csv(issues)[0]["outcome"] == "inconsistent_identity"
    assert read_csv(output, compressed=True) == []


def test_non_string_subjects_top_term_is_preserved_and_counted_as_secondary_issue(
    tmp_path: Path,
) -> None:
    root, output, issues = (
        tmp_path / "source",
        tmp_path / "out.csv.gz",
        tmp_path / "issues.csv",
    )
    write_record(root, 100, "hr", 1, valid_record(subjects_top_term={"term": "Tax"}))
    summary = extract_candidates(root, output, issues)
    row = read_csv(output, compressed=True)[0]
    assert row["subjects_top_term"] == ""
    assert json.loads(row["subjects_top_term_raw_json"]) == {"term": "Tax"}
    assert summary["outcome_counts"] == {
        "emitted": 1,
        "malformed_json": 0,
        "unreadable": 0,
        "unexpected_layout": 0,
        "missing_identity": 0,
        "inconsistent_identity": 0,
        "duplicate_bill_id": 0,
    }
    assert summary["secondary_issue_counts"] == {
        "subjects_not_list_of_strings": 0,
        "subjects_top_term_not_string": 1,
    }
    assert summary["blocking_issue_count"] == 0
    assert summary["secondary_issue_count"] == 1
    assert summary["issue_count"] == 1
    assert read_csv(issues)[0]["outcome"] == "subjects_top_term_not_string"


def test_unreadable_record_is_counted_when_open_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, output, issues = (
        tmp_path / "source",
        tmp_path / "out.csv.gz",
        tmp_path / "issues.csv",
    )
    record_path = write_record(root, 100, "hr", 1, valid_record())
    original_open = Path.open

    def failing_open(path: Path, *args: object, **kwargs: object) -> object:
        if path == record_path:
            raise OSError("synthetic unreadable record")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", failing_open)
    with pytest.raises(SystemExit, match="blocking"):
        extract_candidates(root, output, issues)
    assert read_csv(issues)[0]["outcome"] == "unreadable"


def test_extraction_repeat_run_has_identical_checksum(tmp_path: Path) -> None:
    root = tmp_path / "source"
    write_record(root, 100, "hr", 1, valid_record())
    first = extract_candidates(
        root, tmp_path / "one.csv.gz", tmp_path / "one-issues.csv"
    )
    second = extract_candidates(
        root, tmp_path / "two.csv.gz", tmp_path / "two-issues.csv"
    )
    assert first["output_gzip_sha256"] == second["output_gzip_sha256"]


def test_audit_preserves_match_with_alternatives_and_public_diagnostics(
    tmp_path: Path,
) -> None:
    root, output, issues = (
        tmp_path / "source",
        tmp_path / "candidates.csv.gz",
        tmp_path / "issues.csv",
    )
    write_record(
        root,
        100,
        "hr",
        1,
        valid_record(
            titles=[
                {"type": "official", "title": "Top", "as": "introduced"},
                {"type": "official", "title": "Other", "as": "reported"},
                {"type": "short", "title": "Short"},
                {"type": "popular", "title": "Popular"},
                {"type": "display", "title": "Display"},
            ],
            official_title="Top",
            short_title="Short",
            popular_title="Popular",
        ),
    )
    write_record(
        root,
        100,
        "s",
        2,
        valid_record(
            bill_id="s2-100",
            bill_type="s",
            number=2,
            official_title="Same",
            short_title="Same",
            titles=[],
        ),
    )
    extract_candidates(root, output, issues)
    paths = audit_candidates(output, tmp_path / "tables")
    disagreement = {row["category"]: row for row in read_csv(paths["disagreement"])}
    assert disagreement["official_match_with_distinct_alternatives"]["count"] == "1"
    assert disagreement["official_exact_single_match"]["count"] == "0"
    examples = read_csv(paths["multiple_candidates"])
    assert (
        examples[0]["bill_id"] == "hr1-100"
        and "reported" in examples[0]["candidate_evidence_json"]
    )
    assert read_csv(paths["equal_official_short"])[0]["bill_id"] == "s2-100"
    assert {row["source"] for row in read_csv(paths["candidate_multiplicity"])} == {
        "official",
        "short",
        "popular",
        "display",
    }
    assert paths["display_relationship"].exists()


@pytest.mark.parametrize(
    ("top", "candidates", "state"),
    [
        ("Top", ["Top"], "exact_single_match"),
        ("Top", ["Top", "Other"], "match_with_distinct_alternatives"),
        ("Top", ["Other"], "disagrees_with_candidates"),
        ("Top", [], "top_level_only"),
        ("", ["Candidate"], "candidate_only"),
        ("", [], "absent_from_both"),
    ],
)
def test_audit_reports_every_title_comparison_state(
    tmp_path: Path, top: str, candidates: list[str], state: str
) -> None:
    root, output, issues = (
        tmp_path / "source",
        tmp_path / "out.csv.gz",
        tmp_path / "issues.csv",
    )
    titles = [
        {"type": "official", "title": value, "as": "introduced"} for value in candidates
    ]
    write_record(root, 100, "hr", 1, valid_record(official_title=top, titles=titles))
    extract_candidates(root, output, issues)
    rows = read_csv(audit_candidates(output, tmp_path / "tables")["disagreement"])
    counts = {row["category"]: row["count"] for row in rows}
    assert counts[f"official_{state}"] == "1"


def test_audit_display_diagnostics_are_exclusive_and_equal_examples_are_capped(
    tmp_path: Path,
) -> None:
    root, output, issues = (
        tmp_path / "source",
        tmp_path / "out.csv.gz",
        tmp_path / "issues.csv",
    )
    write_record(root, 100, "hr", 1, valid_record(titles=[]))
    write_record(
        root,
        100,
        "hr",
        2,
        valid_record(
            bill_id="hr2-100",
            number=2,
            official_title="",
            titles=[{"type": "display", "title": "Display"}],
        ),
    )
    write_record(
        root,
        100,
        "hr",
        3,
        valid_record(
            bill_id="hr3-100",
            number=3,
            official_title="Top",
            titles=[{"type": "display", "title": "Top"}],
        ),
    )
    write_record(
        root,
        100,
        "hr",
        4,
        valid_record(
            bill_id="hr4-100",
            number=4,
            official_title="Top",
            titles=[{"type": "display", "title": "Other"}],
        ),
    )
    for number in range(5, 56):
        write_record(
            root,
            100,
            "hr",
            number,
            valid_record(
                bill_id=f"hr{number}-100",
                number=number,
                official_title="Same",
                short_title="Same",
                titles=[],
            ),
        )
    extract_candidates(root, output, issues)
    paths = audit_candidates(output, tmp_path / "tables")
    display = {
        row["diagnostic"]: int(row["count"])
        for row in read_csv(paths["display_relationship"])
    }
    assert display == {
        "display_absent": 52,
        "display_present_official_absent": 1,
        "display_present_matches_official_top": 1,
        "display_present_does_not_match_official_top": 1,
    }
    assert sum(display.values()) == 55
    assert len(read_csv(paths["equal_official_short"])) == 50
    data_audit = {row["metric"]: row["value"] for row in read_csv(paths["data_audit"])}
    assert data_audit["equal_official_short_total"] == "51"
    assert data_audit["equal_official_short_example_cap"] == "50"
