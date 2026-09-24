"""LOAD: copybook conversion of unload files into stg.* with row-level rejects (CONTRACTS.md §9.2, §9.4)."""

from __future__ import annotations

from pathlib import Path

from ..context import RunContext, TableSpec
from ..convert import convert_record
from ..drivers.base import InsertFailure, KeyRange, Reject, StagedRow
from ..errors import ConfigError, ReconcileError
from ..staging import sha256_file

# ODBC SQLSTATE / SQL Server native error -> reject rule for rows the target itself refused
_NATIVE_RULES = {2601: "DUPLICATE_SOURCE_KEY", 2627: "DUPLICATE_SOURCE_KEY"}
_SQLSTATE_RULES = {
    "23000": "DUPLICATE_SOURCE_KEY",
    "22003": "DECIMAL_OVERFLOW",
    "22007": "DATE_INVALID",
    "22001": "STRING_TRUNCATION",
}


def _rule_for(f: InsertFailure) -> str:
    if f.native_error in _NATIVE_RULES:
        return _NATIVE_RULES[f.native_error]
    return _SQLSTATE_RULES.get(f.sqlstate or "", "TARGET_REJECTED")


def _field_for(rule: str, ts: TableSpec) -> str | None:
    if rule == "DUPLICATE_SOURCE_KEY":
        return ts.config.key_columns[0]
    return None


def _range_file(ctx: RunContext, ts: TableSpec, rng: KeyRange) -> Path:
    local = Path(rng.local_path) if rng.local_path else ctx.range_dir(ts.name) / f"{ts.name}.{rng.range_seq:05d}.dat"
    if not local.exists() or (rng.sha256_hex and sha256_file(local) != rng.sha256_hex):
        if not rng.blob_path or not ctx.blobs.download(rng.blob_path, local):
            raise ConfigError(
                f"{ts.name} range {rng.range_seq}: unload file {local} is missing and blob {rng.blob_path!r} "
                f"is not available"
            )
    if rng.sha256_hex:
        actual = sha256_file(local)
        if actual != rng.sha256_hex:
            raise ConfigError(f"{ts.name} range {rng.range_seq}: checksum {actual} != recorded {rng.sha256_hex}")
    return local


