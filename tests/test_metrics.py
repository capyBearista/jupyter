import csv
import gzip
import hashlib
import io
import json
from pathlib import Path

import pytest

from bill_titles.clean import DECISION, PAIR_FIELDS, sha256_gzip_payload
from bill_titles.lexicons import LEXICON_VERSION, LEXICONS, validate_lexicons
from bill_titles.metrics import (
    METRIC_FIELDS,
    TOKENIZER_VERSION,
    compute_pair_metrics,
    tokenize,
    validate_metrics_lineage,
    validate_metrics_output,
    write_metrics,
)


def _write_canonical_sidecar(path: Path) -> None:
    from bill_titles.clean import compression_metadata, sha256_file, sha256_gzip_payload

    path.with_suffix(".summary.json").write_text(
        json.dumps(
            {
                "schema_version": "2",
                "rule_version": "1",
                "decision": "synthetic",
                "input_path": "synthetic",
                "output_path": str(path),
                "total_input": 0,
                "eligible_pairs": 0,
                "missing_official_only": 0,
                "missing_short_only": 0,
                "missing_both": 0,
                "shared_stage": 0,
                "no_shared_stage": 0,
                "output_gzip_sha256": sha256_file(path),
                "output_csv_sha256": sha256_gzip_payload(path),
                "compression": compression_metadata(),
            }
        ),
        encoding="utf-8",
    )


def _write_minimal_canonical_sidecar(path: Path) -> None:
    from bill_titles.clean import compression_metadata, sha256_file, sha256_gzip_payload

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
    shared = sum(
        row.get("stage_alignment_status") == "shared_stage" for row in original_rows
    )
    count = len(original_rows)
    path.with_suffix(".summary.json").write_text(
        json.dumps(
            {
                "schema_version": "3",
                "rule_version": "1",
                "decision": DECISION,
                "input_path": path.name,
                "output_path": path.name,
                "total_input": count,
                "eligible_pairs": count,
                "missing_official_only": 0,
                "missing_short_only": 0,
                "missing_both": 0,
                "shared_stage": shared,
                "no_shared_stage": count - shared,
                "output_gzip_sha256": sha256_file(path),
                "output_csv_sha256": sha256_gzip_payload(path),
                "compression": compression_metadata(),
            }
        ),
        encoding="utf-8",
    )


def test_tokenizer_has_unicode_safe_explicit_boundaries() -> None:
    assert tokenize("L’été O’Neill’s re-entry NASA U.S.A. 2024, café!") == [
        "L’été",
        "O’Neill’s",
        "re-entry",
        "NASA",
        "U.S.A.",
        "2024",
        "café",
    ]
    assert tokenize(None) == []
    assert tokenize("") == []


def test_tokenizer_removes_ordinary_terminal_punctuation_and_preserves_acronyms() -> (
    None
):
    assert tokenize("Act. Section, title!") == ["Act", "Section", "title"]
    assert tokenize("U.S. U.S.A.") == ["U.S.", "U.S.A."]
    assert compute_pair_metrics("Act.", "act")["official_legalese_count"] == 1


def test_pair_metrics_use_documented_directions_and_core_only_candidates() -> None:
    row = compute_pair_metrics(
        "An Act to authorize funding pursuant to section 4",
        "Secure Security American Community",
    )
    assert row["word_count_delta_official_minus_short"] > 0
    assert row["compression_ratio_official_over_short"] > 1
    assert row["short_threat_contextual_count"] == 1
    assert row["short_values_contextual_count"] == 2
    assert not row["threat_framing_candidate"]
    assert not row["values_framing_candidate"]
    assert row["mechanism_obscuring_candidate"]


def test_core_candidate_requires_positive_short_minus_official_delta() -> None:
    positive = compute_pair_metrics("An Act", "Freedom from Crime")
    nonpositive = compute_pair_metrics("Freedom Act", "Freedom")
    assert positive["values_framing_candidate"]
    assert positive["threat_framing_candidate"]
    assert not nonpositive["values_framing_candidate"]


def test_constituency_nouns_are_contextual_not_values_core() -> None:
    nouns = {
        "children",
        "family",
        "families",
        "veteran",
        "veterans",
        "worker",
        "workers",
        "taxpayer",
        "taxpayers",
    }
    assert nouns <= set(LEXICONS["values_contextual"])
    assert not nouns & set(LEXICONS["values_core"])
    assert not compute_pair_metrics("Act", "Children Workers")[
        "values_framing_candidate"
    ]


def test_surface_requires_shorter_and_two_strict_available_improvements() -> None:
    row = compute_pair_metrics(
        "An Act pursuant to section 12 for the authorization of appropriations",
        "Safe Bill",
    )
    assert row["surface_proxy_improvement_count"] >= 2
    assert row["surface_simplification_candidate"]
    assert (
        compute_pair_metrics("Act", "Freedom Act")["surface_simplification_candidate"]
        is False
    )


