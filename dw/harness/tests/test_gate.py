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


def test_schema_incompatible_columns_fail_even_when_values_match() -> None:
    legacy = _manifest("same")
    converted = _manifest("same")
    legacy.columns = [{"name": "value", "type": "bigint"}]
    converted.columns = [{"name": "value", "type": "string"}]
    result = compare(legacy, converted)
    assert result.status is Status.FAIL
    assert any(
        finding.kind == "type" and finding.column == "value"
        for finding in result.findings
    )


def test_decimal_scale_change_fails_type_check() -> None:
    legacy = _manifest("same")
    converted = _manifest("same")
    legacy.columns = [{"name": "value", "type": "numeric", "scale": 2}]
    converted.columns = [{"name": "value", "type": "decimal", "scale": 4}]
    result = compare(legacy, converted)
    assert result.status is Status.FAIL
    assert result.findings[0].kind == "type"


def test_upstream_elt_change_changes_downstream_fingerprint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import assets
    from dataclasses import replace

    upstream_key = "core.fct_order_items"
    upstream = assets.ASSETS[upstream_key]
    replacement = tmp_path / "core_fct_order_items.sql"
    replacement.write_text(upstream.elt.read_text())
    monkeypatch.setitem(
        assets.ASSETS,
        upstream_key,
        replace(upstream, elt=replacement),
    )
    before = assets.fingerprint_for("mart.returns_rate_by_category")
    replacement.write_text(replacement.read_text() + "\n-- changed\n")
    after = assets.fingerprint_for("mart.returns_rate_by_category")
    assert before != after


def test_staging_reference_adds_ddl_to_fingerprint_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import assets
    from dataclasses import replace

    replacement = tmp_path / "core_dim_product.sql"
    replacement.write_text(
        assets.ASSETS["core.dim_product"].elt.read_text()
        + "\nSELECT * FROM staging.stg_returns_raw;\n"
    )
    monkeypatch.setitem(
        assets.ASSETS,
        "core.dim_product",
        replace(assets.ASSETS["core.dim_product"], elt=replacement),
    )
    captured: dict[str, tuple[Path, ...]] = {}

    def capture(**kwargs: object) -> str:
        schema_sources = kwargs["schema_sources"]
        assert isinstance(schema_sources, tuple)
        captured["schema_sources"] = schema_sources
        return "fingerprint"

    monkeypatch.setattr(assets, "fingerprint", capture)
    assets.fingerprint_for("core.dim_product")
    assert (
        assets.ESTATE / "ddl/staging/stg_returns_raw.sql"
    ) in captured["schema_sources"]


def test_each_runtime_input_changes_fingerprint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import assets

    for index, source in enumerate(assets.RUNTIME_SOURCES):
        replacement = tmp_path / f"runtime-{index}.py"
        replacement.write_bytes(source.read_bytes())
        sources = list(assets.RUNTIME_SOURCES)
        sources[index] = replacement
        monkeypatch.setattr(assets, "RUNTIME_SOURCES", tuple(sources))
        before = assets.fingerprint_for("mart.returns_rate_by_category")
        replacement.write_bytes(replacement.read_bytes() + b"\n# changed\n")
        after = assets.fingerprint_for("mart.returns_rate_by_category")
        assert before != after
        monkeypatch.setattr(assets, "RUNTIME_SOURCES", tuple(
            list(assets.RUNTIME_SOURCES[:index]) + [source]
            + list(assets.RUNTIME_SOURCES[index + 1:])
        ))


def test_called_procedure_changes_fingerprint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import assets

    procedure = tmp_path / "sp_merge_customer_scd2.sql"
    procedure.write_text(
        (assets.ESTATE / "procs/sp_merge_customer_scd2.sql").read_text()
    )
    index = assets._procedure_index()
    index["core.sp_merge_customer_scd2"] = procedure
    monkeypatch.setattr(assets, "_procedure_index", lambda: index)
    before = assets.fingerprint_for("core.dim_customer_scd2")
    procedure.write_text(procedure.read_text() + "\n-- changed\n")
    after = assets.fingerprint_for("core.dim_customer_scd2")
    assert before != after


