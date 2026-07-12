"""Streaming Gate 3 title metrics with a transparent, deterministic contract."""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import os
import re
import tempfile
import zlib
from collections import Counter
from importlib.metadata import version
from pathlib import Path
from typing import Any, cast

import textstat

from bill_titles.clean import (
    _validate_compression,
    compression_metadata,
    sha256_file,
    sha256_gzip_payload,
    validate_published_output,
)
from bill_titles.lexicons import LEXICON_VERSION, LEXICONS, validate_lexicons

SCHEMA_VERSION = "3"
RULE_VERSION = "2"
TOKENIZER_VERSION = "2"
READABILITY_VERSION = version("textstat")
REQUIRED_FIELDS = {"bill_id", "canonical_official_title", "canonical_short_title"}
SUMMARY_FIELDS = {
    "schema_version",
    "tokenizer_version",
    "lexicon_version",
    "rule_version",
    "readability_version",
    "input_rows",
    "output_rows",
    "eligibility_counts",
    "candidate_counts",
    "stage_alignment_counts",
    "input_gzip_sha256",
    "input_csv_sha256",
    "output_gzip_sha256",
    "output_csv_sha256",
    "compression",
}
ELIGIBILITY_FIELDS = {"readability_both_eligible_5", "readability_both_eligible_10"}
CANDIDATE_FIELDS = {
    "surface_simplification_candidate",
    "values_framing_candidate",
    "threat_framing_candidate",
    "mechanism_obscuring_candidate",
}
# A token is a run of Unicode letters or digits; internal straight/smart apostrophes,
# hyphens, and dotted acronym periods are retained. Punctuation otherwise separates.
TOKEN_RE = re.compile(r"[^\W_]+(?:[.'’\-][^\W_]+|\.(?=[^\W_]))*", re.UNICODE)


def tokenize(text: str | None) -> list[str]:
    """Return documented Unicode-aware tokens without external tokenizer resources."""
    if not isinstance(text, str):
        return []
    tokens: list[str] = []
    for match in TOKEN_RE.finditer(text):
        token = match.group()
        # Keep the terminal dot of a dotted acronym (U.S.A.), but not prose punctuation.
        if "." in token and match.end() < len(text) and text[match.end()] == ".":
            token += "."
        tokens.append(token)
    return tokens


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _title_metrics(text: str) -> dict[str, Any]:
    tokens = tokenize(text)
    alpha = [token for token in tokens if any(char.isalpha() for char in token)]
    normalized = [token.casefold() for token in alpha]
    result: dict[str, Any] = {
        "word_count": len(tokens),
        "alphabetic_token_count": len(alpha),
        "char_count_including_whitespace": len(text),
        "mean_alphabetic_token_length": (
            sum(sum(c.isalpha() for c in t) for t in alpha) / len(alpha)
            if alpha
            else None
        ),
    }
    acronym = [
        token
        for token in alpha
        if sum(c.isalpha() for c in token) >= 2
        and "".join(c for c in token if c.isalpha()).isupper()
    ]
    result["acronym_count"] = len(acronym)
    result["acronym_density"] = len(acronym) / len(alpha) if alpha else None
    for category, terms in LEXICONS.items():
        matched = [
            token
            for token, normalized_token in zip(alpha, normalized, strict=True)
            if normalized_token in terms
        ]
        result[f"{category}_count"] = len(matched)
        result[f"{category}_terms_json"] = _json(matched)
        result[f"{category}_density"] = len(matched) / len(alpha) if alpha else None
    result["readability_eligible_5"] = len(alpha) >= 5
    result["readability_eligible_10"] = len(alpha) >= 10
    if result["readability_eligible_5"]:
        try:
            result["flesch_reading_ease"] = textstat.flesch_reading_ease(text)
            result["flesch_kincaid_grade"] = textstat.flesch_kincaid_grade(text)
            result["readability_missing_reason"] = None
        except (ArithmeticError, ValueError, TypeError) as error:
            result["flesch_reading_ease"] = None
            result["flesch_kincaid_grade"] = None
            result["readability_missing_reason"] = type(error).__name__
    else:
        result["flesch_reading_ease"] = None
        result["flesch_kincaid_grade"] = None
        result["readability_missing_reason"] = "fewer_than_5_alphabetic_tokens"
    return result


