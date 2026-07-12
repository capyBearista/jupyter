"""Deterministic Gate 3 unigram keyness discovery.

This module is deliberately descriptive: its output is corpus-discovery evidence,
not a measure of importance, bias, intent, or comprehension.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import re
import tempfile
import zlib
from collections import Counter
from collections.abc import Iterable
from importlib.metadata import version
from pathlib import Path
from typing import cast

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

from bill_titles.clean import (
    _relative_path,
    _resolve_relative_path,
    sha256_file,
    validate_published_output,
)
from bill_titles.metrics import TOKENIZER_VERSION, tokenize

SCHEMA_VERSION = "4"
METHOD_VERSION = "1"
MIN_POOLED_COUNT = 25
STOPWORD_SET = frozenset(ENGLISH_STOP_WORDS)
STOPWORD_VERSION = version("scikit-learn")
STOPWORD_POLICY = (
    "scikit-learn ENGLISH_STOP_WORDS, exact token matches after casefolding"
)
STOPWORD_HASH = hashlib.sha256(
    "\n".join(sorted(STOPWORD_SET)).encode("utf-8")
).hexdigest()
DOMAIN_TERM_EXCEPTIONS = frozenset({"act", "bill", "law", "resolution"})
EFFECTIVE_STOPWORD_SET = STOPWORD_SET - DOMAIN_TERM_EXCEPTIONS
EFFECTIVE_STOPWORD_HASH = hashlib.sha256(
    "\n".join(sorted(EFFECTIVE_STOPWORD_SET)).encode("utf-8")
).hexdigest()
FORMULA = (
    "alpha_i=official_i+short_i; alpha_0=sum_i alpha_i; "
    "delta=log((short_i+alpha_i)/(N_short+alpha_0-short_i-alpha_i))"
    "-log((official_i+alpha_i)/(N_official+alpha_0-official_i-alpha_i)); "
    "variance=sum of four reciprocal posterior-bin terms; "
    "z=delta/sqrt(variance)"
)
TABLE_FIELDS = (
    "token",
    "official_count",
    "short_count",
    "pooled_count",
    "official_normalized_rate",
    "short_normalized_rate",
    "log_odds_delta",
    "variance",
    "z_score",
    "direction",
    "short_rank",
    "official_rank",
)
SUMMARY_FIELDS = {
    "schema_version",
    "method",
    "method_version",
    "formula",
    "tokenizer_version",
    "stopword_policy",
    "stopword_version",
    "stopword_base_hash",
    "stopword_base_count",
    "stopword_exceptions",
    "stopword_hash",
    "stopword_count",
    "min_pooled_count",
    "input_path",
    "input_csv_sha256",
    "subsets",
    "tables",
}


def _tokens(text: str) -> list[str]:
    return [
        token.casefold()
        for token in tokenize(text)
        if any(char.isalpha() for char in token)
        and token.casefold() not in EFFECTIVE_STOPWORD_SET
    ]


def weighted_log_odds(
    official: Counter[str], short: Counter[str]
) -> list[dict[str, object]]:
    """Return Monroe-style informative-Dirichlet unigram statistics.

    The prior is the pooled token-count vector (alpha_i = pooled_i), with
    alpha_0 equal to the pooled post-stopword token total.  Delta is short
    log-odds minus official log-odds; its variance is the sum of the four
    posterior-binomial reciprocal terms.
    """
    official_total, short_total = sum(official.values()), sum(short.values())
    pooled = official + short
    total_prior = sum(pooled.values())
    rows: list[dict[str, object]] = []
    for token in sorted(pooled):
        pooled_count = pooled[token]
        if pooled_count < MIN_POOLED_COUNT:
            continue
        alpha = pooled_count
        short_other = short_total + total_prior - short[token] - alpha
        official_other = official_total + total_prior - official[token] - alpha
        if short_other <= 0 or official_other <= 0:
            raise ValueError("keyness requires a nonzero complementary token mass")
        short_logit = math.log((short[token] + alpha) / short_other)
        official_logit = math.log((official[token] + alpha) / official_other)
        variance = (
            1 / (short[token] + alpha)
            + 1 / short_other
            + 1 / (official[token] + alpha)
            + 1 / official_other
        )
        delta = short_logit - official_logit
        rows.append(
            {
                "token": token,
                "official_count": official[token],
                "short_count": short[token],
                "pooled_count": pooled_count,
                "official_normalized_rate": official[token] / official_total
                if official_total
                else 0.0,
                "short_normalized_rate": short[token] / short_total
                if short_total
                else 0.0,
                "log_odds_delta": delta,
                "variance": variance,
                "z_score": delta / math.sqrt(variance),
            }
        )
    rows.sort(key=lambda row: str(row["token"]))
    short_order = sorted(
        rows, key=lambda row: (-float(cast(float, row["z_score"])), str(row["token"]))
    )
    official_order = sorted(
        rows, key=lambda row: (float(cast(float, row["z_score"])), str(row["token"]))
    )
    short_ranks = {row["token"]: i for i, row in enumerate(short_order, 1)}
    official_ranks = {row["token"]: i for i, row in enumerate(official_order, 1)}
    for row in rows:
        z = float(cast(float, row["z_score"]))
        row["direction"] = "short" if z > 0 else "official" if z < 0 else "tie"
        row["short_rank"] = short_ranks[row["token"]]
        row["official_rank"] = official_ranks[row["token"]]
    return rows


def _read_subset(
    path: Path, subset: str
) -> tuple[Counter[str], Counter[str], dict[str, int]]:
    validate_published_output(path)
    official: Counter[str] = Counter()
    short: Counter[str] = Counter()
    pairs = pre = post = excluded = 0
    try:
        with gzip.open(path, "rt", encoding="utf-8", newline="") as source:
            reader = csv.DictReader(source)
            required = {
                "canonical_official_title",
                "canonical_short_title",
                "stage_alignment_status",
            }
            if reader.fieldnames is None or not required <= set(reader.fieldnames):
                raise ValueError("canonical input is missing keyness fields")
            for line, row in enumerate(reader, 2):
                status = row["stage_alignment_status"]
                if status not in {"shared_stage", "no_shared_stage"}:
                    raise ValueError(f"line {line}: malformed stage alignment status")
                if subset == "shared_stage" and status != subset:
                    continue
                pairs += 1
                for text, counter in (
                    (row["canonical_official_title"], official),
                    (row["canonical_short_title"], short),
                ):
                    raw = [
                        token
                        for token in tokenize(text)
                        if any(char.isalpha() for char in token)
                    ]
                    pre += len(raw)
                    kept = _tokens(text)
                    post += len(kept)
                    excluded += len(raw) - len(kept)
                    counter.update(kept)
    except (gzip.BadGzipFile, EOFError, OSError, UnicodeError, zlib.error) as error:
        raise ValueError("malformed or truncated gzip payload") from error
    return (
        official,
        short,
        {
            "pair_count": pairs,
            "pre_stopword_tokens": pre,
            "post_stopword_tokens": post,
            "excluded_stopword_tokens": excluded,
        },
    )


def _write_table(path: Path, rows: Iterable[dict[str, object]]) -> str:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TABLE_FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    field: f"{row[field]:.17g}"
                    if isinstance(row[field], float)
                    else row[field]
                    for field in TABLE_FIELDS
                }
            )
    return sha256_file(path)


def validate_keyness_outputs(
    summary_path: Path,
    *,
    expected_input_path: Path,
    expected_input_csv_sha256: str,
) -> dict[str, object]:
    """Validate keyness artifacts against caller-trusted canonical input."""
    summary_path = Path(summary_path)
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("keyness summary is malformed") from error
    if not isinstance(summary, dict) or set(summary) != SUMMARY_FIELDS:
        raise ValueError("keyness summary schema is malformed")
    if (
        summary["schema_version"] != SCHEMA_VERSION
        or summary["method_version"] != METHOD_VERSION
    ):
        raise ValueError("unsupported keyness version")
    if (
        summary["method"]
        != "Monroe-style weighted log-odds with pooled informative Dirichlet prior"
        or summary["formula"] != FORMULA
    ):
        raise ValueError("keyness method metadata is malformed")
    if (
        summary["stopword_version"] != STOPWORD_VERSION
        or summary["stopword_policy"] != STOPWORD_POLICY
    ):
        raise ValueError("stopword metadata mismatch")
    if (
        summary["stopword_base_hash"] != STOPWORD_HASH
        or summary["stopword_base_count"] != len(STOPWORD_SET)
        or summary["stopword_exceptions"] != sorted(DOMAIN_TERM_EXCEPTIONS)
        or summary["stopword_hash"] != EFFECTIVE_STOPWORD_HASH
        or summary["stopword_count"] != len(EFFECTIVE_STOPWORD_SET)
        or summary["tokenizer_version"] != TOKENIZER_VERSION
        or summary["min_pooled_count"] != MIN_POOLED_COUNT
    ):
        raise ValueError("keyness contract metadata mismatch")
    if not isinstance(summary["input_csv_sha256"], str) or not re.fullmatch(
        r"[0-9a-f]{64}", expected_input_csv_sha256
    ):
        raise ValueError("keyness input checksum is malformed")
    if _resolve_relative_path(
        summary_path, summary["input_path"], filename=False
    ) != Path(expected_input_path).resolve(strict=False):
        raise ValueError("keyness input path does not match trusted expected input")
    canonical_summary = validate_published_output(Path(expected_input_path))
    if (
        canonical_summary["output_csv_sha256"] != expected_input_csv_sha256
        or summary["input_csv_sha256"] != expected_input_csv_sha256
    ):
        raise ValueError("keyness input checksum does not match trusted input")
    if not isinstance(summary["subsets"], dict) or set(summary["subsets"]) != {
        "all",
        "shared_stage",
    }:
        raise ValueError("keyness subset manifest is malformed")
    if not isinstance(summary["tables"], dict) or set(summary["tables"]) != {
        "all",
        "shared_stage",
    }:
        raise ValueError("keyness table manifest is malformed")
    expected_subsets = {
        name: _read_subset(Path(expected_input_path), name)
        for name in ("all", "shared_stage")
    }
    subset_fields = {
        "pair_count",
        "pre_stopword_tokens",
        "post_stopword_tokens",
        "excluded_stopword_tokens",
        "official_tokens",
        "short_tokens",
        "vocabulary_size",
        "eligible_term_count",
    }
    for name, (official, short, counts) in expected_subsets.items():
        actual = summary["subsets"][name]
        if not isinstance(actual, dict) or set(actual) != subset_fields:
            raise ValueError("keyness subset manifest is malformed")
        expected = {
            **counts,
            "official_tokens": sum(official.values()),
            "short_tokens": sum(short.values()),
            "vocabulary_size": len(official | short),
            "eligible_term_count": len(weighted_log_odds(official, short)),
        }
        if any(
            not isinstance(actual[key], int)
            or isinstance(actual[key], bool)
            or actual[key] != expected[key]
            for key in expected
        ):
            raise ValueError("keyness subset counts do not reconcile with input")
    for name, info in summary["tables"].items():
        if not isinstance(info, dict) or set(info) != {
            "path",
            "sha256",
            "row_count",
            "eligible_term_count",
        }:
            raise ValueError("keyness table manifest entry is malformed")
        if (
            not isinstance(info["path"], str)
            or not isinstance(info["sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", info["sha256"])
        ):
            raise ValueError("keyness table manifest entry types are malformed")
        if any(
            not isinstance(info[field], int)
            or isinstance(info[field], bool)
            or info[field] < 0
            for field in ("row_count", "eligible_term_count")
        ):
            raise ValueError("keyness table manifest entry types are malformed")
        expected_filename = (
            "weighted_log_odds_unigrams.csv"
            if name == "all"
            else "weighted_log_odds_unigrams_shared_stage.csv"
        )
        if info["path"] != expected_filename:
            raise ValueError("keyness table path must be an exact filename")
        path = _resolve_relative_path(summary_path, info["path"], filename=True)
        if not path.is_file() or sha256_file(path) != info["sha256"]:
            raise ValueError(f"keyness checksum mismatch: {path}")
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != list(TABLE_FIELDS):
                raise ValueError("keyness table header is malformed")
            official, short, _ = expected_subsets[name]
            expected_rows = weighted_log_odds(official, short)
            if info["row_count"] != len(expected_rows) or info[
                "eligible_term_count"
            ] != len(expected_rows):
                raise ValueError("keyness row count does not reconcile")
            for expected in expected_rows:
                row = next(reader, None)
                if row is None:
                    raise ValueError("keyness table is missing rows")
                if None in row.values() or set(row) != set(TABLE_FIELDS):
                    raise ValueError("keyness row is malformed")
                for field in TABLE_FIELDS:
                    value = expected[field]
                    serialized = (
                        f"{value:.17g}" if isinstance(value, float) else str(value)
                    )
                    if row[field] != serialized:
                        raise ValueError(
                            "keyness table value does not match input arithmetic"
                        )
            if next(reader, None) is not None:
                raise ValueError("keyness table has extra rows")
    return summary


def write_keyness(
    input_path: Path, output_dir: Path = Path("reports/tables")
) -> dict[str, object]:
    input_path, output_dir = Path(input_path), Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "keyness_summary.json"
    final_tables = {
        "all": output_dir / "weighted_log_odds_unigrams.csv",
        "shared_stage": output_dir / "weighted_log_odds_unigrams_shared_stage.csv",
    }
    temps: list[Path] = []
    summary_temp: Path | None = None
    try:
        canonical_summary = validate_published_output(input_path)
        input_csv_sha256 = cast(str, canonical_summary["output_csv_sha256"])
        # The summary is the completion marker: remove it before touching either
        # data table, and do not publish it until both tables are complete.
        summary_path.unlink(missing_ok=True)
        for table in final_tables.values():
            table.unlink(missing_ok=True)
        for table in final_tables.values():
            descriptor, name = tempfile.mkstemp(
                dir=output_dir, prefix=f".{table.name}.", suffix=".tmp"
            )
            os.close(descriptor)
            temps.append(Path(name))
        descriptor, name = tempfile.mkstemp(
            dir=output_dir, prefix=f".{summary_path.name}.", suffix=".tmp"
        )
        os.close(descriptor)
        summary_temp = Path(name)
        subsets: dict[str, object] = {}
        tables: dict[str, object] = {}
        for (subset, table), temp in zip(final_tables.items(), temps, strict=True):
            official, short, counts = _read_subset(input_path, subset)
            rows = weighted_log_odds(official, short)
            checksum = _write_table(temp, rows)
            subsets[subset] = {
                **counts,
                "official_tokens": sum(official.values()),
                "short_tokens": sum(short.values()),
                "vocabulary_size": len(official | short),
                "eligible_term_count": len(rows),
            }
            tables[subset] = {
                "path": table.name,
                "sha256": checksum,
                "row_count": len(rows),
                "eligible_term_count": len(rows),
            }
        summary = {
            "schema_version": SCHEMA_VERSION,
            "method": (
                "Monroe-style weighted log-odds with pooled informative Dirichlet prior"
            ),
            "method_version": METHOD_VERSION,
            "formula": FORMULA,
            "tokenizer_version": TOKENIZER_VERSION,
            "stopword_policy": STOPWORD_POLICY,
            "stopword_version": STOPWORD_VERSION,
            "stopword_base_hash": STOPWORD_HASH,
            "stopword_base_count": len(STOPWORD_SET),
            "stopword_exceptions": sorted(DOMAIN_TERM_EXCEPTIONS),
            "stopword_hash": EFFECTIVE_STOPWORD_HASH,
            "stopword_count": len(EFFECTIVE_STOPWORD_SET),
            "min_pooled_count": MIN_POOLED_COUNT,
            "input_path": _relative_path(summary_path, input_path),
            "input_csv_sha256": input_csv_sha256,
            "subsets": subsets,
            "tables": tables,
        }
        summary_temp.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        for temp, table in zip(temps, final_tables.values(), strict=True):
            os.replace(temp, table)
        os.replace(summary_temp, summary_path)
        validate_keyness_outputs(
            summary_path,
            expected_input_path=input_path,
            expected_input_csv_sha256=input_csv_sha256,
        )
        return summary
    except zlib.error as error:
        for path in (*temps, summary_path, *final_tables.values()):
            path.unlink(missing_ok=True)
        if summary_temp is not None:
            summary_temp.unlink(missing_ok=True)
        raise ValueError("malformed or truncated gzip payload") from error
    except BaseException:
        for path in (*temps, summary_path, *final_tables.values()):
            path.unlink(missing_ok=True)
        if summary_temp is not None:
            summary_temp.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Publish Gate 3 unigram keyness tables."
    )
    parser.add_argument("input_path", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("reports/tables"))
    args = parser.parse_args()
    print(json.dumps(write_keyness(args.input_path, args.output_dir), sort_keys=True))


if __name__ == "__main__":
    main()
