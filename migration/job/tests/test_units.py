"""Unit tests: manifest validation, copybooks against the real files, business hash, CLI exit codes."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from ldm.__main__ import main
from ldm.config import load_manifest, validate_run_id, validate_token
from ldm.context import build_table_specs
from ldm.convert import Timestamp12, convert_record, encode_record
from ldm.copybook import parse_copybook
from ldm.errors import ConfigError
from ldm.hashing import business_hash, render, source_hash, target_hash, tsql_hash_expression

from .conftest import MANIFEST, REPO_ROOT, cp037, docarch_row, make_manifest_tree

COPYBOOKS = REPO_ROOT / "migration" / "source" / "copybooks"


# --- manifest -------------------------------------------------------------------------------------------------------


def test_repo_manifest_loads_after_and_rejects_before() -> None:
    with pytest.raises(ConfigError, match="migrate: false"):
        load_manifest(MANIFEST, "d24-before")
    after = load_manifest(MANIFEST, "d24-after")
    assert after.manifest.migrate is True and after.manifest.purge is True
    assert [t.name for t in after.manifest.tables_in_order()] == ["RETNPLCY", "DOCARCH", "FILEAUD"]
    assert after.manifest.selection_sets["closed-7y"] == ["FIN7", "LGL7", "HRS7", "TAX7", "AUD7", "F07R", "L07R"]
    assert after.manifest.blob_prefix("r1") == "d24-after/r1/"


@pytest.mark.parametrize("ns", ["main", "D24-after", "d24-during", "toolongtoken12-after", "d24", "1d-after"])
def test_bad_namespace_tokens_rejected(ns: str) -> None:
    with pytest.raises(ConfigError):
        validate_token(ns)
    assert validate_token("d24-after") == ("d24", "after")


@pytest.mark.parametrize("rid", ["ab", "-abc", "Run1", "a" * 64])
def test_bad_run_ids_rejected(rid: str) -> None:
    with pytest.raises(ConfigError):
        validate_run_id(rid)


def test_run_token_must_match_namespace(tmp_path: Path) -> None:
    base = make_manifest_tree(tmp_path, "zz1")
    with pytest.raises(ConfigError, match="run_token"):
        load_manifest(base, "d24-after")


def test_missing_overlay_is_config_error(tmp_path: Path) -> None:
    base = make_manifest_tree(tmp_path, "zz1")
    with pytest.raises(ConfigError):
        load_manifest(base, "zz2-after")


def test_unknown_key_and_overlay_only_key_rejected(tmp_path: Path) -> None:
    base = make_manifest_tree(tmp_path, "zz1")
    text = base.read_text(encoding="utf-8")
    base.write_text(text + "\npurge: true\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="overlay-only"):
        load_manifest(base, "zz1-after")
    base.write_text(text + "\nbogus_key: 1\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="unknown"):
        load_manifest(base, "zz1-after")


def test_hash_column_not_in_columns_rejected(tmp_path: Path) -> None:
    base = make_manifest_tree(tmp_path, "zz1")
    text = base.read_text(encoding="utf-8").replace("hash_columns: [POLICY_CODE,", "hash_columns: [NOPE,")
    base.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError, match="NOPE"):
        load_manifest(base, "zz1-after")


def test_overlay_deep_merges_and_typemap_overrides_apply(tmp_path: Path) -> None:
    base = make_manifest_tree(tmp_path, "zz1")
    loaded = load_manifest(base, "zz1-after")
    specs = build_table_specs(loaded)
    doc = specs["DOCARCH"].by_name
    assert doc["OWNER_NAME"].encoding == "cp037" and doc["OWNER_NAME"].target_type == "NVARCHAR(40)"
    assert doc["UNIT_RATE"].target_type == "DECIMAL(18,8)" and doc["UNIT_RATE"].target_precision == 18
    assert doc["STORAGE_CHARGE"].kind == "decimal" and doc["STORAGE_CHARGE"].target_precision >= 31
    assert doc["ARCH_KEY"].is_key and doc["LAST_ACCESS_TS"].kind == "timestamp12"
    assert doc["RETENTION_CLASS"].value_map == {"F07R": "LGL7", "L07R": "FIN7", "H07R": "HRS7"}


# --- copybooks ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("name", "lrecl"), [("DOCARCH", 256), ("FILEAUD", 160), ("RETNPLCY", 128)])
def test_real_copybooks_parse_to_declared_lrecl(name: str, lrecl: int) -> None:
    cb = parse_copybook(COPYBOOKS / f"{name}.cpy", lrecl)
    assert cb.record_length == lrecl
    offsets = [f.offset for f in cb.fields]
    assert offsets == sorted(offsets) and offsets[0] == 0
    assert sum(f.length for f in cb.fields) == lrecl


def test_docarch_copybook_field_layout() -> None:
    cb = parse_copybook(COPYBOOKS / "DOCARCH.cpy", 256)
    schg = cb.field("DA-SCHG")
    assert (schg.usage, schg.digits, schg.scale, schg.length, schg.signed) == ("comp-3", 31, 8, 16, True)
    assert schg.pic_key == "S9(23)V9(8) COMP-3"
    vseq = cb.field("DA-VSEQ")
    assert (vseq.usage, vseq.length, vseq.digits) == ("comp", 2, 4)
    cnt = cb.field("DA-CNT1")
    assert (cnt.usage, cnt.length, cnt.digits) == ("comp", 8, 18)
    assert cb.field("DA-AKEY").offset == 0 and cb.field("DA-DOCI").offset == 16
    assert cb.fields[-1].filler and cb.fields[-1].length == 2


def test_copybook_lrecl_mismatch_and_occurs_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="256"):
        parse_copybook(COPYBOOKS / "DOCARCH.cpy", 255)
    bad = tmp_path / "bad.cpy"
    bad.write_text("       01  X-REC.\n           05  X-A  PIC X(4) OCCURS 3 TIMES.\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        parse_copybook(bad, 12)


def test_record_conversion_roundtrip_against_docarch_copybook(tmp_path: Path) -> None:
    base = make_manifest_tree(tmp_path, "zz1")
    ts = build_table_specs(load_manifest(base, "zz1-after"))["DOCARCH"]
    row = docarch_row("K1", "FIN7", "2016-03-01-10.15.30.123456789012", charge=Decimal("1234.56789012"))
    raw = encode_record(row, ts.columns, ts.copybook.record_length)
    assert len(raw) == 256
    conv = convert_record(raw, ts.columns)
    assert conv.ok and conv.source_key == "K1".ljust(16)  # source key keeps the CHAR(16) padding
    assert conv.values["ARCH_KEY"] == "K1"  # ARCH_KEY has trim: right in the manifest
    assert conv.values["STORAGE_CHARGE"] == Decimal("1234.56789012")
    assert isinstance(conv.values["LAST_ACCESS_TS"], Timestamp12)
    assert conv.values["LAST_ACCESS_TS"].text == "2016-03-01-10.15.30.123456789012"
    assert conv.raw == raw


@pytest.mark.parametrize(
    ("kwargs", "column", "rule", "sqlstate"),
    [
        ({"owner": cp037("A", 1) + b"\x3f" + cp037("", 38)}, "OWNER_NAME", "CCSID_UNMAPPABLE", None),
        ({"disp_dt": b"\x00" * 8}, "DISPOSITION_DT", "DATE_INVALID", "22007"),
        ({"unit_rate": Decimal("99999999999.12345678")}, "UNIT_RATE", "DECIMAL_OVERFLOW", "22003"),
    ],
)
def test_conversion_errors_carry_field_and_bytes(
    tmp_path: Path, kwargs: dict[str, object], column: str, rule: str, sqlstate: str | None
) -> None:
    base = make_manifest_tree(tmp_path, "zz1")
    ts = build_table_specs(load_manifest(base, "zz1-after"))["DOCARCH"]
    bad = docarch_row("K2", "FIN7", "2016-03-01-10.15.30.123456789012", **kwargs)  # type: ignore[arg-type]
    raw = encode_record(bad, ts.columns, ts.copybook.record_length)
    conv = convert_record(raw, ts.columns)
    assert conv.error is not None and conv.raw == raw
    assert (conv.error.column, conv.error.rule, conv.error.sqlstate) == (column, rule, sqlstate)
    assert conv.error.field_bytes == ts.by_name[column].field.slice(raw)
    if rule == "CCSID_UNMAPPABLE":
        assert "X'3F'" in conv.error.error


# --- business hash --------------------------------------------------------------------------------------------------


def test_render_matches_contract_reference() -> None:
    assert render("AB  ", "char", True) == "AB  "
    assert render("AB  ", "char", False) == "AB"
    assert render("0042", "int", False) == "42"
    assert render(Decimal("1.5"), "decimal", False) == "1.50000000"
    assert render("1200.1", "decimal", False) == "1200.10000000"
    assert render(Decimal("-0.000000001"), "decimal", False) == "0.00000000"
    assert render("2016-03-01-10.15.30.123456789012", "timestamp12", False) == "2016-03-01-10.15.30.123456789012"


def test_business_hash_is_order_and_padding_sensitive() -> None:
    a = business_hash([("K   ", "char", True), ("x ", "char", False)])
    assert a == business_hash([("K   ", "char", True), ("x", "char", False)])
    assert a != business_hash([("K", "char", True), ("x", "char", False)])
    assert a != business_hash([("x", "char", False), ("K   ", "char", True)])


def test_source_and_target_hash_agree_and_value_map_applies(tmp_path: Path) -> None:
    base = make_manifest_tree(tmp_path, "zz1")
    ts = build_table_specs(load_manifest(base, "zz1-after"))["DOCARCH"]
    row = docarch_row("K3", "F07R", "2016-03-01-10.15.30.123456789012")
    conv = convert_record(encode_record(row, ts.columns, ts.copybook.record_length), ts.columns)
    src = source_hash(conv.values, ts.config.hash_columns, ts.columns)
    target_row = dict(conv.target_row())
    assert target_row["RETENTION_CLASS"].rstrip() == "LGL7"  # value_map F07R -> LGL7 applied on load
    assert target_hash(target_row, ts.config.hash_columns, ts.columns) == src
    # padding on the key column changes the hash (MIG-04): keys are never trimmed by the renderer
    target_row["ARCH_KEY"] = target_row["ARCH_KEY"] + " "
    assert target_hash(target_row, ts.config.hash_columns, ts.columns) != src


def test_tsql_hash_expression_shape(tmp_path: Path) -> None:
    base = make_manifest_tree(tmp_path, "zz1")
    ts = build_table_specs(load_manifest(base, "zz1-after"))["DOCARCH"]
    sql = tsql_hash_expression(ts.config.hash_columns, ts.columns)
    assert sql.startswith("HASHBYTES('SHA2_256', CONVERT(VARBINARY(MAX), CONCAT(")
    assert "ISNULL([ARCH_KEY], N'')" in sql and "ISNULL(RTRIM([OWNER_NAME]), N'')" in sql
    assert "CAST([STORAGE_CHARGE] AS DECIMAL(38,8))" in sql
    assert "[LAST_ACCESS_TS_NANOS_TAIL]" in sql and sql.count("N'|'") == len(ts.config.hash_columns) - 1


# --- CLI ------------------------------------------------------------------------------------------------------------


def test_cli_rejects_bad_namespace_and_missing_run_id(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["extract", "--manifest", str(MANIFEST), "--namespace", "main"]) == 4
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["exit_code"] == 4 and out["stage"] == "extract" and out["tables"] == {}
    assert main(["extract", "--manifest", str(MANIFEST), "--namespace", "d24-after"]) == 4
    assert main(["init", "--manifest", str(MANIFEST), "--namespace", "d24-after", "--run-id", "r1"]) == 4


def test_cli_before_overlay_migration_disabled_exits_4(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LDM_HOST", "local")
    assert main(["all", "--manifest", str(MANIFEST), "--namespace", "d24-before", "--run-id", "r1"]) == 4


def test_cli_missing_env_exits_4(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in ("DB2_HOST", "DB2_PORT", "DB2_DATABASE", "DB2_USER", "DB2_PASSWORD", "AZSQL_SERVER"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LDM_HOST", "eks")
    assert main(["extract", "--manifest", str(MANIFEST), "--namespace", "d24-after", "--run-id", "r1"]) == 4
