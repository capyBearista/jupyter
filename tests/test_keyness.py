import csv
import gzip
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

import pytest

import bill_titles.keyness as keyness_module
from bill_titles.clean import (
    DECISION,
    PAIR_FIELDS,
    compression_metadata,
    sha256_file,
    sha256_gzip_payload,
)
from bill_titles.keyness import (
    DOMAIN_TERM_EXCEPTIONS,
    STOPWORD_POLICY,
    validate_keyness_outputs,
    weighted_log_odds,
    write_keyness,
)
from bill_titles.metrics import tokenize


def _write_keyness_input(path: Path) -> None:
    fields = [
        "canonical_official_title",
        "canonical_short_title",
        "stage_alignment_status",
    ]
    rows = [
        {
            "canonical_official_title": " ".join(["Act"] * 25),
            "canonical_short_title": " ".join(["bill"] * 25),
            "stage_alignment_status": "shared_stage",
        },
        {
            "canonical_official_title": " ".join(["law"] * 5),
            "canonical_short_title": " ".join(["resolution"] * 5),
            "stage_alignment_status": "no_shared_stage",
        },
    ]
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    _write_keyness_sidecar(path, total_input=2, eligible_pairs=2, shared_stage=1)


def _write_keyness_sidecar(
    path: Path, *, total_input: int, eligible_pairs: int, shared_stage: int
) -> None:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        original_rows = list(csv.DictReader(handle))
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PAIR_FIELDS)
        writer.writeheader()
        for index, original in enumerate(original_rows, 1):
            row = dict.fromkeys(PAIR_FIELDS, "")
            row.update(
                {
                    "source_path": f"synthetic/{index}.json",
                    "bill_id": original.get("bill_id") or f"synthetic-{index}",
                    "congress": "118",
                    "bill_type": "hr",
                    "number": str(index),
                    "canonical_official_title": original.get(
                        "canonical_official_title", "Act"
                    ),
                    "canonical_short_title": original.get(
                        "canonical_short_title", "Act"
                    ),
                    "official_title_source": "top_level",
                    "short_title_source": "top_level",
                    "titles_json": "[]",
                    "official_matching_evidence_json": "[]",
                    "short_matching_evidence_json": "[]",
                    "official_matching_stages_json": "[]",
                    "short_matching_stages_json": "[]",
                    "shared_stages_json": "[]",
                    "stage_alignment_status": original.get(
                        "stage_alignment_status", "no_shared_stage"
                    ),
                }
            )
            if row["stage_alignment_status"] == "shared_stage":
                official = row["canonical_official_title"]
                short = row["canonical_short_title"]
                evidence = [
                    {"type": "official", "title": official, "as": "introduced"},
                    {"type": "short", "title": short, "as": "introduced"},
                ]
                row["titles_json"] = json.dumps(evidence)
                row["official_matching_evidence_json"] = json.dumps([evidence[0]])
                row["short_matching_evidence_json"] = json.dumps([evidence[1]])
                row["official_matching_stages_json"] = '["introduced"]'
                row["short_matching_stages_json"] = '["introduced"]'
                row["shared_stages_json"] = '["introduced"]'
            writer.writerow(row)
    path.with_suffix(".summary.json").write_text(
        json.dumps(
            {
                "schema_version": "3",
                "rule_version": "1",
                "decision": DECISION,
                "input_path": path.name,
                "output_path": path.name,
                "total_input": total_input,
                "eligible_pairs": eligible_pairs,
                "missing_official_only": 0,
                "missing_short_only": 0,
                "missing_both": 0,
                "shared_stage": shared_stage,
                "no_shared_stage": eligible_pairs - shared_stage,
                "output_gzip_sha256": sha256_file(path),
                "output_csv_sha256": sha256_gzip_payload(path),
                "compression": compression_metadata(),
            }
        ),
        encoding="utf-8",
    )


def test_hand_computed_pooled_prior_formula_and_direction() -> None:
    rows = weighted_log_odds(Counter(a=10, b=15), Counter(a=15, b=10))
    row = next(item for item in rows if item["token"] == "a")
    alpha0 = 50
    # alpha_a is pooled a=25; totals are 25 in each corpus.
    expected_delta = math.log((15 + 25) / (25 + alpha0 - 15 - 25)) - math.log(
        (10 + 25) / (25 + alpha0 - 10 - 25)
    )
    expected_variance = 1 / 40 + 1 / 35 + 1 / 35 + 1 / 40
    assert row["log_odds_delta"] == pytest.approx(expected_delta)
    assert row["variance"] == pytest.approx(expected_variance)
    assert row["z_score"] == pytest.approx(
        expected_delta / math.sqrt(expected_variance)
    )
    assert row["direction"] == "short"


