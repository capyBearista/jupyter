"""Streaming extraction of bill-title evidence without title selection."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import re
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "3"
FIELDNAMES = [
    "source_path",
    "bill_id",
    "congress",
    "bill_type",
    "number",
    "official_title",
    "short_title",
    "popular_title",
    "titles_json",
    "title_entry_count",
    "non_portion_official_titles_json",
    "non_portion_short_titles_json",
    "non_portion_popular_titles_json",
    "non_portion_display_titles_json",
    "introduced_at",
    "updated_at",
    "sponsor_name",
    "sponsor_bioguide_id",
    "sponsor_state",
    "sponsor_thomas_id",
    "subjects_json",
    "subjects_top_term",
    "subjects_top_term_raw_json",
]
ISSUE_FIELDS = ["source_path", "outcome", "detail"]
_BILL_DIRECTORY = re.compile(r"(?P<type>[a-z]+)(?P<number>[0-9]+)$")


def _layout(path: Path, root: Path) -> tuple[str, str, int, int] | None:
    """Return nominal path identity, or None when a discovered path is unexpected."""
    parts = path.relative_to(root).parts
    if (
        len(parts) != 5
        or parts[1] != "bills"
        or parts[-1] != "data.json"
        or not parts[0].isdigit()
    ):
        return None
    match = _BILL_DIRECTORY.fullmatch(parts[3])
    if match is None or match["type"] != parts[2]:
        return None
    return parts[0], parts[2], int(match["number"]), int(parts[0])


def _path_key(path: Path, root: Path) -> tuple[int, int, str, int, str]:
    layout = _layout(path, root)
    if layout is None:
        return (1, 0, "", 0, path.relative_to(root).as_posix())
    _, bill_type, number, congress = layout
    return (0, congress, bill_type, number, path.relative_to(root).as_posix())


def discover_records(source_root: Path) -> Iterator[Path]:
    """Yield every data.json below the root, including unexpected layouts."""
    yield from sorted(
        source_root.rglob("data.json"), key=lambda path: _path_key(path, source_root)
    )


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r"(?:0|[1-9][0-9]*)", value):
        return int(value)
    return None


def _candidate_titles(titles: object, title_type: str) -> list[str]:
    if not isinstance(titles, list):
        return []
    result: list[str] = []
    for candidate in titles:
        if not isinstance(candidate, dict) or candidate.get("is_for_portion") is True:
            continue
        title = candidate.get("title")
        if (
            candidate.get("type") == title_type
            and isinstance(title, str)
            and title
            and title not in result
        ):
            result.append(title)
    return result


def _row(
    record: dict[str, Any], source_path: str
) -> tuple[dict[str, str] | None, str | None]:
    bill_id, bill_type = _text(record.get("bill_id")), _text(record.get("bill_type"))
    congress, number = _integer(record.get("congress")), _integer(record.get("number"))
    if not bill_id or not bill_type or congress is None or number is None:
        return None, "bill_id, congress, bill_type, and number require canonical values"
    if bill_id != f"{bill_type}{number}-{congress}":
        return None, "bill_id does not match bill_type, number, and congress"
    titles = record.get("titles")
    title_entries = titles if isinstance(titles, list) else []
    sponsor = record.get("sponsor")
    sponsor = sponsor if isinstance(sponsor, dict) else {}
    return {
        "source_path": source_path,
        "bill_id": bill_id,
        "congress": str(congress),
        "bill_type": bill_type,
        "number": str(number),
        "official_title": _text(record.get("official_title")),
        "short_title": _text(record.get("short_title")),
        "popular_title": _text(record.get("popular_title")),
        "titles_json": _json(titles),
        "title_entry_count": str(len(title_entries)),
        "non_portion_official_titles_json": _json(
            _candidate_titles(title_entries, "official")
        ),
        "non_portion_short_titles_json": _json(
            _candidate_titles(title_entries, "short")
        ),
        "non_portion_popular_titles_json": _json(
            _candidate_titles(title_entries, "popular")
        ),
        "non_portion_display_titles_json": _json(
            _candidate_titles(title_entries, "display")
        ),
        "introduced_at": _text(record.get("introduced_at")),
        "updated_at": _text(record.get("updated_at")),
        "sponsor_name": _text(sponsor.get("name")),
        "sponsor_bioguide_id": _text(sponsor.get("bioguide_id")),
        "sponsor_state": _text(sponsor.get("state")),
        "sponsor_thomas_id": _text(sponsor.get("thomas_id")),
        "subjects_json": _json(record["subjects"])
        if record.get("subjects") is not None
        else "",
        "subjects_top_term": _text(record.get("subjects_top_term")),
        "subjects_top_term_raw_json": _json(record["subjects_top_term"])
        if record.get("subjects_top_term") is not None
        and not isinstance(record["subjects_top_term"], str)
        else "",
    }, None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_candidates(source_root: Path, output: Path, issues: Path) -> dict[str, Any]:
    """Extract every valid record and record every discovery outcome and issue."""
    source_root, output, issues = Path(source_root), Path(output), Path(issues)
    output.parent.mkdir(parents=True, exist_ok=True)
    issues.parent.mkdir(parents=True, exist_ok=True)
    duplicate_evidence = output.with_name("ignored_duplicate_evidence.csv")
    counts: Counter[str] = Counter()
    seen_ids: set[str] = set()
    with (
        output.open("wb") as raw,
        gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed,
    ):
        with (
            io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text,
            issues.open("w", encoding="utf-8", newline="") as issue_handle,
            duplicate_evidence.open(
                "w", encoding="utf-8", newline=""
            ) as duplicate_handle,
        ):
            writer = csv.DictWriter(text, fieldnames=FIELDNAMES)
            issue_writer = csv.DictWriter(issue_handle, fieldnames=ISSUE_FIELDS)
            duplicate_writer = csv.DictWriter(duplicate_handle, fieldnames=FIELDNAMES)
            writer.writeheader()
            issue_writer.writeheader()
            duplicate_writer.writeheader()
            for path in discover_records(source_root):
                source_path = path.relative_to(source_root).as_posix()
                layout = _layout(path, source_root)
                if layout is None:
                    counts["unexpected_layout"] += 1
                    issue_writer.writerow(
                        {
                            "source_path": source_path,
                            "outcome": "unexpected_layout",
                            "detail": (
                                "expected {congress}/bills/{bill_type}/"
                                "{bill_type}{bill_number}/data.json"
                            ),
                        }
                    )
                    continue
                try:
                    with path.open(encoding="utf-8") as handle:
                        record = json.load(handle)
                except (OSError, UnicodeDecodeError) as error:
                    counts["unreadable"] += 1
                    issue_writer.writerow(
                        {
                            "source_path": source_path,
                            "outcome": "unreadable",
                            "detail": str(error),
                        }
                    )
                    continue
                except json.JSONDecodeError as error:
                    counts["malformed_json"] += 1
                    issue_writer.writerow(
                        {
                            "source_path": source_path,
                            "outcome": "malformed_json",
                            "detail": str(error),
                        }
                    )
                    continue
                if not isinstance(record, dict):
                    counts["missing_identity"] += 1
                    issue_writer.writerow(
                        {
                            "source_path": source_path,
                            "outcome": "missing_identity",
                            "detail": "top-level JSON is not an object",
                        }
                    )
                    continue
                row, identity_error = _row(record, source_path)
                if row is None:
                    outcome = (
                        "inconsistent_identity"
                        if identity_error and "does not match" in identity_error
                        else "missing_identity"
                    )
                    counts[outcome] += 1
                    issue_writer.writerow(
                        {
                            "source_path": source_path,
                            "outcome": outcome,
                            "detail": identity_error or "invalid identity",
                        }
                    )
                    continue
                path_congress, path_bill_type, path_number, _ = layout
                if (
                    row["congress"] != path_congress
                    or row["bill_type"] != path_bill_type
                    or row["number"] != str(path_number)
                ):
                    counts["inconsistent_identity"] += 1
                    issue_writer.writerow(
                        {
                            "source_path": source_path,
                            "outcome": "inconsistent_identity",
                            "detail": (
                                "payload identity does not match nominal path identity "
                                f"{path_bill_type}{path_number}-{path_congress}"
                            ),
                        }
                    )
                    continue
                if row["bill_id"] in seen_ids:
                    counts["duplicate_bill_id"] += 1
                    issue_writer.writerow(
                        {
                            "source_path": source_path,
                            "outcome": "duplicate_bill_id",
                            "detail": row["bill_id"],
                        }
                    )
                    duplicate_writer.writerow(row)
                    continue
                seen_ids.add(row["bill_id"])
                subjects = record.get("subjects")
                if subjects is not None and (
                    not isinstance(subjects, list)
                    or not all(isinstance(value, str) for value in subjects)
                ):
                    counts["subjects_not_list_of_strings"] += 1
                    issue_writer.writerow(
                        {
                            "source_path": source_path,
                            "outcome": "subjects_not_list_of_strings",
                            "detail": "subjects must be a list of strings when present",
                        }
                    )
                subjects_top_term = record.get("subjects_top_term")
                if subjects_top_term is not None and not isinstance(
                    subjects_top_term, str
                ):
                    counts["subjects_top_term_not_string"] += 1
                    issue_writer.writerow(
                        {
                            "source_path": source_path,
                            "outcome": "subjects_top_term_not_string",
                            "detail": "subjects_top_term must be a string when present",
                        }
                    )
                counts["emitted"] += 1
                writer.writerow(row)
    outcome_names = (
        "emitted",
        "malformed_json",
        "unreadable",
        "unexpected_layout",
        "missing_identity",
        "inconsistent_identity",
        "duplicate_bill_id",
    )
    outcomes = {name: counts[name] for name in outcome_names}
    blocking = sum(value for name, value in outcomes.items() if name != "emitted")
    secondary_issue_names = (
        "subjects_not_list_of_strings",
        "subjects_top_term_not_string",
    )
    secondary_issues = {name: counts[name] for name in secondary_issue_names}
    secondary_issue_count = sum(secondary_issues.values())
    summary = {
        "schema_version": SCHEMA_VERSION,
        "source_root": str(source_root),
        "discovered": sum(outcomes.values()),
        "outcome_counts": outcomes,
        "emitted": outcomes["emitted"],
        "issue_count": blocking + secondary_issue_count,
        "blocking_issue_count": blocking,
        "secondary_issue_count": secondary_issue_count,
        "secondary_issue_counts": secondary_issues,
        "output_gzip_sha256": _sha256(output),
        "duplicate_evidence_path": str(duplicate_evidence),
    }
    output.with_suffix(".summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if blocking:
        raise SystemExit(f"extraction completed with {blocking} blocking issue(s)")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stream bill title evidence without choosing canonical titles."
    )
    parser.add_argument(
        "source_root",
        type=Path,
        help=(
            "Root containing {congress}/bills/{bill_type}/"
            "{bill_type}{bill_number}/data.json"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/interim/all_bill_title_candidates.csv.gz"),
    )
    parser.add_argument(
        "--issues", type=Path, default=Path("data/interim/extraction_issues.csv")
    )
    args = parser.parse_args()
    summary = extract_candidates(args.source_root, args.output, args.issues)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