def load_range(ctx: RunContext, ts: TableSpec, rng: KeyRange) -> tuple[int, int]:
    """Return (loaded, rejected) for one key range."""
    m = ctx.manifest
    local = _range_file(ctx, ts, rng)
    data = local.read_bytes()
    lrecl = ts.config.record_length
    if len(data) % lrecl:
        raise ConfigError(f"{ts.name} range {rng.range_seq}: file size {len(data)} is not a multiple of LRECL {lrecl}")
    if rng.row_count is not None and len(data) // lrecl != rng.row_count:
        raise ConfigError(
            f"{ts.name} range {rng.range_seq}: file has {len(data) // lrecl} records, .cnt says {rng.row_count}"
        )

    if rng.load_status == "RUNNING":
        ctx.log.warn(f"range {rng.range_seq} was interrupted mid-load; replacing its staged rows", ts.name)
        ctx.target.delete_staging_range(ctx.run_id, ctx.namespace, ts.name, rng.range_seq)
        ctx.target.delete_rejects_range(ctx.run_id, ctx.namespace, ts.name, "LOAD", rng.range_seq)
    ctx.target.update_key_range(ctx.run_id, ctx.namespace, ts.name, rng.range_seq, load_status="RUNNING")

    loaded = rejected = 0
    seen_keys: set[str] = set()
    batch: list[StagedRow] = []
    rejects: list[Reject] = []

    def flush() -> None:
        nonlocal loaded, rejected
        if not batch:
            return
        failures = ctx.target.insert_staging(ctx.run_id, ctx.namespace, ts.name, batch)
        failed_keys = {f.source_key for f in failures}
        loaded += len(batch) - len(failed_keys)
        by_key = {r.source_key: r for r in batch}
        for f in failures:
            rule = _rule_for(f)
            rejects.append(
                Reject(
                    table_name=ts.name,
                    source_key=f.source_key,
                    stage="LOAD",
                    rule=rule,
                    field_name=_field_for(rule, ts),
                    raw_bytes=by_key[f.source_key].raw_bytes,
                    field_bytes=None,
                    sqlstate=f.sqlstate,
                    native_error=f.native_error,
                    error_text=f.error_text[:4000],
                    key_range_seq=rng.range_seq,
                )
            )
        rejected += len(failed_keys)
        batch.clear()
        if rejects:
            ctx.target.insert_rejects(ctx.run_id, ctx.namespace, rejects)
            rejects.clear()

    for i in range(0, len(data), lrecl):
        rec = data[i : i + lrecl]
        conv = convert_record(rec, ts.columns)
        if conv.ok and conv.source_key in seen_keys:
            rejects.append(
                Reject(
                    ts.name,
                    conv.source_key,
                    "LOAD",
                    "DUPLICATE_SOURCE_KEY",
                    ts.config.key_columns[0],
                    rec,
                    None,
                    "23000",
                    2601,
                    f"source key {conv.source_key!r} appears more than once in the unload of range {rng.range_seq}",
                    rng.range_seq,
                )
            )
            rejected += 1
            continue
        if not conv.ok:
            err = conv.error
            assert err is not None
            rejects.append(
                Reject(
                    ts.name,
                    conv.source_key,
                    "LOAD",
                    err.rule,
                    err.column,
                    rec,
                    err.field_bytes,
                    err.sqlstate,
                    None,
                    err.error[:4000],
                    rng.range_seq,
                )
            )
            rejected += 1
            continue
        seen_keys.add(conv.source_key)
        batch.append(StagedRow(ts.name, conv.source_key, rng.range_seq, rec, conv.target_row()))
        if len(batch) >= m.batch.load_batch_rows:
            flush()
    flush()
    if rejects:
        ctx.target.insert_rejects(ctx.run_id, ctx.namespace, rejects)
    ctx.target.update_key_range(ctx.run_id, ctx.namespace, ts.name, rng.range_seq, load_status="DONE")
    ctx.log.info(f"range {rng.range_seq} loaded={loaded} rejected={rejected}", ts.name)
    return loaded, rejected


def load_table(ctx: RunContext, ts: TableSpec) -> dict[str, int]:
    ranges = ctx.target.get_key_ranges(ctx.run_id, ctx.namespace, ts.name)
    if not ranges:
        raise ConfigError(f"{ts.name}: no key ranges recorded; run extract first")
    pending = [r for r in ranges if r.status != "DONE"]
    if pending:
        raise ConfigError(f"{ts.name}: {len(pending)} key range(s) not extracted (status != DONE)")
    for rng in sorted(ranges, key=lambda r: r.range_seq):
        if rng.load_status == "DONE":
            continue
        load_range(ctx, ts, rng)
    ledger = ctx.target.get_ledger(ctx.run_id, ctx.namespace)[ts.name]
    loaded = ctx.target.count_staging(ctx.run_id, ctx.namespace, ts.name)
    rejected = ctx.target.count_rejects(ctx.run_id, ctx.namespace, ts.name, "LOAD")
    ctx.target.update_ledger(ctx.run_id, ctx.namespace, ts.name, loaded=loaded, rejected=rejected)
    extracted = ledger.extracted if ledger.extracted is not None else -1
    if extracted != loaded + rejected:
        raise ReconcileError(f"{ts.name}: extracted {extracted} != loaded {loaded} + rejected {rejected}")
    return {"loaded": loaded, "rejected": rejected}


def run(ctx: RunContext) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for ts in ctx.tables_in_order():
        log_id = ctx.target.stage_log_start(ctx.run_id, ctx.namespace, "LOAD", ts.name)
        try:
            out[ts.name] = load_table(ctx, ts)
        except Exception as e:
            ctx.target.stage_log_finish(log_id, "FAILED", None, str(e)[:4000])
            raise
        ctx.target.stage_log_finish(log_id, "OK", out[ts.name]["loaded"], None)
    return out