def test_corpus_swap_negates_delta_and_z() -> None:
    left = weighted_log_odds(Counter(a=10, b=15), Counter(a=15, b=10))
    right = weighted_log_odds(Counter(a=15, b=10), Counter(a=10, b=15))
    for first, second in zip(left, right, strict=True):
        assert first["token"] == second["token"]
        assert first["log_odds_delta"] == pytest.approx(-second["log_odds_delta"])
        assert first["z_score"] == pytest.approx(-second["z_score"])


def test_minimum_count_boundary_and_zero_count_prior() -> None:
    official = Counter(common=24, eligible=1)
    short = Counter(eligible=24)
    rows = weighted_log_odds(official, short)
    assert {row["token"] for row in rows} == {"eligible"}
    rows = weighted_log_odds(Counter(eligible=25), Counter(other=25))
    assert {row["token"] for row in rows} == {"eligible", "other"}
    assert next(row for row in rows if row["token"] == "eligible")["short_count"] == 0


def test_tokenizer_integration_and_stopword_policy() -> None:
    assert tokenize("U.S.A.'s Act, bill") == ["U.S.A.", "s", "Act", "bill"]
    rows = weighted_log_odds(Counter(act=25, bill=1), Counter(act=1, bill=25))
    assert {row["token"] for row in rows} == {"act", "bill"}


def test_keyness_publish_and_validator_recompute_manifest(tmp_path: Path) -> None:
    input_path = tmp_path / "pairs.csv.gz"
    output_dir = tmp_path / "tables"
    _write_keyness_input(input_path)

    summary = write_keyness(input_path, output_dir)
    assert summary["stopword_exceptions"] == sorted(DOMAIN_TERM_EXCEPTIONS)
    digest = sha256_gzip_payload(input_path)
    assert summary["input_csv_sha256"] == digest
    assert summary["stopword_policy"] == STOPWORD_POLICY
    assert (
        validate_keyness_outputs(
            output_dir / "keyness_summary.json",
            expected_input_path=input_path,
            expected_input_csv_sha256=digest,
        )
        == summary
    )

    summary["subsets"]["all"]["eligible_term_count"] += 1
    (output_dir / "keyness_summary.json").write_text(
        json.dumps(summary), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="subset counts do not reconcile"):
        validate_keyness_outputs(
            output_dir / "keyness_summary.json",
            expected_input_path=input_path,
            expected_input_csv_sha256=digest,
        )


def test_keyness_validation_uses_absolute_trusted_paths_from_unrelated_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_path = tmp_path / "pairs.csv.gz"
    output_dir = tmp_path / "tables"
    _write_keyness_input(input_path)
    summary = write_keyness(input_path.resolve(), output_dir.resolve())
    assert summary["tables"]["all"]["path"] == "weighted_log_odds_unigrams.csv"
    assert summary["tables"]["shared_stage"]["path"] == (
        "weighted_log_odds_unigrams_shared_stage.csv"
    )
    monkeypatch.chdir(Path("/tmp"))

    validate_keyness_outputs(
        (output_dir / "keyness_summary.json").resolve(),
        expected_input_path=input_path.resolve(),
        expected_input_csv_sha256=sha256_gzip_payload(input_path),
    )


def test_keyness_rejects_internal_parent_input_path(tmp_path: Path) -> None:
    input_path = tmp_path / "pairs.csv.gz"
    output_dir = tmp_path / "tables"
    _write_keyness_input(input_path)
    write_keyness(input_path, output_dir)
    summary_path = output_dir / "keyness_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["input_path"] = "a/../pairs.csv.gz"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    with pytest.raises(ValueError, match="summary-relative path"):
        validate_keyness_outputs(
            summary_path,
            expected_input_path=input_path,
            expected_input_csv_sha256=sha256_gzip_payload(input_path),
        )


def test_keyness_validator_recomputes_table_arithmetic(tmp_path: Path) -> None:
    input_path = tmp_path / "pairs.csv.gz"
    output_dir = tmp_path / "tables"
    _write_keyness_input(input_path)
    write_keyness(input_path, output_dir)

    table = output_dir / "weighted_log_odds_unigrams.csv"
    rows = list(csv.DictReader(table.open(encoding="utf-8", newline="")))
    rows[0]["short_count"] = str(int(rows[0]["short_count"]) + 1)
    with table.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    summary_path = output_dir / "keyness_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["tables"]["all"]["sha256"] = hashlib.sha256(table.read_bytes()).hexdigest()
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    with pytest.raises(ValueError, match="table value does not match"):
        validate_keyness_outputs(
            summary_path,
            expected_input_path=input_path,
            expected_input_csv_sha256=sha256_gzip_payload(input_path),
        )


