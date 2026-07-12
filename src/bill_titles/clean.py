"""Deterministic canonical top-level title-pair selection."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import platform
import re
import tempfile
import zlib
from collections import Counter
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "3"
RULE_VERSION = "1"
DECISION = (
    "Canonical official and short titles are the source-provided top-level "
    "official_title and short_title fields; popular and display titles are "
    "comparison-only and is_for_portion entries are never candidates."
)
REQUIRED_FIELDS = {
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
}
PAIR_FIELDS = [
    "source_path",
    "bill_id",
    "congress",
    "bill_type",
    "number",
    "introduced_at",
    "updated_at",
    "subjects_top_term",
    "canonical_official_title",
    "canonical_short_title",
    "official_title_source",
    "short_title_source",
    "popular_title_comparison",
    "titles_json",
    "official_matching_evidence_json",
    "short_matching_evidence_json",
    "official_matching_stages_json",
    "short_matching_stages_json",
    "shared_stages_json",
    "stage_alignment_status",
]


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_equal(left: object, right: object) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            _json_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _json_equal(left_item, right_item)
            for left_item, right_item in zip(left, right, strict=True)
        )
    return left == right


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_gzip_payload(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with gzip.open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except (gzip.BadGzipFile, EOFError, OSError, UnicodeError, zlib.error) as error:
        raise ValueError(f"malformed or truncated gzip payload: {path}") from error
    return digest.hexdigest()


_sha256 = sha256_file


def compression_metadata() -> dict[str, object]:
    return {
        "format": "gzip",
        "compresslevel": 9,
        "mtime": 0,
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "zlib_compile_version": zlib.ZLIB_VERSION,
        "zlib_runtime_version": zlib.ZLIB_RUNTIME_VERSION,
    }


COMPRESSION_FIELDS = set(compression_metadata())


def _validate_compression(value: object, label: str) -> None:
    if not isinstance(value, dict) or set(value) != COMPRESSION_FIELDS:
        raise ValueError(f"{label} compression metadata is malformed")
    if value["format"] != "gzip" or value["compresslevel"] != 9 or value["mtime"] != 0:
        raise ValueError(f"{label} compression settings are malformed")
    for field in (
        "python_implementation",
        "python_version",
        "zlib_compile_version",
        "zlib_runtime_version",
    ):
        if not isinstance(value[field], str) or not value[field]:
            raise ValueError(f"{label} compression provenance is malformed")


def _relative_path(summary_path: Path, target: Path) -> str:
    """Serialize a target as a canonical POSIX path relative to its summary."""
    return Path(
        os.path.relpath(
            Path(target).resolve(strict=False), Path(summary_path).parent.resolve()
        )
    ).as_posix()


def _resolve_relative_path(
    summary_path: Path, value: object, *, filename: bool
) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("summary-relative path is malformed")
    path = Path(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or value == "."
        or "." in path.parts
        or "//" in value
        or value.endswith("/")
    ):
        raise ValueError("summary-relative path is not canonical")
    saw_normal_component = False
    for component in path.parts:
        if component == "..":
            if saw_normal_component:
                raise ValueError("summary-relative path is not canonical")
        else:
            saw_normal_component = True
    if filename and (len(path.parts) != 1 or path.name != value):
        raise ValueError("summary output path must be an exact filename")
    return (Path(summary_path).parent / path).resolve(strict=False)


def validate_published_output(output: Path) -> dict[str, object]:
    """Validate a completed canonical pair table before opening it for reading."""
    output = Path(output)
    summary_path = output.with_suffix(".summary.json")
    if not output.is_file():
        raise ValueError(f"canonical pair data is missing: {output}")
    if not summary_path.is_file():
        raise ValueError(f"canonical pair summary is missing: {summary_path}")
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(
            f"canonical pair summary is malformed: {summary_path}"
        ) from error
    if not isinstance(summary, dict):
        raise ValueError(
            f"canonical pair summary must be a JSON object: {summary_path}"
        )
    expected_fields = {
        "schema_version",
        "rule_version",
        "decision",
        "input_path",
        "output_path",
        "total_input",
        "eligible_pairs",
        "missing_official_only",
        "missing_short_only",
        "missing_both",
        "shared_stage",
        "no_shared_stage",
        "output_gzip_sha256",
        "output_csv_sha256",
        "compression",
    }
    if (
        set(summary) != expected_fields
        or summary["schema_version"] != SCHEMA_VERSION
        or summary["rule_version"] != RULE_VERSION
        or summary["decision"] != DECISION
    ):
        raise ValueError("canonical pair summary schema is unsupported or malformed")
    for field in ("output_gzip_sha256", "output_csv_sha256"):
        if not isinstance(summary[field], str) or not re.fullmatch(
            r"[0-9a-f]{64}", summary[field]
        ):
            raise ValueError(f"canonical pair summary {field} is malformed")
    _validate_compression(summary["compression"], "canonical pair")
    output_target = _resolve_relative_path(
        summary_path, summary["output_path"], filename=True
    )
    if (
        output_target != output.resolve(strict=False)
        or summary["output_path"] != output.name
    ):
        raise ValueError("canonical output path does not match summary")
    _resolve_relative_path(summary_path, summary["input_path"], filename=False)
    count_fields = (
        "total_input",
        "eligible_pairs",
        "missing_official_only",
        "missing_short_only",
        "missing_both",
        "shared_stage",
        "no_shared_stage",
    )
    if any(
        not isinstance(summary[field], int)
        or isinstance(summary[field], bool)
        or summary[field] < 0
        for field in count_fields
    ):
        raise ValueError("canonical summary counts are malformed")
    if (
        summary["shared_stage"] + summary["no_shared_stage"]
        != summary["eligible_pairs"]
    ):
        raise ValueError("canonical summary stage counts do not reconcile")
    if summary["total_input"] != summary["eligible_pairs"] + sum(
        summary[field]
        for field in ("missing_official_only", "missing_short_only", "missing_both")
    ):
        raise ValueError("canonical summary counts do not reconcile")
    if sha256_file(output) != summary["output_gzip_sha256"]:
        raise ValueError(f"canonical pair gzip checksum does not match data: {output}")
    if sha256_gzip_payload(output) != summary["output_csv_sha256"]:
        raise ValueError(f"canonical pair CSV checksum does not match data: {output}")
    _validate_canonical_rows(output, summary)
    return summary


def _validate_canonical_rows(output: Path, summary: dict[str, object]) -> None:
    """Validate canonical CSV semantics without reopening the interim source.

    The total and missing-category counts are generation-reported provenance,
    constrained here by their types and arithmetic rather than recomputed from
    the candidate input.
    """
    seen: set[str] = set()
    shared = no_shared = rows = 0
    try:
        with gzip.open(output, "rt", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            if next(reader, None) != PAIR_FIELDS:
                raise ValueError("canonical data header is malformed")
            for line, values in enumerate(reader, 2):
                if len(values) != len(PAIR_FIELDS) or any(
                    value is None for value in values
                ):
                    raise ValueError(f"line {line}: canonical row is malformed")
                row = dict(zip(PAIR_FIELDS, values, strict=True))
                required = (
                    "source_path",
                    "bill_id",
                    "congress",
                    "bill_type",
                    "number",
                    "canonical_official_title",
                    "canonical_short_title",
                    "official_title_source",
                    "short_title_source",
                    "official_matching_evidence_json",
                    "short_matching_evidence_json",
                    "official_matching_stages_json",
                    "short_matching_stages_json",
                    "shared_stages_json",
                    "stage_alignment_status",
                )
                if any(not row[field] for field in required):
                    raise ValueError(f"line {line}: canonical required field is empty")
                if row["bill_id"] in seen:
                    raise ValueError(f"line {line}: duplicate bill_id")
                seen.add(row["bill_id"])
                if (
                    row["official_title_source"] != "top_level"
                    or row["short_title_source"] != "top_level"
                ):
                    raise ValueError(f"line {line}: title source is malformed")
                titles = _titles(row, line)
                official_evidence = _matching_evidence(
                    titles, "official", row["canonical_official_title"], line
                )
                short_evidence = _matching_evidence(
                    titles, "short", row["canonical_short_title"], line
                )

                def decoded_list(field: str) -> list[Any]:
                    try:
                        value = json.loads(row[field])
                    except json.JSONDecodeError as error:
                        raise ValueError(
                            f"line {line}: malformed {field}: {error.msg}"
                        ) from error
                    if not isinstance(value, list):
                        raise ValueError(f"line {line}: {field} must be a JSON list")
                    return value

                for field, expected in (
                    ("official_matching_evidence_json", official_evidence),
                    ("short_matching_evidence_json", short_evidence),
                ):
                    stored = decoded_list(field)
                    if not all(isinstance(item, dict) for item in stored):
                        raise ValueError(
                            f"line {line}: {field} must be a list of objects"
                        )
                    if not _json_equal(stored, expected):
                        raise ValueError(
                            f"line {line}: {field} does not match titles_json"
                        )

                official_stages = _stages(official_evidence)
                short_stages = _stages(short_evidence)
                stored_official_stages = decoded_list("official_matching_stages_json")
                stored_short_stages = decoded_list("short_matching_stages_json")
                for field, stored_stages in (
                    ("official_matching_stages_json", stored_official_stages),
                    ("short_matching_stages_json", stored_short_stages),
                ):
                    if not all(
                        isinstance(stage, str) or stage is None
                        for stage in stored_stages
                    ):
                        raise ValueError(
                            f"line {line}: {field} must contain only strings or null"
                        )
                if stored_official_stages != official_stages:
                    raise ValueError(
                        f"line {line}: official matching stages do not match evidence"
                    )
                if stored_short_stages != short_stages:
                    raise ValueError(
                        f"line {line}: short matching stages do not match evidence"
                    )

                stored_shared_stages = decoded_list("shared_stages_json")
                if not all(isinstance(stage, str) for stage in stored_shared_stages):
                    raise ValueError(
                        f"line {line}: shared_stages_json must contain only strings"
                    )
                expected_shared_stages = [
                    stage
                    for stage in official_stages
                    if stage is not None and stage in short_stages
                ]
                if stored_shared_stages != expected_shared_stages:
                    raise ValueError(
                        f"line {line}: shared stages do not match evidence"
                    )
                expected_status = (
                    "shared_stage" if expected_shared_stages else "no_shared_stage"
                )
                if row["stage_alignment_status"] != expected_status:
                    raise ValueError(f"line {line}: stage alignment is inconsistent")
                if expected_status == "shared_stage":
                    shared += 1
                else:
                    no_shared += 1
                rows += 1
    except ValueError:
        raise
    except (OSError, EOFError, csv.Error, UnicodeError, zlib.error) as error:
        raise ValueError("canonical data is missing or malformed") from error
    if (
        rows != summary["eligible_pairs"]
        or shared != summary["shared_stage"]
        or no_shared != summary["no_shared_stage"]
    ):
        raise ValueError("canonical data counts do not reconcile with summary")


def _titles(row: dict[str, str], line_number: int) -> list[dict[str, Any]]:
    try:
        titles = json.loads(row["titles_json"])
    except json.JSONDecodeError as error:
        raise ValueError(
            f"line {line_number}: malformed titles_json: {error}"
        ) from error
    if not isinstance(titles, list) or not all(
        isinstance(item, dict) for item in titles
    ):
        raise ValueError(f"line {line_number}: titles_json must be a list of objects")
    return titles


def _matching_evidence(
    titles: list[dict[str, Any]], title_type: str, title: str, line_number: int
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for entry in titles:
        if entry.get("is_for_portion") is True:
            continue
        if entry.get("type") != title_type or entry.get("title") != title:
            continue
        stage = entry.get("as")
        if stage is not None and not isinstance(stage, str):
            raise ValueError(
                f"line {line_number}: title candidate 'as' must be string or null"
            )
        evidence.append(entry)
    return evidence


def _stages(evidence: list[dict[str, Any]]) -> list[str | None]:
    stages: list[str | None] = []
    for entry in evidence:
        stage = entry.get("as")
        if stage not in stages:
            stages.append(stage)
    return stages


def _temporary_path(output: Path) -> Path:
    """Reserve a same-directory temporary path for atomic publication."""
    descriptor, name = tempfile.mkstemp(
        dir=output.parent, prefix=f".{output.name}.", suffix=".tmp"
    )
    os.close(descriptor)
    return Path(name)


def _candidate_rows(candidate_path: Path):
    """Yield candidate rows, normalizing failures reading the input gzip."""
    try:
        with gzip.open(candidate_path, "rt", encoding="utf-8", newline="") as source:
            reader = csv.DictReader(source)
            if reader.fieldnames is None or not REQUIRED_FIELDS <= set(
                reader.fieldnames
            ):
                missing = sorted(REQUIRED_FIELDS - set(reader.fieldnames or []))
                raise ValueError(f"candidate input missing required fields: {missing}")
            yield from reader
    except (gzip.BadGzipFile, EOFError, OSError, UnicodeError, zlib.error) as error:
        raise ValueError(
            f"malformed or truncated gzip payload: {candidate_path}"
        ) from error


def canonicalize_candidates(candidate_path: Path, output: Path) -> dict[str, object]:
    """Select complete top-level title pairs and preserve their source evidence."""
    candidate_path, output = Path(candidate_path), Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    summary_path = output.with_suffix(".summary.json")
    summary_path.unlink(missing_ok=True)
    output.unlink(missing_ok=True)
    output_temp = _temporary_path(output)
    summary_temp = _temporary_path(summary_path)
    counts: Counter[str] = Counter()
    seen_ids: set[str] = set()
    try:
        with (
            output_temp.open("wb") as raw,
            gzip.GzipFile(
                filename="", fileobj=raw, mode="wb", mtime=0, compresslevel=9
            ) as compressed,
            io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text,
        ):
            writer = csv.DictWriter(text, fieldnames=PAIR_FIELDS)
            writer.writeheader()
            for line_number, row in enumerate(_candidate_rows(candidate_path), start=2):
                if None in row or any(value is None for value in row.values()):
                    raise ValueError(f"line {line_number}: malformed candidate row")
                bill_id = row["bill_id"]
                if not bill_id:
                    raise ValueError(f"line {line_number}: missing bill_id")
                if bill_id in seen_ids:
                    raise ValueError(f"line {line_number}: duplicate bill_id {bill_id}")
                seen_ids.add(bill_id)
                titles = _titles(row, line_number)
                official, short = row["official_title"], row["short_title"]
                if not official and not short:
                    counts["missing_both"] += 1
                    continue
                if not official:
                    counts["missing_official_only"] += 1
                    continue
                if not short:
                    counts["missing_short_only"] += 1
                    continue
                official_evidence = _matching_evidence(
                    titles, "official", official, line_number
                )
                short_evidence = _matching_evidence(titles, "short", short, line_number)
                official_stages, short_stages = (
                    _stages(official_evidence),
                    _stages(short_evidence),
                )
                shared_stages = [
                    stage
                    for stage in official_stages
                    if stage is not None and stage in short_stages
                ]
                alignment = "shared_stage" if shared_stages else "no_shared_stage"
                counts["eligible_pairs"] += 1
                counts[alignment] += 1
                writer.writerow(
                    {
                        "source_path": row["source_path"],
                        "bill_id": bill_id,
                        "congress": row["congress"],
                        "bill_type": row["bill_type"],
                        "number": row["number"],
                        "introduced_at": row["introduced_at"],
                        "updated_at": row["updated_at"],
                        "subjects_top_term": row["subjects_top_term"],
                        "canonical_official_title": official,
                        "canonical_short_title": short,
                        "official_title_source": "top_level",
                        "short_title_source": "top_level",
                        "popular_title_comparison": row["popular_title"],
                        "titles_json": row["titles_json"],
                        "official_matching_evidence_json": _json(official_evidence),
                        "short_matching_evidence_json": _json(short_evidence),
                        "official_matching_stages_json": _json(official_stages),
                        "short_matching_stages_json": _json(short_stages),
                        "shared_stages_json": _json(shared_stages),
                        "stage_alignment_status": alignment,
                    }
                )
        total = (
            sum(counts.values()) - counts["shared_stage"] - counts["no_shared_stage"]
        )
        if total != len(seen_ids):
            raise AssertionError("canonical selection denominators do not reconcile")
        summary: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "rule_version": RULE_VERSION,
            "decision": DECISION,
            "input_path": _relative_path(summary_path, candidate_path),
            "output_path": output.name,
            "total_input": total,
            "eligible_pairs": counts["eligible_pairs"],
            "missing_official_only": counts["missing_official_only"],
            "missing_short_only": counts["missing_short_only"],
            "missing_both": counts["missing_both"],
            "shared_stage": counts["shared_stage"],
            "no_shared_stage": counts["no_shared_stage"],
            "output_gzip_sha256": sha256_file(output_temp),
            "output_csv_sha256": sha256_gzip_payload(output_temp),
            "compression": compression_metadata(),
        }
        summary_temp.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(output_temp, output)
        os.replace(summary_temp, summary_path)
        validate_published_output(output)
        return summary
    except zlib.error as error:
        output_temp.unlink(missing_ok=True)
        summary_temp.unlink(missing_ok=True)
        output.unlink(missing_ok=True)
        summary_path.unlink(missing_ok=True)
        raise ValueError(
            f"malformed or truncated gzip payload: {candidate_path}"
        ) from error
    except BaseException:
        output_temp.unlink(missing_ok=True)
        summary_temp.unlink(missing_ok=True)
        output.unlink(missing_ok=True)
        summary_path.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Select canonical top-level title pairs."
    )
    parser.add_argument("candidate_path", type=Path)
    parser.add_argument(
        "--output", type=Path, default=Path("data/processed/title_pairs.csv.gz")
    )
    args = parser.parse_args()
    print(
        json.dumps(
            canonicalize_candidates(args.candidate_path, args.output), sort_keys=True
        )
    )


if __name__ == "__main__":
    main()