def compute_pair_metrics(official_title: str, short_title: str) -> dict[str, Any]:
    """Compute title metrics; deltas are official minus short unless named otherwise."""
    official, short = _title_metrics(official_title), _title_metrics(short_title)
    result: dict[str, Any] = {}
    for prefix, values in (("official", official), ("short", short)):
        result.update({f"{prefix}_{key}": value for key, value in values.items()})
    for key in (
        "word_count",
        "alphabetic_token_count",
        "char_count_including_whitespace",
        "acronym_count",
        "legalese_count",
        "mechanism_concrete_count",
        "broad_action_count",
        "values_core_count",
        "values_contextual_count",
        "threat_core_count",
        "threat_contextual_count",
    ):
        result[f"{key}_delta_official_minus_short"] = official[key] - short[key]
    result["compression_ratio_official_over_short"] = (
        official["word_count"] / short["word_count"] if short["word_count"] else None
    )
    both_5 = bool(
        official["readability_eligible_5"] and short["readability_eligible_5"]
    )
    result["readability_both_eligible_5"] = both_5
    result["readability_both_eligible_10"] = bool(
        official["readability_eligible_10"] and short["readability_eligible_10"]
    )
    for score in ("flesch_reading_ease", "flesch_kincaid_grade"):
        result[f"{score}_delta_official_minus_short"] = (
            official[score] - short[score]
            if both_5 and official[score] is not None and short[score] is not None
            else None
        )
    for name, comparator in (
        ("mean_alphabetic_token_length", lambda a, b: b < a),
        ("legalese_density", lambda a, b: b < a),
        ("acronym_density", lambda a, b: b < a),
    ):
        available = official[name] is not None and short[name] is not None
        result[f"surface_proxy_{name}_available"] = available
        result[f"surface_proxy_{name}_improved"] = bool(
            available and comparator(official[name], short[name])
        )
    readability_available = (
        both_5
        and official["flesch_reading_ease"] is not None
        and short["flesch_reading_ease"] is not None
    )
    result["surface_proxy_flesch_reading_ease_available"] = readability_available
    result["surface_proxy_flesch_reading_ease_improved"] = bool(
        readability_available
        and short["flesch_reading_ease"] > official["flesch_reading_ease"]
    )
    available_keys = [
        key
        for key in result
        if key.startswith("surface_proxy_") and key.endswith("_available")
    ]
    improved_keys = [
        key
        for key in result
        if key.startswith("surface_proxy_") and key.endswith("_improved")
    ]
    result["surface_proxy_available_count"] = sum(result[key] for key in available_keys)
    result["surface_proxy_improvement_count"] = sum(
        result[key] for key in improved_keys
    )
    result["surface_simplification_candidate"] = bool(
        official["word_count"] > short["word_count"]
        and result["surface_proxy_improvement_count"] >= 2
    )
    for category in ("values", "threat"):
        result[f"{category}_framing_candidate"] = (
            short[f"{category}_core_count"] - official[f"{category}_core_count"] > 0
        )
    result["mechanism_obscuring_candidate"] = bool(
        short["broad_action_count"] > 0
        and official["mechanism_concrete_count"] > short["mechanism_concrete_count"]
    )
    return result


METRIC_FIELDS = tuple(compute_pair_metrics("", ""))


def _serialized_boolean_fields(fieldnames: list[str]) -> set[str]:
    return {
        field
        for field in fieldnames
        if field in ELIGIBILITY_FIELDS | CANDIDATE_FIELDS
        or (
            field.startswith(("official_", "short_"))
            and field.endswith(("readability_eligible_5", "readability_eligible_10"))
        )
        or (
            field.startswith("surface_proxy_")
            and field.endswith(("_available", "_improved"))
        )
    }


