from __future__ import annotations

import json
from pathlib import Path

import pytest

from compare import Status, compare, main as compare_main
from digest import column_digests, fold_unordered
from manifest import Column, Manifest, normalise
from sources import DuckDBSource


def test_unordered_digest_is_order_independent_but_counts_duplicates() -> None:
    assert fold_unordered(["a", "b", "a"])[1] == fold_unordered(
        ["a", "a", "b"]
    )[1]
    assert fold_unordered(["a", "b"])[1] != fold_unordered(
        ["a", "b", "b"]
    )[1]


def test_even_multiplicity_datasets_do_not_cancel() -> None:
    left = fold_unordered(["a", "a", "b", "b"])
    right = fold_unordered(["c", "c", "d", "d"])
    assert left[0] == right[0]
    assert left[1] != right[1]


def test_null_boolean_is_not_false() -> None:
    column = Column("flag", "boolean")
    assert "IS NULL THEN NULL" in normalise(column)
    assert column_digests([("\\N",)], 1)[2] != column_digests(
        [("false",)], 1
    )[2]


def test_numeric_bounds_are_not_lexicographic() -> None:
    source = DuckDBSource(":memory:")
    try:
        source.connection.execute(
            "CREATE TABLE values_for_test (amount DECIMAL(12, 0))"
        )
        source.connection.execute(
            "INSERT INTO values_for_test VALUES (9), (100)"
        )
        columns = source.columns("main.values_for_test")
        profile = source.profile("main.values_for_test", columns)
        assert profile[3] == "9"
        assert profile[4] == "100"
    finally:
        source.close()


def _manifest(fingerprint: str) -> Manifest:
    return Manifest(
        table="mart.example",
        engine="test",
        row_count=1,
        row_digest=1,
        columns=[],
        fingerprint=fingerprint,
    )


def test_fingerprint_mismatch_blocks_and_override_is_audited(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    legacy = _manifest("legacy")
    converted = _manifest("converted")
    assert compare(legacy, converted).status is Status.BLOCKED

    legacy_path = legacy.write(tmp_path / "legacy.json")
    converted_path = converted.write(tmp_path / "converted.json")
    report_path = tmp_path / "report.json"
    assert (
        compare_main(
            [
                "--legacy",
                str(legacy_path),
                "--converted",
                str(converted_path),
                "--report",
                str(report_path),
            ]
        )
        == 1
    )
    report = json.loads(report_path.read_text())
    assert report["status"] == "blocked"
    assert "BLOCKED" in capsys.readouterr().out

    reason = "intentional fixture rerecord"
    assert (
        compare_main(
            [
                "--legacy",
                str(legacy_path),
                "--converted",
                str(converted_path),
                "--report",
                str(report_path),
                "--rerecord-reason",
                reason,
            ]
        )
        == 0
    )
    report = json.loads(report_path.read_text())
    assert report["status"] == "pass"
    assert reason in report["notes"][0]