def test_transitive_called_procedure_changes_fingerprint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import assets

    merge = tmp_path / "sp_merge_customer_scd2.sql"
    merge.write_text(
        (assets.ESTATE / "procs/sp_merge_customer_scd2.sql").read_text()
        + "\nCALL core.sp_nested();\n"
    )
    nested = tmp_path / "sp_nested.sql"
    nested.write_text(
        "CREATE OR REPLACE PROCEDURE core.sp_nested() "
        "LANGUAGE plpgsql AS $$ BEGIN NULL; END; $$;"
    )
    index = assets._procedure_index()
    index.update({
        "core.sp_merge_customer_scd2": merge,
        "core.sp_nested": nested,
    })
    monkeypatch.setattr(assets, "_procedure_index", lambda: index)
    before = assets.fingerprint_for("core.dim_customer_scd2")
    nested.write_text(nested.read_text() + "\n-- changed\n")
    after = assets.fingerprint_for("core.dim_customer_scd2")
    assert before != after


def test_code_only_scan_does_not_count_procedure_names_as_tables(
    tmp_path: Path,
) -> None:
    from dw.discovery.scan import main as scan_main

    estate = tmp_path / "estate"
    (estate / "ddl/core").mkdir(parents=True)
    (estate / "elt").mkdir()
    (estate / "procs").mkdir()
    (estate / "jobs").mkdir()
    (estate / "ddl/core/fct_orders.sql").write_text(
        "CREATE TABLE core.fct_orders (order_id BIGINT);"
    )
    (estate / "elt/fct_orders.sql").write_text(
        "INSERT INTO core.fct_orders (order_id) "
        "SELECT order_id FROM staging.stg_orders_raw;"
    )
    (estate / "procs/sp_housekeeping.sql").write_text(
        "CREATE OR REPLACE PROCEDURE core.sp_housekeeping()\n"
        "LANGUAGE plpgsql AS $$ BEGIN "
        "PERFORM COUNT(*) FROM core.fct_orders; END; $$;"
    )
    (estate / "procs/sp_refresh_marts.sql").write_text(
        "CREATE OR REPLACE PROCEDURE core.sp_refresh_marts()\n"
        "LANGUAGE plpgsql AS $$ BEGIN "
        "CALL core.sp_housekeeping(); "
        "INSERT INTO mart.daily_revenue_by_channel "
        "SELECT * FROM core.fct_orders; END; $$;"
    )
    (estate / "jobs/schedule.py").write_text(
        "dw/legacy-estate/elt/fct_orders.sql\nCALL core.sp_refresh_marts();"
    )
    output = tmp_path / "inventory.json"
    assert (
        scan_main(
            [
                "--estate",
                str(estate),
                "--out",
                str(output),
            ]
        )
        == 0
    )
    inventory = json.loads(output.read_text())
    assert inventory["totals"]["tables"] == 3
    assert "core.sp_housekeeping" not in inventory["catalog"]
    assert "core.sp_refresh_marts" not in inventory["catalog"]
    assets = {
        asset["path"]: asset for asset in inventory["assets"]
    }
    assert assets["elt/fct_orders.sql"]["scheduled"] is True
    assert assets["ddl/core/fct_orders.sql"]["scheduled"] is False
    assert assets["procs/sp_refresh_marts.sql"]["scheduled"] is True
    assert assets["procs/sp_housekeeping.sql"]["scheduled"] is True


def test_code_only_scan_matches_estate_table_catalog(tmp_path: Path) -> None:
    from dw.discovery.scan import main as scan_main

    output = tmp_path / "inventory.json"
    assert scan_main(
        [
            "--estate",
            "dw/legacy-estate",
            "--out",
            str(output),
        ]
    ) == 0
    inventory = json.loads(output.read_text())
    assert inventory["totals"]["tables"] == 26
    assert inventory["dead_tables"] == [
        "core.stg_orders_dedup_audit",
        "mart.customer_churn_flags",
    ]