def validate_metrics_output(output: Path) -> dict[str, object]:
    """Validate completed Gate 3 output and its summary-last completion marker."""
    output = Path(output)
    summary_path = output.with_suffix(".summary.json")
    if not output.is_file() or not summary_path.is_file():
        raise ValueError("metrics data and summary completion marker are required")
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("metrics summary is malformed") from error
    if not isinstance(summary, dict):
        raise ValueError("metrics summary must be an object")
    if set(summary) != SUMMARY_FIELDS:
        raise ValueError("metrics summary schema is missing or has unknown fields")
    if summary["schema_version"] != SCHEMA_VERSION:
        raise ValueError("metrics summary schema version is unsupported")
    versions = {
        "tokenizer_version": TOKENIZER_VERSION,
        "lexicon_version": LEXICON_VERSION,
        "rule_version": RULE_VERSION,
        "readability_version": READABILITY_VERSION,
    }
    if any(summary[key] != expected for key, expected in versions.items()):
        raise ValueError("metrics summary version fields are malformed")
    for field in (
        "input_gzip_sha256",
        "input_csv_sha256",
        "output_gzip_sha256",
        "output_csv_sha256",
    ):
        if not isinstance(summary[field], str) or not re.fullmatch(
            r"[0-9a-f]{64}", summary[field]
        ):
            raise ValueError(f"metrics summary {field} is malformed")
    _validate_compression(summary["compression"], "metrics")
    if sha256_file(output) != summary["output_gzip_sha256"]:
        raise ValueError("metrics output gzip checksum does not match summary")
    if sha256_gzip_payload(output) != summary["output_csv_sha256"]:
        raise ValueError("metrics output CSV checksum does not match summary")
    input_rows, output_rows = summary["input_rows"], summary["output_rows"]
    if (
        not isinstance(input_rows, int)
        or isinstance(input_rows, bool)
        or input_rows < 0
        or not isinstance(output_rows, int)
        or isinstance(output_rows, bool)
        or output_rows < 0
        or input_rows != output_rows
    ):
        raise ValueError("metrics row counts are malformed or do not reconcile")
    for field, expected in (
        ("eligibility_counts", ELIGIBILITY_FIELDS),
        ("candidate_counts", CANDIDATE_FIELDS),
    ):
        values = summary[field]
        if not isinstance(values, dict) or set(values) != expected:
            raise ValueError(f"metrics {field} schema is malformed")
        if any(
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
            or value > output_rows
            for value in values.values()
        ):
            raise ValueError(f"metrics {field} values are malformed")
    alignment = summary["stage_alignment_counts"]
    if (
        not isinstance(alignment, dict)
        or any(
            not isinstance(key, str)
            or not key
            or not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
            or value > output_rows
            for key, value in alignment.items()
        )
        or sum(alignment.values()) != output_rows
    ):
        raise ValueError("metrics stage alignment counts are malformed")
    actual_eligibility: Counter[str] = Counter(dict.fromkeys(ELIGIBILITY_FIELDS, 0))
    actual_candidates: Counter[str] = Counter(dict.fromkeys(CANDIDATE_FIELDS, 0))
    actual_alignment: Counter[str] = Counter()
    seen: set[str] = set()
    try:
        with gzip.open(output, "rt", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames
            if fieldnames is None or len(fieldnames) != len(set(fieldnames)):
                raise ValueError("metrics data header is missing or malformed")
            required_output_fields = REQUIRED_FIELDS | set(METRIC_FIELDS)
            if not required_output_fields <= set(fieldnames):
                missing = sorted(required_output_fields - set(fieldnames))
                raise ValueError(
                    f"metrics data header is missing required fields: {missing}"
                )
            boolean_fields = _serialized_boolean_fields(list(fieldnames))
            rows = 0
            for line, row in enumerate(reader, 2):
                if None in row or any(
                    row.get(field) is None for field in required_output_fields
                ):
                    raise ValueError(f"line {line}: metrics row is malformed")
                identifier = row["bill_id"]
                if not identifier or identifier in seen:
                    raise ValueError(
                        f"line {line}: missing or duplicate bill_id {identifier}"
                    )
                if (
                    not row["canonical_official_title"]
                    or not row["canonical_short_title"]
                ):
                    raise ValueError(f"line {line}: canonical titles must be nonempty")
                seen.add(identifier)
                for field in boolean_fields:
                    if row[field] not in {"True", "False"}:
                        raise ValueError(
                            f"line {line}: malformed boolean field {field}"
                        )
                for key in ELIGIBILITY_FIELDS:
                    actual_eligibility[key] += row[key] == "True"
                for key in CANDIDATE_FIELDS:
                    actual_candidates[key] += row[key] == "True"
                actual_alignment[row.get("stage_alignment_status") or "missing"] += 1
                rows += 1
    except ValueError:
        raise
    except (OSError, EOFError, csv.Error, UnicodeError, zlib.error) as error:
        raise ValueError("metrics data is missing or malformed") from error
    if rows != output_rows:
        raise ValueError("metrics data rows do not reconcile with summary")
    if dict(sorted(actual_eligibility.items())) != summary["eligibility_counts"]:
        raise ValueError("metrics eligibility_counts do not match data")
    if dict(sorted(actual_candidates.items())) != summary["candidate_counts"]:
        raise ValueError("metrics candidate_counts do not match data")
    if dict(sorted(actual_alignment.items())) != summary["stage_alignment_counts"]:
        raise ValueError("metrics stage alignment counts do not match data")
    return summary


def validate_metrics_lineage(
    output: Path, *, expected_input_path: Path, expected_input_csv_sha256: str
) -> dict[str, object]:
    """Validate metrics output and its caller-anchored canonical provenance."""
    summary = validate_metrics_output(output)
    if not isinstance(expected_input_csv_sha256, str) or not re.fullmatch(
        r"[0-9a-f]{64}", expected_input_csv_sha256
    ):
        raise ValueError("expected canonical input checksum is malformed")
    canonical = validate_published_output(Path(expected_input_path))
    if canonical["output_csv_sha256"] != expected_input_csv_sha256:
        raise ValueError("canonical input checksum does not match caller digest")
    if summary["input_csv_sha256"] != expected_input_csv_sha256:
        raise ValueError("metrics input CSV checksum does not match canonical input")
    if summary["input_gzip_sha256"] != sha256_file(Path(expected_input_path)):
        raise ValueError("metrics input gzip checksum does not match canonical input")
    return summary


def _temporary_path(output: Path) -> Path:
    descriptor, name = tempfile.mkstemp(
        dir=output.parent, prefix=f".{output.name}.", suffix=".tmp"
    )
    os.close(descriptor)
    return Path(name)


def write_metrics(input_path: Path, output: Path) -> dict[str, object]:
    """Validate input, stream metrics, and atomically publish data then summary."""
    input_path, output = Path(input_path), Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    summary_path = output.with_suffix(".summary.json")
    output.unlink(missing_ok=True)
    summary_path.unlink(missing_ok=True)
    output_temp, summary_temp = _temporary_path(output), _temporary_path(summary_path)
    eligibility_counts: Counter[str] = Counter(dict.fromkeys(ELIGIBILITY_FIELDS, 0))
    candidate_counts: Counter[str] = Counter(dict.fromkeys(CANDIDATE_FIELDS, 0))
    stage_alignment_counts: Counter[str] = Counter()
    seen: set[str] = set()
    try:
        input_summary = validate_published_output(input_path)
        validate_lexicons()
        with gzip.open(input_path, "rt", encoding="utf-8", newline="") as source:
            reader = csv.DictReader(source)
            if reader.fieldnames is None or not REQUIRED_FIELDS <= set(
                reader.fieldnames
            ):
                missing = sorted(REQUIRED_FIELDS - set(reader.fieldnames or []))
                raise ValueError(f"canonical input missing required fields: {missing}")
            canonical_fields = list(reader.fieldnames)
            if set(canonical_fields) & set(METRIC_FIELDS):
                raise ValueError("canonical input headers overlap metric fields")
            fieldnames = canonical_fields + list(METRIC_FIELDS)
            with (
                output_temp.open("wb") as raw,
                gzip.GzipFile(
                    filename="", fileobj=raw, mode="wb", mtime=0, compresslevel=9
                ) as compressed,
                io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text,
            ):
                writer = csv.DictWriter(text, fieldnames=fieldnames)
                writer.writeheader()
                for line, row in enumerate(reader, 2):
                    if None in row or any(value is None for value in row.values()):
                        raise ValueError(f"line {line}: malformed row")
                    identifier = row["bill_id"]
                    if not identifier or identifier in seen:
                        raise ValueError(
                            f"line {line}: missing or duplicate bill_id {identifier}"
                        )
                    if (
                        not row["canonical_official_title"]
                        or not row["canonical_short_title"]
                    ):
                        raise ValueError(
                            f"line {line}: canonical titles must be nonempty"
                        )
                    seen.add(identifier)
                    metrics = compute_pair_metrics(
                        row["canonical_official_title"], row["canonical_short_title"]
                    )
                    combined = row | metrics
                    writer.writerow(combined)
                    for key in (
                        "readability_both_eligible_5",
                        "readability_both_eligible_10",
                    ):
                        eligibility_counts[key] += bool(metrics[key])
                    for key in CANDIDATE_FIELDS:
                        candidate_counts[key] += bool(metrics[key])
                    alignment = row.get("stage_alignment_status", "missing")
                    stage_alignment_counts[alignment] += 1
        summary: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "tokenizer_version": TOKENIZER_VERSION,
            "lexicon_version": LEXICON_VERSION,
            "rule_version": RULE_VERSION,
            "readability_version": READABILITY_VERSION,
            "input_rows": len(seen),
            "output_rows": len(seen),
            "eligibility_counts": dict(sorted(eligibility_counts.items())),
            "candidate_counts": dict(sorted(candidate_counts.items())),
            "stage_alignment_counts": dict(sorted(stage_alignment_counts.items())),
            "input_gzip_sha256": input_summary["output_gzip_sha256"],
            "input_csv_sha256": input_summary["output_csv_sha256"],
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
        validate_metrics_lineage(
            output,
            expected_input_path=input_path,
            expected_input_csv_sha256=cast(str, input_summary["output_csv_sha256"]),
        )
        return summary
    except zlib.error as error:
        for path in (output_temp, summary_temp, output, summary_path):
            path.unlink(missing_ok=True)
        raise ValueError("malformed or truncated gzip payload") from error
    except BaseException:
        for path in (output_temp, summary_temp, output, summary_path):
            path.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute transparent Gate 3 title metrics."
    )
    parser.add_argument("input_path", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/title_pairs_with_metrics.csv.gz"),
    )
    args = parser.parse_args()
    print(json.dumps(write_metrics(args.input_path, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
