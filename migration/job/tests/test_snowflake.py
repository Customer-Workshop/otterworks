"""Split target against real services: PostgreSQL control plane + Snowflake archive store.

Skipped unless LDM_TEST_PG_HOST *and* LDM_TEST_SNOWFLAKE_ACCOUNT are set. Snowflake side: SNOWFLAKE_PAT (the
programmatic access token, never echoed), LDM_TEST_SNOWFLAKE_USER, LDM_TEST_SNOWFLAKE_ROLE (LDM_JOB_<TOKEN>,
bootstrap/tenant.sql), LDM_TEST_SNOWFLAKE_WAREHOUSE (LDM_WH) and LDM_TEST_SNOWFLAKE_DATABASE (the bootstrapped
tenant database). Every test uses a fresh namespace inside that database and drops it afterwards.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
import yaml

from ldm.context import Log
from ldm.drivers.base import ArchiveStoreTarget, StagedRow
from ldm.drivers.factory import target_spec
from ldm.drivers.snowflake import SnowflakeTarget
from ldm.runner import build_context, execute, prepare_run
from ldm.stages import extract, load
from ldm.staging import DirectoryBlobStore

from .conftest import Seed, make_manifest_tree, seed_source
from .test_postgresql import PG_ENV

SF_ENV = {
    "SNOWFLAKE_ACCOUNT": os.environ.get("LDM_TEST_SNOWFLAKE_ACCOUNT", ""),
    "SNOWFLAKE_USER": os.environ.get("LDM_TEST_SNOWFLAKE_USER", ""),
    "SNOWFLAKE_PAT": os.environ.get("SNOWFLAKE_PAT", ""),
    "SNOWFLAKE_ROLE": os.environ.get("LDM_TEST_SNOWFLAKE_ROLE", "LDM_JOB_LDM_CI"),
    "SNOWFLAKE_WAREHOUSE": os.environ.get("LDM_TEST_SNOWFLAKE_WAREHOUSE", "LDM_WH"),
    "SNOWFLAKE_DATABASE": os.environ.get("LDM_TEST_SNOWFLAKE_DATABASE", "OTTERWORKS_LDM_LDM_CI"),
}

pytestmark = pytest.mark.skipif(
    not (PG_ENV["PG_HOST"] and SF_ENV["SNOWFLAKE_ACCOUNT"] and SF_ENV["SNOWFLAKE_PAT"]),
    reason="LDM_TEST_PG_HOST / LDM_TEST_SNOWFLAKE_ACCOUNT / SNOWFLAKE_PAT not set",
)

FIXTURES = Path(__file__).resolve().parents[2] / "source" / "seed" / "fixtures"


def _env(tmp_path: Path) -> dict[str, str]:
    return {
        **PG_ENV,
        **SF_ENV,
        "LOCAL_STAGING_DIR": str(tmp_path / "staging"),
        "LDM_UNLOAD_MODE": "builtin",
        "LDM_HOST": "local",
    }


def _ctx(tmp_path: Path, manifest: Path, token: str, seed: Seed, run_id: str):
    return build_context(
        manifest,
        f"{token}-after",
        run_id,
        env=_env(tmp_path),
        source=seed.source,
        blobs=DirectoryBlobStore(tmp_path / "blobs"),
        log=Log(),
    )


def _staged(target: SnowflakeTarget, run_id: str, ns: str, table: str) -> dict[str, StagedRow]:
    out: dict[str, StagedRow] = {}
    for batch in target.iter_staging(run_id, ns, table, 500):
        for r in batch:
            out[r.source_key] = r
    return out


def _rejects(target: SnowflakeTarget, run_id: str, ns: str) -> set[tuple[str, str, str]]:
    return {(f.table_name, f.source_key, f.rule) for f in target.failures(run_id, ns)}


def _sf_rows(target: SnowflakeTarget, sql: str, params: tuple[object, ...] = ()) -> list[tuple[object, ...]]:
    return target.archive._rows(sql, params)


def _arch_counts(target: SnowflakeTarget, ns: str) -> dict[str, int]:
    rows = _sf_rows(
        target,
        f"SELECT TABLE_NAME, SUM(ROWS_ARCHIVED) FROM {target.archive._q('MIG', 'V_ARCHIVE_COUNTS')} "
        "WHERE NAMESPACE = ? GROUP BY TABLE_NAME",
        (ns,),
    )
    return {str(t): int(n) for t, n in rows}  # type: ignore[call-overload]


@pytest.fixture
def token() -> str:
    return "s" + uuid.uuid4().hex[:5]


@pytest.fixture
def cleanup():
    """Drop everything a test's namespace wrote on both halves (PostgreSQL mig/*, Snowflake STG/ARCH/MIG)."""
    targets: list[tuple[SnowflakeTarget, str]] = []
    yield targets
    for t, ns in targets:
        t.connect()
        try:
            t.drop_namespace(ns)
        finally:
            t.close()