def test_keyness_validator_rejects_one_appended_row_with_updated_manifest(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "pairs.csv.gz"
    output_dir = tmp_path / "tables"
    _write_keyness_input(input_path)
    write_keyness(input_path, output_dir)

    table = output_dir / "weighted_log_odds_unigrams.csv"
    with table.open("a", encoding="utf-8", newline="") as handle:
        handle.write(",".join(["extra"] * len(keyness_module.TABLE_FIELDS)) + "\n")
    summary_path = output_dir / "keyness_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["tables"]["all"]["sha256"] = hashlib.sha256(table.read_bytes()).hexdigest()
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    with pytest.raises(ValueError, match="table value does not match|extra rows"):
        validate_keyness_outputs(
            summary_path,
            expected_input_path=input_path,
            expected_input_csv_sha256=sha256_gzip_payload(input_path),
        )


def test_validator_requires_trusted_input_and_rejects_substituted_generation(
    tmp_path: Path,
) -> None:
    input_a = tmp_path / "a.csv.gz"
    input_b = tmp_path / "b.csv.gz"
    output_a = tmp_path / "a_tables"
    output_b = tmp_path / "b_tables"
    _write_keyness_input(input_a)
    _write_keyness_input(input_b)
    payload = gzip.decompress(input_b.read_bytes())
    with input_b.open("wb") as raw:
        with gzip.GzipFile(
            filename="", fileobj=raw, mode="wb", mtime=1, compresslevel=9
        ) as compressed:
            compressed.write(payload)
    _write_keyness_sidecar(input_b, total_input=2, eligible_pairs=2, shared_stage=1)
    # Rebuild the sidecar after recompression; the payload identity is unchanged.
    assert input_a.read_bytes() != input_b.read_bytes()
    assert sha256_gzip_payload(input_a) == sha256_gzip_payload(input_b)
    write_keyness(input_a, output_a)
    write_keyness(input_b, output_b)
    validate_keyness_outputs(
        output_b / "keyness_summary.json",
        expected_input_path=input_b,
        expected_input_csv_sha256=sha256_gzip_payload(input_a),
    )
    assert (output_a / "weighted_log_odds_unigrams.csv").read_bytes() == (
        output_b / "weighted_log_odds_unigrams.csv"
    ).read_bytes()


def test_header_only_input_publishes_and_validates_empty_tables(tmp_path: Path) -> None:
    input_path = tmp_path / "empty.csv.gz"
    fields = [
        "canonical_official_title",
        "canonical_short_title",
        "stage_alignment_status",
    ]
    with gzip.open(input_path, "wt", encoding="utf-8", newline="") as handle:
        csv.DictWriter(handle, fieldnames=fields).writeheader()
    # A header-only canonical table still has a complete schema-2 sidecar.
    _write_keyness_sidecar(input_path, total_input=0, eligible_pairs=0, shared_stage=0)
    output_dir = tmp_path / "tables"
    summary = write_keyness(input_path, output_dir)
    digest = sha256_gzip_payload(input_path)
    assert summary["subsets"]["all"]["eligible_term_count"] == 0
    assert summary["subsets"]["shared_stage"]["eligible_term_count"] == 0
    for table in summary["tables"].values():
        assert table["row_count"] == 0
    validate_keyness_outputs(
        output_dir / "keyness_summary.json",
        expected_input_path=input_path,
        expected_input_csv_sha256=digest,
    )


@pytest.mark.parametrize("failure_number", [2, 3])
def test_publication_replace_failure_removes_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_number: int
) -> None:
    input_path = tmp_path / "pairs.csv.gz"
    output_dir = tmp_path / "tables"
    _write_keyness_input(input_path)
    output_dir.mkdir()
    (output_dir / "keyness_summary.json").write_text("stale", encoding="utf-8")
    for name in (
        "weighted_log_odds_unigrams.csv",
        "weighted_log_odds_unigrams_shared_stage.csv",
    ):
        (output_dir / name).write_text("stale", encoding="utf-8")

    original_replace = keyness_module.os.replace
    calls = 0

    def fail_replace(source: str | bytes, destination: str | bytes) -> None:
        nonlocal calls
        calls += 1
        if calls <= 2:
            assert not (output_dir / "keyness_summary.json").exists()
        if calls == failure_number:
            raise RuntimeError("injected publication failure")
        original_replace(source, destination)

    monkeypatch.setattr(keyness_module.os, "replace", fail_replace)
    with pytest.raises(RuntimeError, match="injected"):
        write_keyness(input_path, output_dir)
    assert not list(output_dir.glob(".*.tmp"))
    assert not list(output_dir.glob("weighted_log_odds_unigrams*.csv"))
    assert not (output_dir / "keyness_summary.json").exists()