def test_readability_has_five_and_ten_alphabetic_token_guards() -> None:
    for count in (4, 5, 9, 10):
        title = " ".join(f"word{i}" for i in range(count))
        metrics = compute_pair_metrics(title, title)
        assert metrics["official_readability_eligible_5"] is (count >= 5)
        assert metrics["official_readability_eligible_10"] is (count >= 10)
    asymmetric = compute_pair_metrics("one two three four", "one two three four five")
    assert not asymmetric["readability_both_eligible_5"]
    assert asymmetric["official_flesch_reading_ease"] is None
    assert asymmetric["flesch_reading_ease_delta_official_minus_short"] is None
    eligible = compute_pair_metrics(
        "one two three four five", "one two three four five"
    )
    assert eligible["readability_both_eligible_5"]
    assert eligible["flesch_reading_ease_delta_official_minus_short"] == pytest.approx(
        0
    )
    assert not eligible["readability_both_eligible_10"]


def test_lexicons_are_nonconflicting() -> None:
    validate_lexicons()
    assert LEXICON_VERSION


def test_writer_is_deterministic_validates_and_cleans_failed_publication(
    tmp_path,
) -> None:
    source = tmp_path / "title_pairs.csv.gz"
    fields = [
        "bill_id",
        "canonical_official_title",
        "canonical_short_title",
        "stage_alignment_status",
    ]
    with gzip.open(source, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "bill_id": "hr1-1",
                "canonical_official_title": "An Act to authorize funding",
                "canonical_short_title": "Freedom Act",
                "stage_alignment_status": "shared_stage",
            }
        )
    _write_minimal_canonical_sidecar(source)
    output = tmp_path / "metrics.csv.gz"
    summary = write_metrics(source, output)
    assert summary["output_rows"] == 1
    assert validate_metrics_output(output)["output_rows"] == 1
    first_bytes, first_checksum = output.read_bytes(), summary["output_gzip_sha256"]
    second = tmp_path / "metrics-second.csv.gz"
    assert write_metrics(source, second)["output_gzip_sha256"] == first_checksum
    assert second.read_bytes() == first_bytes
    with gzip.open(output, "rt", encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["stage_alignment_status"] == "shared_stage"
    assert row["bill_id"] == "hr1-1"
    bad = tmp_path / "bad.csv.gz"
    with gzip.open(bad, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "bill_id": "x",
                "canonical_official_title": "",
                "canonical_short_title": "x",
                "stage_alignment_status": "shared_stage",
            }
        )
    _write_minimal_canonical_sidecar(bad)
    with pytest.raises(ValueError):
        write_metrics(bad, output)
    assert not output.exists()
    assert not output.with_suffix(".summary.json").exists()
    assert TOKENIZER_VERSION


@pytest.mark.parametrize(
    "mutation",
    [
        lambda summary: summary.pop("rule_version"),
        lambda summary: summary.update(output_gzip_sha256="not-a-sha"),
        lambda summary: summary.update(output_rows=2),
        lambda summary: summary.update(eligibility_counts={}),
        lambda summary: summary.update(unknown_field=1),
    ],
)
def test_validator_rejects_missing_tampered_and_malformed_sidecars(
    tmp_path, mutation
) -> None:
    source = tmp_path / "input.csv.gz"
    fields = ["bill_id", "canonical_official_title", "canonical_short_title"]
    with gzip.open(source, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "bill_id": "x",
                "canonical_official_title": "Act",
                "canonical_short_title": "Act",
            }
        )
    _write_minimal_canonical_sidecar(source)
    output = tmp_path / "metrics.csv.gz"
    write_metrics(source, output)
    sidecar = output.with_suffix(".summary.json")
    summary = json.loads(sidecar.read_text(encoding="utf-8"))
    mutation(summary)
    sidecar.write_text(json.dumps(summary), encoding="utf-8")
    with pytest.raises(ValueError):
        validate_metrics_output(output)


def test_validator_rejects_missing_data_and_malformed_json_sidecar(tmp_path) -> None:
    output = tmp_path / "metrics.csv.gz"
    output.with_suffix(".summary.json").write_text("{bad", encoding="utf-8")
    with pytest.raises(ValueError, match="data and summary"):
        validate_metrics_output(output)
    output.write_bytes(b"not gzip")
    with pytest.raises(ValueError, match="malformed"):
        validate_metrics_output(output)


def test_metrics_lineage_is_cwd_independent_and_rejects_forged_input_hashes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "title_pairs.csv.gz"
    fields = ["bill_id", "canonical_official_title", "canonical_short_title"]
    with gzip.open(source, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "bill_id": "x",
                "canonical_official_title": "Act",
                "canonical_short_title": "Act",
            }
        )
    _write_minimal_canonical_sidecar(source)
    output = tmp_path / "metrics.csv.gz"
    write_metrics(source, output)
    summary_path = output.with_suffix(".summary.json")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["input_csv_sha256"] = "0" * 64
    summary["input_gzip_sha256"] = "1" * 64
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    assert validate_metrics_output(output)["output_rows"] == 1
    monkeypatch.chdir(Path("/tmp"))
    with pytest.raises(ValueError, match="input CSV checksum"):
        validate_metrics_lineage(
            output.resolve(),
            expected_input_path=source.resolve(),
            expected_input_csv_sha256=sha256_gzip_payload(source),
        )