def test_target_spec_opens_split_target(tmp_path: Path, token: str) -> None:
    import pickle

    from ldm.config import load_manifest

    manifest = make_manifest_tree(tmp_path, token, snowflake_target=True)
    spec = pickle.loads(pickle.dumps(target_spec(load_manifest(manifest, f"{token}-after"), _env(tmp_path))))
    t = spec.open()
    assert isinstance(t, SnowflakeTarget) and isinstance(t, ArchiveStoreTarget)
    t.connect()
    try:
        (role, wh, db), *_ = _sf_rows(t, "SELECT CURRENT_ROLE(), CURRENT_WAREHOUSE(), CURRENT_DATABASE()")
        assert (role, wh) == (SF_ENV["SNOWFLAKE_ROLE"], SF_ENV["SNOWFLAKE_WAREHOUSE"])
        assert db in (None, SF_ENV["SNOWFLAKE_DATABASE"])
    finally:
        t.close()


def test_init_applies_both_ddl_sets_idempotently(tmp_path: Path, token: str, cleanup) -> None:
    seed = seed_source()
    manifest = make_manifest_tree(tmp_path, token, snowflake_target=True)
    ctx = _ctx(tmp_path, manifest, token, seed, "run-init")
    assert isinstance(ctx.target, SnowflakeTarget)
    cleanup.append((ctx.target, ctx.namespace))
    first = None
    for _ in range(2):
        code, tables = execute(ctx, "init")
        assert code == 0, tables
        first = first or tables["_ddl"]
        # the second pass finds every script already recorded (sha match) on both halves
    # either half may already be recorded by earlier suites on the shared test databases; the second pass is a no-op
    assert first is not None and set(first) == {"applied", "scripts", "archive_applied", "archive_scripts"}
    assert tables["_ddl"]["applied"] == 0 and tables["_ddl"]["archive_applied"] == 0
    ctx.target.connect()
    try:
        db = ctx.target.archive.database
        views = {
            str(r[0])
            for r in _sf_rows(
                ctx.target, f"SELECT TABLE_NAME FROM {db}.INFORMATION_SCHEMA.VIEWS WHERE TABLE_SCHEMA = 'MIG'"
            )
        }
        assert {"V_RUN_SUMMARY", "V_FAILURES", "V_ARCHIVE_COUNTS", "V_CLASS_TOTALS"} <= views
        stg = {
            str(r[0])
            for r in _sf_rows(
                ctx.target,
                f"SELECT TABLE_NAME FROM {db}.INFORMATION_SCHEMA.TABLES "
                "WHERE TABLE_SCHEMA IN ('STG', 'ARCH') AND TABLE_TYPE = 'BASE TABLE'",
            )
        }
        assert {"DOCARCH", "FILEAUD", "RETNPLCY"} <= stg
    finally:
        ctx.target.close()


