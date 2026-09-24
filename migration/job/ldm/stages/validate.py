"""VALIDATE: business hash, parent check, per-class counts and sums; purge_safe only for fully clean rows."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from ..context import RunContext, TableSpec
from ..convert import convert_record
from ..drivers.base import ClassAggregate, ClassTotalRow, Reject, StagedRow, ValidationRow
from ..errors import ReconcileError
from ..hashing import render_source_column, render_target_column, source_hash, tsql_hash_expression

RULE_HASH = "HASH_MISMATCH"
RULE_ORPHAN = "ORPHAN_PARENT_NOT_SELECTED"
RULE_CLASS_COUNT = "CLASS_COUNT_MISMATCH"
RULE_CLASS_TOTAL = "CLASS_TOTAL_MISMATCH"


@dataclass
class _Candidate:
    row: StagedRow
    source_values: dict[str, object]
    source_hash: bytes
    target_hash: bytes | None
    source_class: str | None = None
    target_class: str | None = None
    rule: str | None = None
    field_name: str | None = None
    error: str | None = None


@dataclass
class _ClassSide:
    count: int = 0
    sums: dict[str, Decimal] = field(default_factory=dict)


def _successor_map(ctx: RunContext, ts: TableSpec) -> dict[str, str]:
    """Db2 policy code -> system-of-record class from the staged reference table (this run)."""
    ct = ts.config.class_totals
    if not ct or not ct.source_class_resolution:
        return {}
    res = ct.source_class_resolution
    lookup = ctx.table(res.lookup_table)
    out: dict[str, str] = {}
    for batch in ctx.target.iter_staging(
        ctx.run_id, ctx.namespace, lookup.name, ctx.manifest.batch.validate_batch_rows
    ):
        for r in batch:
            code = str(r.values[res.lookup_key]).rstrip(" ")
            succ = str(r.values[res.successor_column] or "").rstrip(" ")
            if succ:
                out[code] = succ
    return out


def _source_class(raw_class: str, spec_value_map: dict[str, str], successors: dict[str, str]) -> str:
    code = raw_class.rstrip(" ")
    if code in successors:
        return successors[code]
    return spec_value_map.get(code, code)


def _differing_column(c: _Candidate, ts: TableSpec) -> str:
    for name in ts.config.hash_columns:
        spec = ts.by_name[name]
        if render_source_column(c.source_values[name], spec) != render_target_column(c.row.values, spec):
            return name
    return ts.config.hash_columns[0]


def validate_table(ctx: RunContext, ts: TableSpec) -> dict[str, int]:
    m = ctx.manifest
    cfg = ts.config
    hash_cols = cfg.hash_columns
    tsql = tsql_hash_expression(hash_cols, ts.columns)
    target_hashes = ctx.target.target_hashes(ctx.run_id, ctx.namespace, ts.name, tsql)

    candidates: list[_Candidate] = []
    for batch in ctx.target.iter_staging(ctx.run_id, ctx.namespace, ts.name, m.batch.validate_batch_rows):
        for row in batch:
            conv = convert_record(row.raw_bytes, ts.columns)
            if not conv.ok:  # cannot happen for a staged row; treat as a hash failure rather than crash
                err = conv.error
                assert err is not None
                candidates.append(
                    _Candidate(row, {}, b"", None, rule=RULE_HASH, field_name=err.column, error=err.error)
                )
                continue
            candidates.append(
                _Candidate(
                    row,
                    dict(conv.source_text),
                    source_hash(conv.source_text, hash_cols, ts.columns),
                    target_hashes.get(row.source_key),
                )
            )

    # 1. business hash
    for c in candidates:
        if c.rule:
            continue
        if c.target_hash != c.source_hash:
            c.rule = RULE_HASH
            c.field_name = _differing_column(c, ts)
            c.error = (
                f"business hash source={c.source_hash.hex()[:16]} target="
                f"{(c.target_hash or b'').hex()[:16] or 'missing'} differs at {c.field_name}"
            )

    # 2. parent present (validated in this run, or already archived)
    if cfg.selection.parent:
        parent = cfg.selection.parent
        present = ctx.target.parents_present(
            ctx.run_id, ctx.namespace, ts.name, parent.columns, parent.table, parent.references
        )
        for c in candidates:
            if c.rule or c.row.source_key in present:
                continue
            c.rule = RULE_ORPHAN
            c.field_name = parent.columns[0]
            pk = "|".join(str(c.row.values[col]).rstrip(" ") for col in parent.columns)
            c.error = f"parent {parent.table}({pk}) is neither validated in this run nor present in arch.{parent.table}"

    # 3. counts and sums by retention class (system-of-record class vs converted class)
    class_rows: list[ClassTotalRow] = []
    if cfg.class_totals:
        ct = cfg.class_totals
        successors = _successor_map(ctx, ts)
        class_spec = ts.by_name[ct.class_column]
        src: dict[str, _ClassSide] = defaultdict(_ClassSide)
        for c in candidates:
            raw = c.source_values.get(ct.class_column)
            c.source_class = _source_class(str(raw or ""), class_spec.value_map, successors)
            c.target_class = str(c.row.values[ct.class_column] or "").rstrip(" ")
            side = src[c.source_class]
            side.count += 1
            for col in ct.sum_columns:
                v = c.source_values[col]
                assert isinstance(v, Decimal)
                side.sums[col] = side.sums.get(col, Decimal(0)) + v
        tgt: dict[str, ClassAggregate] = ctx.target.class_aggregates(
            ctx.run_id, ctx.namespace, ts.name, ct.class_column, ct.sum_columns
        )
        sum_col = ct.sum_columns[0] if ct.sum_columns else None
        for cls in sorted(set(src) | set(tgt)):
            s, t = src.get(cls, _ClassSide()), tgt.get(cls, ClassAggregate())
            s_sum = s.sums.get(sum_col, Decimal(0)) if sum_col else None
            t_sum = t.sums.get(sum_col, Decimal(0)) if sum_col else None
            count_ok = s.count == t.count
            sums_ok = all(s.sums.get(col, Decimal(0)) == t.sums.get(col, Decimal(0)) for col in ct.sum_columns)
            status = "MATCH" if count_ok and sums_ok else "MISMATCH"
            class_rows.append(ClassTotalRow(ts.name, cls, s.count, t.count, s_sum, t_sum, status))
            if status == "MATCH":
                continue
            rule = RULE_CLASS_COUNT if not count_ok else RULE_CLASS_TOTAL
            detail = (
                f"class {cls}: source count={s.count} target count={t.count}"
                if not count_ok
                else f"class {cls}: source SUM({sum_col})={s_sum} target SUM({sum_col})={t_sum}"
            )
            moved = [
                c for c in candidates if cls in (c.source_class, c.target_class) and c.source_class != c.target_class
            ]
            affected = moved or [c for c in candidates if c.target_class == cls]
            for c in affected:
                if c.rule:
                    continue
                c.rule = rule
                c.field_name = ct.class_column
                c.error = (
                    f"{detail}; row class {c.source_class} (system of record) vs {c.target_class} (target)"
                    if c.source_class != c.target_class
                    else detail
                )
        ctx.target.write_class_totals(ctx.run_id, ctx.namespace, class_rows)
        for r in class_rows:
            ctx.log.info(
                f"class {r.retention_class}: count {r.source_count}/{r.target_count} sum {r.source_sum}/{r.target_sum} "
                f"{r.status}",
                ts.name,
            )

    # persist
    rows: list[ValidationRow] = []
    rejects: list[Reject] = []
    for c in candidates:
        ok = c.rule is None
        rows.append(
            ValidationRow(
                ts.name,
                c.row.source_key,
                "VALIDATED" if ok else "FAILED",
                c.rule,
                c.source_hash,
                c.target_hash,
                purge_safe=ok and cfg.role == "data",
                error_text=c.error,
            )
        )
        if not ok:
            rejects.append(
                Reject(
                    ts.name,
                    c.row.source_key,
                    "VALIDATE",
                    c.rule or "",
                    c.field_name,
                    c.row.raw_bytes,
                    None,
                    None,
                    None,
                    c.error or "",
                )
            )
    ctx.target.write_validation(ctx.run_id, ctx.namespace, rows)
    if rejects:
        ctx.target.insert_rejects(ctx.run_id, ctx.namespace, rejects)
    promoted = ctx.target.promote(ctx.run_id, ctx.namespace, ts.name, cfg.key_columns)

    validated = ctx.target.count_validation(ctx.run_id, ctx.namespace, ts.name, "VALIDATED")
    failed = ctx.target.count_validation(ctx.run_id, ctx.namespace, ts.name, "FAILED")
    ctx.target.update_ledger(ctx.run_id, ctx.namespace, ts.name, validated=validated, validate_failed=failed)
    ledger = ctx.target.get_ledger(ctx.run_id, ctx.namespace)[ts.name]
    loaded = ledger.loaded if ledger.loaded is not None else -1
    if loaded != validated + failed:
        raise ReconcileError(f"{ts.name}: loaded {loaded} != validated {validated} + validate_failed {failed}")
    ctx.log.info(f"validated={validated} failed={failed} promoted={promoted}", ts.name)
    return {"validated": validated, "validate_failed": failed}


def run(ctx: RunContext) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for ts in ctx.tables_in_order():
        log_id = ctx.target.stage_log_start(ctx.run_id, ctx.namespace, "VALIDATE", ts.name)
        try:
            out[ts.name] = validate_table(ctx, ts)
        except Exception as e:
            ctx.target.stage_log_finish(log_id, "FAILED", None, str(e)[:4000])
            raise
        ctx.target.stage_log_finish(log_id, "OK", out[ts.name]["validated"], None)
    return out