def test_header_only_input_publishes_full_schema_and_validates(tmp_path) -> None:
    source = tmp_path / "input.csv.gz"
    fields = [
        "bill_id",
        "canonical_official_title",
        "canonical_short_title",
        "source_note",
    ]
    with gzip.open(source, "wt", encoding="utf-8", newline="") as handle:
        csv.DictWriter(handle, fieldnames=fields).writeheader()
    _write_minimal_canonical_sidecar(source)

    output = tmp_path / "metrics.csv.gz"
    summary = write_metrics(source, output)
    with gzip.open(output, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        assert next(reader, None) is None
    assert header == PAIR_FIELDS + list(METRIC_FIELDS)
    assert summary["output_rows"] == 0
    assert validate_metrics_output(output)["output_rows"] == 0


def test_validator_rejects_in_range_aggregate_tampering(tmp_path) -> None:
    source = tmp_path / "input.csv.gz"
    fields = ["bill_id", "canonical_official_title", "canonical_short_title"]
    with gzip.open(source, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "bill_id": "x",
                "canonical_official_title": "Act",
                "canonical_short_title": "Act",
            }
        )
    _write_minimal_canonical_sidecar(source)
    output = tmp_path / "metrics.csv.gz"
    write_metrics(source, output)
    sidecar = output.with_suffix(".summary.json")
    summary = json.loads(sidecar.read_text(encoding="utf-8"))
    summary["candidate_counts"]["surface_simplification_candidate"] = 1
    sidecar.write_text(json.dumps(summary), encoding="utf-8")
    with pytest.raises(ValueError, match="candidate_counts do not match"):
        validate_metrics_output(output)


def test_validator_rejects_changed_row_with_valid_checksum(tmp_path) -> None:
    source = tmp_path / "input.csv.gz"
    fields = ["bill_id", "canonical_official_title", "canonical_short_title"]
    with gzip.open(source, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "bill_id": "x",
                "canonical_official_title": "Act",
                "canonical_short_title": "Act",
            }
        )
    _write_minimal_canonical_sidecar(source)
    output = tmp_path / "metrics.csv.gz"
    write_metrics(source, output)
    with gzip.open(output, "rt", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["readability_both_eligible_5"] = "True"
    with output.open("wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed:
            with __import__("io").TextIOWrapper(
                compressed, encoding="utf-8", newline=""
            ) as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
    sidecar = output.with_suffix(".summary.json")
    summary = json.loads(sidecar.read_text(encoding="utf-8"))
    summary["output_gzip_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    from bill_titles.clean import sha256_gzip_payload

    summary["output_csv_sha256"] = sha256_gzip_payload(output)
    sidecar.write_text(json.dumps(summary), encoding="utf-8")
    with pytest.raises(ValueError, match="eligibility_counts do not match"):
        validate_metrics_output(output)


def test_validator_rejects_missing_header_and_noncanonical_boolean(tmp_path) -> None:
    source = tmp_path / "input.csv.gz"
    fields = ["bill_id", "canonical_official_title", "canonical_short_title"]
    with gzip.open(source, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "bill_id": "x",
                "canonical_official_title": "Act",
                "canonical_short_title": "Act",
            }
        )
    _write_minimal_canonical_sidecar(source)
    output = tmp_path / "metrics.csv.gz"
    write_metrics(source, output)
    with gzip.open(output, "rt", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    sidecar = output.with_suffix(".summary.json")
    summary = json.loads(sidecar.read_text(encoding="utf-8"))
    with output.open("wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        field
                        for field in rows[0]
                        if field != "readability_both_eligible_5"
                    ],
                    extrasaction="ignore",
                )
                writer.writeheader()
                writer.writerows(rows)
    summary["output_gzip_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    from bill_titles.clean import sha256_gzip_payload

    summary["output_csv_sha256"] = sha256_gzip_payload(output)
    sidecar.write_text(json.dumps(summary), encoding="utf-8")
    with pytest.raises(ValueError, match="header is missing required fields"):
        validate_metrics_output(output)

    write_metrics(source, output)
    with gzip.open(output, "rt", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["readability_both_eligible_5"] = "true"
    with output.open("wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
    summary = json.loads(sidecar.read_text(encoding="utf-8"))
    summary["output_gzip_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    summary["output_csv_sha256"] = sha256_gzip_payload(output)
    sidecar.write_text(json.dumps(summary), encoding="utf-8")
    with pytest.raises(ValueError, match="malformed boolean"):
        validate_metrics_output(output)


@pytest.mark.parametrize("header", [[], ["bill_id", "canonical_official_title"]])
def test_writer_rejects_missing_canonical_headers(tmp_path, header) -> None:
    source = tmp_path / "input.csv.gz"
    with gzip.open(source, "wt", encoding="utf-8", newline="") as handle:
        csv.DictWriter(handle, fieldnames=header).writeheader()
    with pytest.raises(ValueError, match="canonical pair summary"):
        write_metrics(source, tmp_path / "metrics.csv.gz")