def test_full_run_on_split_target(tmp_path: Path, token: str, cleanup) -> None:
    """extract -> Parquet COPY INTO STG -> validate (Snowflake hashes vs source) -> promote to ARCH -> purge ->
    reconcile, with the ledger, rejects and verdicts in PostgreSQL and the rows + MIG mirror in Snowflake."""
    seed = seed_source()
    manifest = make_manifest_tree(tmp_path, token, snowflake_target=True)
    ctx = _ctx(tmp_path, manifest, token, seed, "run-split")
    assert isinstance(ctx.target, SnowflakeTarget)
    cleanup.append((ctx.target, ctx.namespace))
    code, tables = execute(ctx, "all")
    assert code == 0, tables
    p = seed.planted
    n_load_rejects = sum(len(p[c]) for c in ("MIG-01", "MIG-02", "MIG-03"))
    d = tables["DOCARCH"]
    assert d["extracted"] == seed.docarch_selected
    assert d["loaded"] + d["rejected"] == d["extracted"]
    assert d["rejected"] == n_load_rejects
    assert d["validated"] == d["loaded"] - len(p["MIG-04"]) - len(p["MIG-07"])
    assert d["purged"] == d["validated"]
    f = tables["FILEAUD"]
    assert f["validate_failed"] == len(p["MIG-05"]) and f["purged"] == f["validated"]
    assert tables["RETNPLCY"] == {**tables["RETNPLCY"], "loaded": 10, "validated": 10, "purged": 0}

    run, ns = ctx.run_id, ctx.namespace
    ctx.target.connect()
    try:
        # control plane (PostgreSQL) closed the run and holds every failure class the seed plants
        assert ctx.target.get_run_status(run, ns) == "CLOSED"
        rules = {r for _, _, r in _rejects(ctx.target, run, ns)}
        assert {
            "CCSID_UNMAPPABLE",
            "DECIMAL_OVERFLOW",
            "DATE_INVALID",
            "HASH_MISMATCH",
            "ORPHAN_PARENT_NOT_SELECTED",
            "CLASS_TOTAL_MISMATCH",
        } <= rules
        # archive store (Snowflake): ARCH holds exactly the validated rows, failed rows never got promoted
        counts = _arch_counts(ctx.target, ns)
        assert counts == {"DOCARCH": d["validated"], "FILEAUD": f["validated"], "RETNPLCY": 10}
        failed_keys = {k for t, k, r in _rejects(ctx.target, run, ns) if t == "DOCARCH" and r == "HASH_MISMATCH"}
        arch = ctx.target.archive._q("ARCH", "DOCARCH")
        placeholders = ", ".join("?" for _ in failed_keys)
        (n_failed_in_arch,), *_ = _sf_rows(
            ctx.target,
            f"SELECT COUNT(*) FROM {arch} WHERE NAMESPACE = ? AND SOURCE_KEY IN ({placeholders})",
            (ns, *failed_keys),
        )
        assert n_failed_in_arch == 0
        # staging was cleared at close; the MIG mirror carries the run + ledger + verdicts
        assert ctx.target.count_staging(run, ns, "DOCARCH") == 0
        runs = ctx.target.archive._q("MIG", "RUNS")
        (status,), *_ = _sf_rows(ctx.target, f"SELECT STATUS FROM {runs} WHERE RUN_ID = ? AND NAMESPACE = ?", (run, ns))
        assert status == "CLOSED"
        summary = {
            str(r[0]): (int(r[1]), int(r[2]), int(r[3]), str(r[4]))  # type: ignore[call-overload]
            for r in _sf_rows(
                ctx.target,
                "SELECT TABLE_NAME, VALIDATED, PURGED, FAILED, RUN_STATUS "
                f"FROM {ctx.target.archive._q('MIG', 'V_RUN_SUMMARY')} WHERE RUN_ID = ? AND NAMESPACE = ?",
                (run, ns),
            )
        }
        assert summary["DOCARCH"] == (d["validated"], d["purged"], d["rejected"] + d["validate_failed"], "CLOSED")
        # tenant isolation: another namespace inside the same database sees none of it
        assert _arch_counts(ctx.target, ns + "-x") == {}
    finally:
        ctx.target.close()


def test_spark_engine_matches_serial_engine_on_snowflake(tmp_path: Path, token: str, cleanup) -> None:
    pytest.importorskip("pyspark")
    seed = seed_source()
    serial_manifest = make_manifest_tree(tmp_path / "s", token + "r", snowflake_target=True, load_engine="serial")
    spark_manifest = make_manifest_tree(tmp_path / "k", token + "a", snowflake_target=True, load_engine="spark")
    text = spark_manifest.read_text(encoding="utf-8").replace("load_batch_rows: 5000", "load_batch_rows: 40")
    spark_manifest.write_text(text, encoding="utf-8")
    overlay = spark_manifest.parent / "manifests" / f"{token}a-after.yaml"
    data = yaml.safe_load(overlay.read_text(encoding="utf-8"))
    data.setdefault("execution", {})["spark"] = {"records_per_slice": 30, "shuffle_partitions": 2}
    overlay.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    results = {}
    for engine, manifest in (("serial", serial_manifest), ("spark", spark_manifest)):
        ctx = _ctx(tmp_path / engine[0], manifest, token + engine[2], seed, f"run-{engine}")
        assert isinstance(ctx.target, SnowflakeTarget)
        cleanup.append((ctx.target, ctx.namespace))
        ctx.source.connect()
        ctx.target.connect()
        try:
            prepare_run(ctx)
            extract.run(ctx)
            counts = load.run(ctx)
            staged = {t.name: _staged(ctx.target, ctx.run_id, ctx.namespace, t.name) for t in ctx.tables_in_order()}
            rejects = _rejects(ctx.target, ctx.run_id, ctx.namespace)
        finally:
            ctx.source.close()
            ctx.target.close()
        results[engine] = (staged, rejects, counts)
    (s_rows, s_rej, s_counts), (k_rows, k_rej, k_counts) = results["serial"], results["spark"]
    assert k_counts == s_counts
    assert k_rej == s_rej and s_rej
    for table, rows in s_rows.items():
        assert set(k_rows[table]) == set(rows)
        for key, row in rows.items():
            assert k_rows[table][key].values == row.values
            assert k_rows[table][key].raw_bytes == row.raw_bytes


def test_mig06_prior_run_fixture_plants_duplicates_across_both_halves(tmp_path: Path, token: str, cleanup) -> None:
    """`ldm init --apply-sql <pg fixture> --apply-archive-sql <snowflake fixture>`: the ABANDONED run + stale key
    range land in PostgreSQL, the five stale STG.DOCARCH rows in Snowflake, and the real run rejects MIG06-*."""
    seed = seed_source()
    manifest = make_manifest_tree(tmp_path, token, snowflake_target=True)
    fixtures = manifest.parent / "fixtures"
    fixtures.mkdir()
    pg_fixture, sf_fixture = (fixtures / n for n in ("mig06_prior_run.postgresql.sql", "mig06_prior_run.snowflake.sql"))
    for f in (pg_fixture, sf_fixture):
        f.write_bytes((FIXTURES / f.name).read_bytes())
    ctx = _ctx(tmp_path, manifest, token, seed, "run-init")
    assert isinstance(ctx.target, SnowflakeTarget)
    cleanup.append((ctx.target, ctx.namespace))
    for _ in range(2):
        code, tables = execute(ctx, "init", apply_sql=[pg_fixture], apply_archive_sql=[sf_fixture])
        assert code == 0, tables
        assert tables["_ddl"]["scripts"] == 1 and tables["_ddl"]["archive_scripts"] == 1
    ns = ctx.namespace
    ctx.target.connect()
    try:
        assert ctx.target.get_run_status("prior-partial", ns) == "ABANDONED"
        assert [r.range_seq for r in ctx.target.get_key_ranges("prior-partial", ns, "DOCARCH")] == [1]
        planted = _staged(ctx.target, "prior-partial", ns, "DOCARCH")
        assert sorted(planted) == [f"MIG06-{k:010d}" for k in range(1, 6)]
        assert planted["MIG06-0000000001"].values["RETENTION_CLASS"] == "AUD7"
    finally:
        ctx.target.close()

    ctx = _ctx(tmp_path, manifest, token, seed, "run-real")
    code, tables = execute(ctx, "all")
    assert code == 0, tables
    ctx.target.connect()
    try:
        rejects = _rejects(ctx.target, ctx.run_id, ns)
        dupes = {k for t, k, r in rejects if t == "DOCARCH" and r == "DUPLICATE_SOURCE_KEY"}
        # the stale rows still belong to the abandoned run; the real run never overwrote them
        assert sorted(_staged(ctx.target, "prior-partial", ns, "DOCARCH")) == sorted(planted)
    finally:
        ctx.target.close()
    assert dupes == {k.strip() for k in seed.planted["MIG-06"]}
    assert tables["DOCARCH"]["rejected"] == sum(len(seed.planted[c]) for c in ("MIG-01", "MIG-02", "MIG-03", "MIG-06"))
