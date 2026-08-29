"""Run the silver_rating unit against live Oracle and the shared workspace, and measure the recon.

Sequence, once per invocation:

1. verify the pinned Oracle source SHA (stop if it moved),
2. snapshot the source read-only: counts, the rating Oracle itself computes for the population,
   and the source's own RATING_PERIODS/RATING_RESULTS rows,
3. deploy the notebook and its column spec under the parent-owned notebook root,
4. run the notebook twice on serverless with identical inputs, then a third time with a corrected
   plan for one tenant to exercise the re-finalize path, then restore that tenant and prove the
   rerun is a no-op again — the perturbation is a per-run notebook input, so neither
   Oracle nor `ow_tp.bronze.*` is touched,
5. recompute counts, money, types and every rated row **from the Delta targets** over the SQL
   warehouse, independently of what the notebook reported,
6. compare against Oracle row by row and against the eight pinned Oracle transcripts one by one,
7. write the recon report.

Nothing here writes to Oracle, to `ow_tp.bronze.*`, or to any table this unit does not own, and no
compute resource is ever created: the notebook runs on serverless and SQL goes to the pre-existing
warehouse.
"""

from __future__ import annotations

import datetime as dt
import decimal
import json
import os
import pathlib
import sys
from typing import Any

from scripts.tp_databricks.bronze_core.dbx_client import Dbx, DbxError, sql_str
from scripts.tp_databricks.silver_rating import oracle_truth

ROOT = pathlib.Path(__file__).resolve().parents[3]
UNIT = "silver_rating"
CATALOG = "ow_tp"
SCHEMA = "silver"
BRONZE = "bronze"
NOTEBOOK_ROOT = "/Shared/ow_tp"
LANDING_ROOT = "/Volumes/ow_tp/bronze/landing"
NOTEBOOK_LOCAL = ROOT / "databricks" / "notebooks" / "ow_tp_silver_rating.py"
SPEC_LOCAL = ROOT / "databricks" / "ddl" / "silver_rating_spec.json"
REPORT_PATH = ROOT / "docs" / "tech-partnerships" / "recon" / f"{UNIT}.recon.json"
TRANSCRIPT_DIR = ROOT / "procs" / "oracle" / "transcripts" / "rating"
PINNED_SHA_FILE = ROOT / "procs" / "oracle" / "transcripts" / "ORACLE_SOURCE_SHA"
SEED_MANIFEST = ROOT / "testdata" / "legacy" / "manifests"

PERIOD_START = "2026-02-01"
PERIOD_END = "2026-02-28"
# The period immediately before it. Every subscription in this population starts 2026-01-01 with a
# NULL ends_on, so January is covered for all 69 tenants and rating it quarantines nothing; all the
# usage sits in February, so January banks rollover and prices nothing. That is what makes it the
# period to rate first when proving the bank reads what this unit itself finalized.
PRECEDING_PERIOD_START = "2026-01-01"
PRECEDING_PERIOD_END = "2026-01-31"
ROLLOVER_MONTHS = 3

MONEY_COLS = ("overage_amount",)
COUNT_COLS = (
    "used_units",
    "quota_units",
    "rollover_units",
    "computed_rollover_units",
    "first_tier_units",
    "second_tier_units",
    "billable_units",
)
PARITY_COLS = ("subscription_id",) + COUNT_COLS + MONEY_COLS + ("suspension_prorated",)
EXPECTED_ANOMALIES = [
    "ANOM-ROLLOVER-PERSIST",
    "ANOM-PKG-GLOBAL-STATE",
    "ANOM-STRING-DATE-COMPARE",
    "ANOM-ROWNUM-1",
    "ANOM-SWALLOWED-EXCEPTION",
]


class Halt(RuntimeError):
    """A stop-and-report condition from the unit's brief, not a bug."""


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def check(
    cid: str,
    expected: Any,
    actual: Any,
    sot: str,
    passed: bool | None = None,
    **extra: Any,
) -> dict[str, Any]:
    ok = (expected == actual) if passed is None else passed
    row = {
        "id": cid,
        "expected": expected,
        "actual": actual,
        "source_of_truth": sot,
        "result": "pass" if ok else "fail",
    }
    row.update(extra)
    return row


# -- deploy / run --------------------------------------------------------------


def deploy(dbx: Dbx) -> None:
    dbx.mkdirs_workspace(NOTEBOOK_ROOT)
    dbx.import_workspace(
        f"{NOTEBOOK_ROOT}/ow_tp_silver_rating", str(NOTEBOOK_LOCAL), fmt="SOURCE", language="PYTHON"
    )
    dbx.import_workspace(
        f"{NOTEBOOK_ROOT}/silver_rating_spec.json", str(SPEC_LOCAL), fmt="AUTO"
    )


def run_notebook(
    dbx: Dbx,
    ns: str,
    batch_id: str,
    plan_overrides: list[dict] | None = None,
    period_start: str = PERIOD_START,
    period_end: str = PERIOD_END,
) -> dict[str, Any]:
    run_id = dbx.submit_notebook_run(
        run_name=f"ow_tp_silver_rating_{ns}_{batch_id}",
        notebook_path=f"{NOTEBOOK_ROOT}/ow_tp_silver_rating",
        params={
            "ns": ns,
            "catalog": CATALOG,
            "schema": SCHEMA,
            "bronze_schema": BRONZE,
            "period_start": period_start,
            "period_end": period_end,
            "landing_root": LANDING_ROOT,
            "spec_path": f"{NOTEBOOK_ROOT}/silver_rating_spec.json",
            "batch_id": batch_id,
            "plan_overrides": json.dumps(plan_overrides) if plan_overrides else "",
        },
    )
    run = dbx.wait_run(run_id)
    state = (run.get("state") or {}).get("result_state") or (
        run.get("status", {}).get("termination_details", {}).get("code")
    )
    if state not in ("SUCCESS", "SUCCESS_WITH_FAILURES", None):
        out = dbx.run_output(run_id)
        raise DbxError(
            f"silver_rating notebook run {run_id} ended {state}: "
            f"{json.dumps(out.get('error') or out)[:4000]}"
        )
    summary = json.loads(
        dbx.read_volume_file(f"{LANDING_ROOT}/{ns}/{UNIT}/_runs/{batch_id}.json").decode()
    )
    summary["run_id"] = run_id
    # The workspace host stays out of the branch, so only the host-relative run path is kept.
    url = run.get("run_page_url") or ""
    summary["run_page_path"] = url.split("cloud.databricks.com", 1)[-1] if url else None
    return summary


# -- target side, recomputed from Delta ---------------------------------------


def target_snapshot(dbx: Dbx, ns: str) -> dict[str, Any]:
    ns_lit = sql_str(ns)
    counts = {}
    for name in ("rating_periods", "rating_results", f"quarantine_{UNIT}"):
        rows = dbx.sql(
            f"SELECT count(*) FROM {CATALOG}.{SCHEMA}.{name} WHERE ns = {ns_lit}"
        )
        counts[name] = int(rows[0][0])
    other_ns = int(
        dbx.sql(
            f"SELECT count(*) FROM {CATALOG}.{SCHEMA}.rating_results WHERE ns <> {ns_lit}"
        )[0][0]
    )

    money = dbx.sql(
        f"""
        SELECT CAST(coalesce(sum(overage_amount), 0) AS STRING),
               CAST(coalesce(sum(CASE WHEN _origin = 'target-finalize' THEN overage_amount END), 0) AS STRING),
               CAST(coalesce(sum(CASE WHEN _origin = 'source-migrated' THEN overage_amount END), 0) AS STRING),
               CAST(coalesce(sum(used_units), 0) AS STRING),
               CAST(coalesce(sum(billable_units), 0) AS STRING),
               CAST(coalesce(sum(rollover_units), 0) AS STRING),
               count(*) FILTER (WHERE _origin = 'target-finalize'),
               count(*) FILTER (WHERE _origin = 'source-migrated')
        FROM {CATALOG}.{SCHEMA}.rating_results WHERE ns = {ns_lit}
        """
    )[0]

    # Money per rated period, so a run that has finalized more than one period is never summed into
    # a single figure: the parity comparison is always against one period's own total.
    money_by_period = {
        r[0]: {
            "overage_amount_total": r[1],
            "rows": int(r[2]),
            "used_units_total": r[3],
            "billable_units_total": r[4],
            "rollover_units_total_persisted": r[5],
        }
        for r in dbx.sql(
            f"""
            SELECT date_format(rp.period_start, 'yyyy-MM-dd'),
                   CAST(coalesce(sum(rr.overage_amount), 0) AS STRING),
                   count(*),
                   CAST(coalesce(sum(rr.used_units), 0) AS STRING),
                   CAST(coalesce(sum(rr.billable_units), 0) AS STRING),
                   CAST(coalesce(sum(rr.rollover_units), 0) AS STRING)
            FROM {CATALOG}.{SCHEMA}.rating_results rr
            JOIN {CATALOG}.{SCHEMA}.rating_periods rp ON rp.id = rr.period_id AND rp.ns = rr.ns
            WHERE rr.ns = {ns_lit} AND rr._origin = 'target-finalize'
            GROUP BY 1 ORDER BY 1
            """
        )
    }

    rows = dbx.sql(
        f"""
        SELECT rp.tenant_id, rr.id, rr.period_id, rr.subscription_id,
               CAST(rr.used_units AS STRING), CAST(rr.quota_units AS STRING),
               CAST(rr.rollover_units AS STRING), CAST(rr.computed_rollover_units AS STRING),
               CAST(rr.first_tier_units AS STRING), CAST(rr.second_tier_units AS STRING),
               CAST(rr.billable_units AS STRING), CAST(rr.overage_amount AS STRING),
               CAST(rr.suspension_prorated AS STRING),
               date_format(rr.created_at, 'yyyy-MM-dd HH:mm:ss'),
               date_format(rp.period_start, 'yyyy-MM-dd'), date_format(rp.period_end, 'yyyy-MM-dd'),
               rr._origin
        FROM {CATALOG}.{SCHEMA}.rating_results rr
        JOIN {CATALOG}.{SCHEMA}.rating_periods rp ON rp.id = rr.period_id AND rp.ns = rr.ns
        WHERE rr.ns = {ns_lit}
        ORDER BY rp.tenant_id, rp.period_start
        """
    )
    keys = (
        "tenant_id", "id", "period_id", "subscription_id", "used_units", "quota_units",
        "rollover_units", "computed_rollover_units", "first_tier_units", "second_tier_units",
        "billable_units", "overage_amount", "suspension_prorated", "created_at",
        "period_start", "period_end", "_origin",
    )
    result_rows = [dict(zip(keys, r)) for r in rows]

    periods = [
        {"id": r[0], "tenant_id": r[1], "period_start": r[2], "period_end": r[3], "_origin": r[4]}
        for r in dbx.sql(
            f"""
            SELECT id, tenant_id, date_format(period_start, 'yyyy-MM-dd'),
                   date_format(period_end, 'yyyy-MM-dd'), _origin
            FROM {CATALOG}.{SCHEMA}.rating_periods WHERE ns = {ns_lit}
            ORDER BY tenant_id, period_start
            """
        )
    ]

    types = {
        f"{r[0]}.{r[1]}": r[2]
        for r in dbx.sql(
            f"""
            SELECT table_name, column_name, full_data_type
            FROM {CATALOG}.information_schema.columns
            WHERE table_schema = {sql_str(SCHEMA)}
              AND table_name IN ('rating_periods', 'rating_results', 'quarantine_{UNIT}')
            ORDER BY table_name, ordinal_position
            """
        )
    }

    quarantine = [
        {"quarantine_reason": r[0], "source_table": r[1], "rows": int(r[2])}
        for r in dbx.sql(
            f"""
            SELECT quarantine_reason, source_table, count(*)
            FROM {CATALOG}.{SCHEMA}.quarantine_{UNIT} WHERE ns = {ns_lit}
            GROUP BY quarantine_reason, source_table ORDER BY 1, 2
            """
        )
    ]
    quarantine_shape = int(
        dbx.sql(
            f"""
            SELECT count(*) FROM {CATALOG}.{SCHEMA}.quarantine_{UNIT}
            WHERE ns = {ns_lit}
              AND (quarantine_reason IS NULL OR ns IS NULL OR source_table IS NULL
                   OR raw_source_payload IS NULL)
            """
        )[0][0]
    )

    # D-01: the wrapped LEAST/GREATEST must return NULL for a NULL argument where Spark's own
    # least/greatest silently return the other side. Probed on the warehouse, not asserted.
    null_probe = dbx.sql(
        """
        SELECT CAST(least(CAST(NULL AS DECIMAL(38,0)), CAST(5 AS DECIMAL(38,0))) AS STRING),
               CAST(CASE WHEN CAST(NULL AS DECIMAL(38,0)) IS NULL OR CAST(5 AS DECIMAL(38,0)) IS NULL
                         THEN NULL
                         ELSE least(CAST(NULL AS DECIMAL(38,0)), CAST(5 AS DECIMAL(38,0))) END AS STRING),
               CAST(greatest(CAST(NULL AS DECIMAL(38,0)), CAST(0 AS DECIMAL(38,0))) AS STRING),
               CAST(CASE WHEN CAST(NULL AS DECIMAL(38,0)) IS NULL OR CAST(0 AS DECIMAL(38,0)) IS NULL
                         THEN NULL
                         ELSE greatest(CAST(NULL AS DECIMAL(38,0)), CAST(0 AS DECIMAL(38,0))) END AS STRING)
        """
    )[0]

    return {
        "counts": counts,
        "rows_in_other_namespaces": other_ns,
        "money": {
            "overage_amount_total": money[0],
            "overage_amount_total_target_finalize": money[1],
            "overage_amount_total_source_migrated": money[2],
            "used_units_total": money[3],
            "billable_units_total": money[4],
            "rollover_units_total_persisted": money[5],
            "target_finalize_rows": int(money[6]),
            "source_migrated_rows": int(money[7]),
        },
        "money_by_period": money_by_period,
        "result_rows": result_rows,
        "periods": periods,
        "column_types": types,
        "quarantine": quarantine,
        "quarantine_rows_missing_required_fields": quarantine_shape,
        "d01_probe": {
            "spark_least_null_5": null_probe[0],
            "wrapped_least_null_5": null_probe[1],
            "spark_greatest_null_0": null_probe[2],
            "wrapped_greatest_null_0": null_probe[3],
        },
    }


def result_row(dbx: Dbx, ns: str, tenant_id: str) -> dict[str, Any]:
    """One rated row, read back from Delta, for the re-finalize comparison."""
    cols = (
        "subscription_id", "used_units", "quota_units", "rollover_units", "billable_units",
        "overage_amount", "computed_rollover_units", "first_tier_units", "second_tier_units",
        "overage_rate", "created_at", "_origin",
    )
    row = dbx.sql(
        f"""
        SELECT rr.subscription_id, CAST(rr.used_units AS STRING), CAST(rr.quota_units AS STRING),
               CAST(rr.rollover_units AS STRING), CAST(rr.billable_units AS STRING),
               CAST(rr.overage_amount AS STRING), CAST(rr.computed_rollover_units AS STRING),
               CAST(rr.first_tier_units AS STRING), CAST(rr.second_tier_units AS STRING),
               CAST(rr.overage_rate AS STRING),
               date_format(rr.created_at, 'yyyy-MM-dd HH:mm:ss'), rr._origin
        FROM {CATALOG}.{SCHEMA}.rating_results rr
        JOIN {CATALOG}.{SCHEMA}.rating_periods rp ON rp.id = rr.period_id AND rp.ns = rr.ns
        WHERE rr.ns = {sql_str(ns)} AND rp.tenant_id = {sql_str(tenant_id)}
          AND date_format(rp.period_start, 'yyyy-MM-dd') = {sql_str(PERIOD_START)}
        """
    )[0]
    return dict(zip(cols, row))


# The columns sp_finalize_rating's DUP_VAL_ON_INDEX fallback assigns, and the ones it leaves alone.
REFINALIZE_UPDATED = ("used_units", "rollover_units", "billable_units", "overage_amount")
REFINALIZE_HELD = ("subscription_id", "quota_units", "created_at")


def refinalize_probe(dbx: Dbx, ns: str, snap: dict, stamp: str) -> dict[str, Any]:
    """Re-rate one tenant on a corrected plan, then restore it.

    The correction is supplied as a per-run notebook input, so the Oracle source and
    `ow_tp.bronze.*` are both untouched: what changes is only what the notebook is asked to rate.
    Run 3 re-finalizes the tenant on the corrected plan, run 4 rates it again from bronze alone,
    which puts the row back to the value the parity comparison is made against.
    """
    candidates = [
        r
        for r in snap["result_rows"]
        if r["_origin"] == "target-finalize"
        and decimal.Decimal(r["used_units"]) > 0
        and decimal.Decimal(r["rollover_units"]) > 0
    ]
    if not candidates:
        return {
            "performed": False,
            "reason": "no rated tenant in this population has both used_units > 0 and "
            "rollover_units > 0, so a re-rate could not be made to move the money columns "
            "without inventing a source row",
        }
    tenant = sorted(
        candidates, key=lambda r: (-decimal.Decimal(r["used_units"]), r["tenant_id"])
    )[0]["tenant_id"]

    before = result_row(dbx, ns, tenant)
    # A quota of zero on a corrected plan moves billable, overage and the persisted rollover; the
    # usage itself is unchanged, so used_units legitimately stays put.
    override = [{"tenant_id": tenant, "included_units": 0, "overage_rate": "0.500000"}]
    run3 = run_notebook(dbx, ns, f"{stamp}c", plan_overrides=override)
    after = result_row(dbx, ns, tenant)
    run4 = run_notebook(dbx, ns, f"{stamp}d")
    restored = result_row(dbx, ns, tenant)

    moved = [c for c in REFINALIZE_UPDATED if before[c] != after[c]]
    held = {c: {"before": before[c], "after_rerate": after[c]} for c in REFINALIZE_HELD}
    return {
        "performed": True,
        "tenant_id": tenant,
        "plan_override": override,
        "run3": {"batch_id": run3["batch_id"], "run_id": run3["run_id"],
                 "merge_metrics": run3["merge_metrics"]},
        "run4_restore": {"batch_id": run4["batch_id"], "run_id": run4["run_id"],
                         "merge_metrics": run4["merge_metrics"]},
        "row_before": before,
        "row_after_rerate": after,
        "row_after_restore": restored,
        "columns_updated_by_the_rerate": moved,
        "columns_held_at_first_finalize": held,
        "held_unchanged": all(before[c] == after[c] for c in REFINALIZE_HELD),
        "restored_to_pre_probe_values": all(
            before[c] == restored[c] for c in before if c != "_origin"
        ),
    }


# -- the two-period rollover bank ---------------------------------------------


def silver_bank_rows(dbx: Dbx, ns: str, before: str) -> list[dict[str, Any]]:
    """The bank contribution this unit finalized itself, read back from Delta.

    These are the rows the source does not have: what the target adds to the three-month bank when
    it has rated a period the source never finalized. They are handed to Oracle so the source engine
    prices the period off the same bank, instead of the comparison being made against a Python
    re-implementation of the rule.
    """
    return [
        {"tenant_id": r[0], "period_start": r[1], "rollover_units": r[2]}
        for r in dbx.sql(
            f"""
            SELECT rp.tenant_id, date_format(rp.period_start, 'yyyy-MM-dd'),
                   CAST(rr.rollover_units AS STRING)
            FROM {CATALOG}.{SCHEMA}.rating_results rr
            JOIN {CATALOG}.{SCHEMA}.rating_periods rp ON rp.id = rr.period_id AND rp.ns = rr.ns
            WHERE rr.ns = {sql_str(ns)} AND rr._origin = 'target-finalize'
              AND rp.period_start < DATE'{before}'
              AND rp.period_start >= add_months(DATE'{before}', -{ROLLOVER_MONTHS})
            ORDER BY rp.tenant_id, rp.period_start
            """
        )
    ]


def drop_rated_period(dbx: Dbx, ns: str, period_start: str) -> dict[str, Any]:
    """Undo the probe: remove the period this unit rated only to prove the bank reads it.

    Both tables are this unit's own targets, and the delete is scoped to the rows this unit
    finalized itself (`_origin = 'target-finalize'`): the source's own migrated rows for that
    period stay exactly as bronze has them. The slice therefore ends the recon in the
    source-equivalent state the parity comparison and the pinned transcripts are measured in.
    """
    ns_lit, ps = sql_str(ns), f"DATE'{period_start}'"
    before = {
        t: int(
            dbx.sql(
                f"""
                SELECT count(*) FROM {CATALOG}.{SCHEMA}.{t} x
                WHERE x.ns = {ns_lit} AND x._origin = 'target-finalize' AND EXISTS (
                  SELECT 1 FROM {CATALOG}.{SCHEMA}.rating_periods rp
                  WHERE rp.ns = {ns_lit} AND rp.period_start = {ps}
                    AND rp.id = {'x.id' if t == 'rating_periods' else 'x.period_id'}
                )
                """
            )[0][0]
        )
        for t in ("rating_results", "rating_periods")
    }
    dbx.sql(
        f"""
        DELETE FROM {CATALOG}.{SCHEMA}.rating_results
        WHERE ns = {ns_lit} AND _origin = 'target-finalize' AND period_id IN (
          SELECT id FROM {CATALOG}.{SCHEMA}.rating_periods
          WHERE ns = {ns_lit} AND period_start = {ps}
        )
        """
    )
    dbx.sql(
        f"""
        DELETE FROM {CATALOG}.{SCHEMA}.rating_periods
        WHERE ns = {ns_lit} AND _origin = 'target-finalize' AND period_start = {ps}
          AND id NOT IN (
            SELECT period_id FROM {CATALOG}.{SCHEMA}.rating_results WHERE ns = {ns_lit}
          )
        """
    )
    return {"period_start": period_start, "rows_removed": before}


def bank_proof(dbx: Dbx, ns: str, stamp: str, money_before: dict[str, Any]) -> dict[str, Any]:
    """Rate the preceding period, then the current one, and measure what the bank did.

    The point being proven is that the current period is priced off the rollover this unit banked
    for the preceding one — the money the old bronze-only bank silently missed. Oracle is asked for
    the same period twice: once on its own bank (what the source holds today) and once with the
    silver rows added, so both totals are the source engine's own arithmetic.
    """
    jan = run_notebook(
        dbx,
        ns,
        f"{stamp}d",
        period_start=PRECEDING_PERIOD_START,
        period_end=PRECEDING_PERIOD_END,
    )
    if jan["drivers"]["quarantine_rate_pct"] > 5:
        raise Halt(
            f"quarantine rate {jan['drivers']['quarantine_rate_pct']}% on "
            f"{PRECEDING_PERIOD_START} exceeds 5%: halting the unit"
        )
    oracle_preceding = oracle_truth.snapshot(PRECEDING_PERIOD_START, PRECEDING_PERIOD_END)
    snap_preceding = target_snapshot(dbx, ns)
    parity_preceding = compare_rating(
        oracle_preceding["rating"], snap_preceding["result_rows"], PRECEDING_PERIOD_START
    )

    bank = silver_bank_rows(dbx, ns, PERIOD_START)
    oracle_with_bank = oracle_truth.snapshot(PERIOD_START, PERIOD_END, silver_bank=bank)

    rerated = run_notebook(dbx, ns, f"{stamp}e")
    snap_after = target_snapshot(dbx, ns)
    parity_with_bank = compare_rating(
        oracle_with_bank["rating"], snap_after["result_rows"], PERIOD_START
    )
    noop = run_notebook(dbx, ns, f"{stamp}f")

    money_after = snap_after["money_by_period"][PERIOD_START]
    oracle_money_with_bank = sum(
        decimal.Decimal(r["overage_amount"] or "0") for r in oracle_with_bank["rating"].values()
    ).quantize(decimal.Decimal("0.01"))
    removed = drop_rated_period(dbx, ns, PRECEDING_PERIOD_START)

    return {
        "performed": True,
        "preceding_period": {"start": PRECEDING_PERIOD_START, "end": PRECEDING_PERIOD_END},
        "current_period": {"start": PERIOD_START, "end": PERIOD_END},
        "runs": {
            "preceding_period": {"batch_id": jan["batch_id"], "run_id": jan["run_id"],
                                 "drivers": jan["drivers"],
                                 "merge_metrics": jan["merge_metrics"]},
            "current_period_with_bank": {"batch_id": rerated["batch_id"],
                                         "run_id": rerated["run_id"],
                                         "merge_metrics": rerated["merge_metrics"]},
            "current_period_rerun": {"batch_id": noop["batch_id"], "run_id": noop["run_id"],
                                     "merge_metrics": noop["merge_metrics"]},
        },
        "preceding_period_parity": parity_preceding,
        "preceding_period_money": snap_preceding["money_by_period"].get(PRECEDING_PERIOD_START),
        "bank_read_by_the_current_run": rerated["prior_bank"],
        "silver_bank_rows_handed_to_oracle": {
            "rows": len(bank),
            "sample": bank[:5],
            "note": "read back from ow_tp.silver.rating_results (_origin = 'target-finalize') and "
            "evaluated inside Oracle's own rating statement, which applies the same "
            "bronze-wins-per-(tenant, period) rule",
        },
        "money": {
            "current_period_before_the_preceding_period_existed": money_before,
            "current_period_with_the_silver_bank": money_after,
            "oracle_with_the_silver_bank": str(oracle_money_with_bank),
            "moved_by": str(
                decimal.Decimal(money_after["overage_amount_total"])
                - decimal.Decimal(money_before["overage_amount_total"])
            ),
        },
        "parity_with_bank": parity_with_bank,
        "rerun_merge_metrics": noop["merge_metrics"],
        "rerun_was_a_no_op": all(
            m["merge_rows_inserted"] == 0
            and m["merge_rows_updated"] == 0
            and m["merge_rows_deleted"] == 0
            for m in noop["merge_metrics"].values()
        ),
        "probe_undone": removed,
        "all_runs": [jan, rerated, noop],
    }


def proration_cross_check(run: dict[str, Any]) -> dict[str, Any]:
    """The target's suspension factor against Oracle's, on the same synthetic timestamps."""
    probe = run.get("proration_probe", {})
    cases = probe.get("cases", [])
    if not cases:
        return {"performed": False, "reason": "the job run carried no proration probe"}
    oracle_cases = oracle_truth.proration(
        probe["period_start"],
        probe["period_end"],
        [c["suspended_on"] for c in cases],
        probe["inputs"]["billable_pre_proration"],
        probe["inputs"]["overage_pre_proration"],
    )
    compared = []
    for tgt, src in zip(cases, oracle_cases):
        expected = {
            "factor": src["factor_10dp"],
            "billable_units": src["billable_prorated"],
            "overage_amount": src["overage_prorated"],
        }
        actual = {
            "factor": str(
                decimal.Decimal(tgt["factor"]).quantize(decimal.Decimal("0.0000000001"))
            ),
            "billable_units": norm(tgt["billable_prorated"], "billable_units"),
            "overage_amount": norm(tgt["overage_prorated"], "overage_amount"),
        }
        compared.append(
            {
                "label": tgt["label"],
                "suspended_on": tgt["suspended_on"],
                "oracle": expected,
                "target": actual,
                "agree": expected == actual,
                "target_if_the_date_were_truncated": {
                    "billable_units": tgt["billable_prorated_if_date_truncated"],
                    "overage_amount": tgt["overage_prorated_if_date_truncated"],
                },
            }
        )
    return {
        "performed": True,
        "inputs": probe["inputs"],
        "period": {"start": probe["period_start"], "end": probe["period_end"]},
        "cases": compared,
        "all_agree": all(c["agree"] for c in compared),
        "midday_differs_from_truncated": (
            compared[0]["target"]["overage_amount"]
            != norm(compared[0]["target_if_the_date_were_truncated"]["overage_amount"],
                    "overage_amount")
        ),
    }


# -- comparisons ---------------------------------------------------------------


def norm(value: Any, col: str) -> Any:
    if value is None:
        return None
    if col in MONEY_COLS:
        return str(decimal.Decimal(str(value)).quantize(decimal.Decimal("0.01")))
    if col in COUNT_COLS:
        return str(decimal.Decimal(str(value)).quantize(decimal.Decimal("1")))
    if col == "suspension_prorated":
        return str(value).lower() in ("true", "1")
    return value


def compare_rating(
    oracle: dict[str, dict], target_rows: list[dict], period_start: str = PERIOD_START
) -> dict[str, Any]:
    """Row-by-row, column-by-column comparison of one rated period against Oracle."""
    rated = {
        r["tenant_id"]: r
        for r in target_rows
        if r["_origin"] == "target-finalize" and r["period_start"] == period_start
    }
    per_col = {c: 0 for c in PARITY_COLS}
    mismatches: list[dict[str, Any]] = []
    for tenant_id, src in oracle.items():
        tgt = rated.get(tenant_id)
        if tgt is None:
            mismatches.append({"tenant_id": tenant_id, "column": "*", "expected": "row", "actual": None})
            for c in per_col:
                per_col[c] += 1
            continue
        for col in PARITY_COLS:
            exp, act = norm(src.get(col), col), norm(tgt.get(col), col)
            if exp != act:
                per_col[col] += 1
                if len(mismatches) < 25:
                    mismatches.append(
                        {"tenant_id": tenant_id, "column": col, "expected": exp, "actual": act}
                    )
    extra = sorted(set(rated) - set(oracle))
    return {
        "rows_compared": len(oracle),
        "rows_in_target_not_in_source": extra[:25],
        "rows_differing": len({m["tenant_id"] for m in mismatches}),
        "per_column_mismatches": per_col,
        "mismatch_sample": mismatches,
    }


def compare_migrated(oracle_rows: list[dict], target_rows: list[dict]) -> dict[str, Any]:
    """The periods this run does not finalize migrate verbatim: compare them to the source rows."""
    tgt = {r["id"]: r for r in target_rows if r["_origin"] == "source-migrated"}
    cols = ("period_id", "subscription_id", "used_units", "quota_units", "rollover_units",
            "billable_units", "overage_amount", "created_at")
    mismatches = []
    for src in oracle_rows:
        t = tgt.get(src["id"])
        if t is None:
            continue  # the rated period replaces its own source row; counted separately
        for col in cols:
            exp, act = norm(src.get(col), col), norm(t.get(col), col)
            if exp != act:
                mismatches.append(
                    {"id": src["id"], "column": col, "expected": exp, "actual": act}
                )
    return {
        "source_rows": len(oracle_rows),
        "target_rows": len(tgt),
        "rows_compared": len([s for s in oracle_rows if s["id"] in tgt]),
        "columns_differing": mismatches[:25],
        "rows_differing": len({m["id"] for m in mismatches}),
    }


TRANSCRIPT_FIELD_MAP = {
    "pkg_rating.fn_usage_rating": {
        "used_units": "used_units",
        "quota_units": "quota_units",
        "rollover_units": "computed_rollover_units",
        "billable_units": "billable_units",
        "first_tier_units": "first_tier_units",
        "second_tier_units": "second_tier_units",
        "overage_amount": "overage_amount",
    },
    "pkg_rating.sp_finalize_rating": {
        "used_units": "used_units",
        "quota_units": "quota_units",
        "rollover_units": "rollover_units",
        "billable_units": "billable_units",
        "overage_amount": "overage_amount",
    },
}


def transcript_checks(
    target_rows: list[dict], usage_summary: list[dict], pinned_sha: str
) -> list[dict[str, Any]]:
    """One measured comparison per transcript: eight comparisons, not one claim."""
    rated = {r["tenant_id"]: r for r in target_rows if r["_origin"] == "target-finalize"}
    checks = []
    for path in sorted(TRANSCRIPT_DIR.glob("RATING-*.json")):
        t = json.loads(path.read_text())
        scenario, entry = t["scenario"], t["oracle_entrypoint"]
        tenant = t["inputs"]["tenant_id"]
        fields = t["business_fields"]
        sot = (
            f"pinned Oracle transcript {path.relative_to(ROOT)} ({entry}), "
            f"oracle_source_sha {t['oracle_source_sha']}"
        )
        if t["oracle_source_sha"] != pinned_sha:
            checks.append(
                check(f"TRANSCRIPT-{scenario}", pinned_sha, t["oracle_source_sha"], sot,
                      note="transcript pinned to a different source SHA")
            )
            continue

        if entry == "pkg_rating.fn_usage_summary":
            got = [r for r in usage_summary if r["tenant_id"] == tenant]
            got.sort(key=lambda r: r["kind"])
            expected = {"kinds": fields["kinds"], "units": [str(u) for u in fields["units"]]}
            actual = {
                "kinds": [r["kind"] for r in got],
                "units": [norm(r["units"], "used_units") for r in got],
            }
            checks.append(
                check(
                    f"TRANSCRIPT-{scenario}",
                    expected,
                    actual,
                    sot,
                    tenant_id=tenant,
                    entrypoint=entry,
                    target_object="ported fn_usage_summary projection over ow_tp.bronze.usage_events, "
                    "emitted by the job run (the source entrypoint returns a cursor, so the unit's "
                    "three declared target objects do not persist it)",
                )
            )
            continue

        row = rated.get(tenant)
        mapping = TRANSCRIPT_FIELD_MAP[entry]
        expected = {k: norm(v, mapping[k]) for k, v in fields.items() if k in mapping}
        actual = (
            {k: norm(row.get(mapping[k]), mapping[k]) for k in expected}
            if row
            else {k: None for k in expected}
        )
        extra: dict[str, Any] = {
            "tenant_id": tenant,
            "entrypoint": entry,
            "target_columns": {k: mapping[k] for k in expected},
        }
        if entry == "pkg_rating.sp_finalize_rating":
            extra["probe_rating_result"] = t["probes"]["rating_result"]
            extra["note"] = (
                "rollover_units here is the persisted GREATEST(quota_units - used_units, 0) of D-09; "
                "the value compute_rating banked for the same tenant is the transcript RATING-002 "
                "figure and is kept in computed_rollover_units"
            )
        checks.append(check(f"TRANSCRIPT-{scenario}", expected, actual, sot, **extra))
    return checks


# -- report --------------------------------------------------------------------


def seeded_scale() -> dict[str, Any]:
    manifest = SEED_MANIFEST / "demo.json"
    if not manifest.exists():
        return {"manifest": None}
    data = json.loads(manifest.read_text())
    return {"manifest": str(manifest.relative_to(ROOT)), "seed": data}


def build_report(
    ns: str,
    oracle: dict,
    run1: dict,
    run2: dict,
    snap: dict,
    parity: dict,
    migrated: dict,
    pinned_sha: str,
    refinalize: dict,
    all_runs: list[dict],
    bank: dict,
    proration: dict,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    src = oracle["source_counts"]
    quar_rows = run2["drivers"]["quarantined_rows"]
    quar_pct = run2["drivers"]["quarantine_rate_pct"]
    drivers = run2["drivers"]

    checks.append(
        check(
            "SRC-SHA",
            {"oracle_source_sha": pinned_sha},
            {"oracle_source_sha": oracle["oracle_source_sha"]},
            f"{PINNED_SHA_FILE.relative_to(ROOT)} vs the checked-out "
            "services/legacy-billing/db/oracle tree, digested by the recipe in "
            "procs/harness/oracle_record.py",
        )
    )
    checks.append(
        check(
            "ACC-QUAR-silver_rating",
            {"loaded_plus_quarantined": src["tenants"]},
            {"loaded_plus_quarantined": drivers["loaded_rows"] + quar_rows},
            "live Oracle OW_BILLING.TENANTS COUNT(*) — one rating driver per tenant per period, "
            "the population sp_finalize_rating is called for",
            source_rows=drivers["source_rows"],
            loaded_rows=drivers["loaded_rows"],
            quarantined_rows=quar_rows,
            quarantine_pct=quar_pct,
            quarantine_by_reason=drivers["quarantine_by_reason"],
            halt_threshold_pct=5,
        )
    )
    expected_periods = drivers["loaded_rows"] + len(
        [p for p in oracle["existing_periods"] if p["period_start"] != PERIOD_START]
    )
    checks.append(
        check(
            "ROWS-rating_periods",
            {"rows": expected_periods},
            {"rows": snap["counts"]["rating_periods"]},
            f"ow_tp.silver.rating_periods COUNT(*) WHERE ns = '{ns}' (recomputed from Delta) vs "
            "live Oracle: the rated period for every non-quarantined tenant plus the source's own "
            "RATING_PERIODS rows for the other periods",
            quarantined_rows=quar_rows,
        )
    )
    checks.append(
        check(
            "ROWS-rating_results",
            {"rows": expected_periods},
            {"rows": snap["counts"]["rating_results"]},
            f"ow_tp.silver.rating_results COUNT(*) WHERE ns = '{ns}' (recomputed from Delta); "
            "sp_finalize_rating writes exactly one result per period",
            quarantined_rows=quar_rows,
        )
    )
    checks.append(
        check(
            "ACC-RATING-PARITY",
            {"rows_differing": 0, "rows_in_target_not_in_source": []},
            {
                "rows_differing": parity["rows_differing"],
                "rows_in_target_not_in_source": parity["rows_in_target_not_in_source"],
            },
            "every rated row compared column by column against the rating live Oracle computes for "
            "the same population (compute_rating/sp_finalize_rating re-expressed as one read-only "
            "SQL statement and evaluated by Oracle)",
            rows_compared=parity["rows_compared"],
            per_column_mismatches=parity["per_column_mismatches"],
            mismatch_sample=parity["mismatch_sample"],
            quarantined_rows=quar_rows,
        )
    )
    for col in PARITY_COLS:
        checks.append(
            check(
                f"PARITY-COL-rating_results.{col}",
                {"mismatches": 0},
                {"mismatches": parity["per_column_mismatches"][col]},
                f"ow_tp.silver.rating_results.{col} vs the same column computed by live Oracle, "
                f"over {parity['rows_compared']} rated tenants",
                target_type=snap["column_types"].get(f"rating_results.{col}"),
                quarantined_rows=quar_rows,
            )
        )
    checks.append(
        check(
            "ACC-MIGRATED-PARITY",
            {"rows_differing": 0},
            {"rows_differing": migrated["rows_differing"]},
            "the source's own RATING_RESULTS rows for periods this run does not finalize, compared "
            "column by column with the rows carried into ow_tp.silver.rating_results",
            source_rows=migrated["source_rows"],
            rows_compared=migrated["rows_compared"],
            columns_differing=migrated["columns_differing"],
            quarantined_rows=quar_rows,
        )
    )

    oracle_money = sum(
        decimal.Decimal(r["overage_amount"] or "0") for r in oracle["rating"].values()
    )
    checks.append(
        check(
            "ACC-MONEY-overage_amount",
            {"sum": str(oracle_money.quantize(decimal.Decimal('0.01')))},
            {"sum": snap["money"]["overage_amount_total_target_finalize"]},
            "SUM(overage_amount) as live Oracle computes it for the rated period vs SUM recomputed "
            "from ow_tp.silver.rating_results (DECIMAL(14,2), never DOUBLE)",
            rows=snap["money"]["target_finalize_rows"],
            quarantined_rows=quar_rows,
            target_type=snap["column_types"].get("rating_results.overage_amount"),
        )
    )
    oracle_migrated_money = sum(
        decimal.Decimal(r["overage_amount"] or "0")
        for r in oracle["existing_results"]
        if r["period_start"] != PERIOD_START
    )
    checks.append(
        check(
            "ACC-MONEY-overage_amount-migrated",
            {"sum": str(oracle_migrated_money.quantize(decimal.Decimal('0.01')))},
            {"sum": snap["money"]["overage_amount_total_source_migrated"]},
            "SUM(overage_amount) over live Oracle OW_BILLING.RATING_RESULTS for the periods this run "
            "does not finalize vs SUM recomputed from ow_tp.silver.rating_results",
            rows=snap["money"]["source_migrated_rows"],
            quarantined_rows=quar_rows,
        )
    )

    money_types = {k: v for k, v in snap["column_types"].items() if k.endswith("overage_amount")}
    floats = {
        k: v for k, v in snap["column_types"].items() if v.lower() in ("double", "float", "real")
    }
    checks.append(
        check(
            "ACC-MONEY-TYPES",
            {"money_columns": {k: "decimal(14,2)" for k in money_types}, "float_columns": {}},
            {"money_columns": {k: v.lower() for k, v in money_types.items()}, "float_columns": floats},
            "ow_tp.information_schema.columns for the unit's three targets (D-23/T6: money is "
            "DECIMAL(14,2) end to end and no DOUBLE appears anywhere in the unit)",
            all_column_types=snap["column_types"],
        )
    )
    checks.append(
        check(
            "ACC-NULL-PROP",
            {"wrapped_least_null_5": None, "wrapped_greatest_null_0": None},
            {
                "wrapped_least_null_5": snap["d01_probe"]["wrapped_least_null_5"],
                "wrapped_greatest_null_0": snap["d01_probe"]["wrapped_greatest_null_0"],
            },
            "D-01 probed on the warehouse: Spark's own least/greatest ignore NULL "
            f"(least(NULL,5) = {snap['d01_probe']['spark_least_null_5']}, "
            f"greatest(NULL,0) = {snap['d01_probe']['spark_greatest_null_0']}), the wrapper the "
            "pipeline uses propagates it as Oracle does",
            spark_builtin=snap["d01_probe"],
        )
    )
    checks.append(
        check(
            "ACC-MERGE-KEY",
            {"keys": [k["period_id"] for k in oracle["sample_keys"]]},
            {
                "keys": [
                    next(
                        (
                            p["id"]
                            for p in snap["periods"]
                            if p["tenant_id"] == k["tenant_id"] and p["period_start"] == PERIOD_START
                        ),
                        None,
                    )
                    for k in oracle["sample_keys"]
                ]
            },
            "pkg_ow_util.f_md5_uuid called in live Oracle for a 10-tenant sample vs the MERGE keys "
            "in ow_tp.silver.rating_periods (D-14)",
            result_id_sample=[
                {
                    "expected": k["result_id"],
                    "actual": next(
                        (
                            r["id"]
                            for r in snap["result_rows"]
                            if r["tenant_id"] == k["tenant_id"] and r["_origin"] == "target-finalize"
                        ),
                        None,
                    ),
                }
                for k in oracle["sample_keys"]
            ],
        )
    )
    checks.append(
        check(
            "ACC-NS",
            {"rows_without_ns": 0, "ns_of_every_row": ns},
            {"rows_without_ns": run2["target_counts"]["rating_results"]["rows_without_ns"], "ns_of_every_row": ns},
            f"every row in the unit's three targets carries ns = '{ns}'; rows in other namespaces "
            "are untouched by this run",
            rows_in_other_namespaces=snap["rows_in_other_namespaces"],
            volume_path=f"{LANDING_ROOT}/{ns}/{UNIT}/_runs/",
        )
    )
    checks.append(
        check(
            "ACC-QUARANTINE-SHAPE",
            {"rows_missing_required_fields": 0},
            {"rows_missing_required_fields": snap["quarantine_rows_missing_required_fields"]},
            f"ow_tp.silver.quarantine_{UNIT}: every row carries quarantine_reason, ns, source_table "
            "and the raw source payload",
            rows=snap["counts"][f"quarantine_{UNIT}"],
            by_reason=snap["quarantine"],
            closed_reason_set=json.loads(SPEC_LOCAL.read_text())["quarantine_reasons"],
        )
    )

    idem_metrics = run2["merge_metrics"]
    idem_zero = all(
        m["merge_rows_inserted"] == 0 and m["merge_rows_updated"] == 0 and m["merge_rows_deleted"] == 0
        for m in idem_metrics.values()
    )
    checks.append(
        check(
            "ACC-IDEM",
            {"second_run_rows_changed": 0, "row_counts_identical": True},
            {
                "second_run_rows_changed": sum(
                    m["merge_rows_inserted"] + m["merge_rows_updated"] + m["merge_rows_deleted"]
                    for m in idem_metrics.values()
                ),
                "row_counts_identical": run1["target_counts"] == run2["target_counts"],
            },
            "Delta MERGE operationMetrics read from the second identical run's own MERGE commit "
            "in DESCRIBE HISTORY (the latest MERGE, so a managed OPTIMIZE commit landing after it "
            "cannot be mistaken for the write)",
            passed=idem_zero and run1["target_counts"] == run2["target_counts"],
            run1=run1["merge_metrics"],
            run2=idem_metrics,
        )
    )

    if refinalize["performed"]:
        checks.append(
            check(
                "REFINALIZE-UPDATE-SET",
                {
                    "columns_held_at_first_finalize_unchanged": True,
                    "money_or_usage_columns_updated": True,
                    "row_restored_after_the_probe": True,
                },
                {
                    "columns_held_at_first_finalize_unchanged": refinalize["held_unchanged"],
                    "money_or_usage_columns_updated": bool(
                        refinalize["columns_updated_by_the_rerate"]
                    ),
                    "row_restored_after_the_probe": refinalize["restored_to_pre_probe_values"],
                },
                "ow_tp.silver.rating_results read back from Delta before, after and after undoing a "
                "re-rate of one tenant on a corrected plan supplied as a per-run notebook input (Oracle and "
                "ow_tp.bronze.* untouched), against sp_finalize_rating's DUP_VAL_ON_INDEX UPDATE set",
                tenant_id=refinalize["tenant_id"],
                source_update_set=list(REFINALIZE_UPDATED),
                source_columns_left_at_first_finalize=list(REFINALIZE_HELD),
                columns_updated_by_the_rerate=refinalize["columns_updated_by_the_rerate"],
                held_columns=refinalize["columns_held_at_first_finalize"],
                row_before=refinalize["row_before"],
                row_after_rerate=refinalize["row_after_rerate"],
                row_after_restore=refinalize["row_after_restore"],
                quarantined_rows=quar_rows,
            )
        )
    if bank["performed"]:
        checks.append(
            check(
                "BANK-SILVER-PICKUP",
                {
                    "current_run_bank_rows_from_silver": bank["bank_read_by_the_current_run"][
                        "bank_rows_from_silver"
                    ],
                    "money_moved": True,
                },
                {
                    "current_run_bank_rows_from_silver": bank["bank_read_by_the_current_run"][
                        "bank_rows_from_silver"
                    ],
                    "money_moved": decimal.Decimal(bank["money"]["moved_by"]) != 0,
                },
                f"the {PERIOD_START} run's rollover bank, read back from the job run after "
                f"{PRECEDING_PERIOD_START} had been finalized into "
                f"{CATALOG}.{SCHEMA}.rating_results by this same unit",
                passed=(
                    bank["bank_read_by_the_current_run"]["bank_rows_from_silver"] > 0
                    and decimal.Decimal(bank["money"]["moved_by"]) != 0
                ),
                bank=bank["bank_read_by_the_current_run"],
                money=bank["money"],
                consequence="with the bank read from bronze alone the second period is priced off "
                "a stale bank and the difference is silent",
            )
        )
        bronze_first = [
            r
            for r in bank["bank_read_by_the_current_run"]["sample"]
            if r["bank_rows_from_bronze"] > 0
        ]
        checks.append(
            check(
                "BANK-BRONZE-PRECEDENCE",
                {"silver_rows_used_where_bronze_has_the_period": 0},
                {
                    "silver_rows_used_where_bronze_has_the_period": sum(
                        r["bank_rows_from_silver"] for r in bronze_first
                    )
                },
                "the tenants whose bank draws on bronze, measured in the job run while the same "
                f"period existed in both {CATALOG}.{BRONZE}.rating_results and "
                f"{CATALOG}.{SCHEMA}.rating_results: the source stays authoritative and silver "
                "fills only the periods it alone rated",
                passed=bool(bronze_first)
                and sum(r["bank_rows_from_silver"] for r in bronze_first) == 0,
                tenants=bronze_first,
                deduplicated_per=["tenant_id", "period_start"],
                note=f"the source's own {PRECEDING_PERIOD_START} row for these tenants is in "
                "bronze, and the target finalized that period too, so both sides held it and "
                "exactly one row entered the bank",
            )
        )
        checks.append(
            check(
                "ACC-MONEY-overage_amount-WITH-SILVER-BANK",
                {
                    "sum": bank["money"]["oracle_with_the_silver_bank"],
                    "rows_differing": 0,
                },
                {
                    "sum": bank["money"]["current_period_with_the_silver_bank"][
                        "overage_amount_total"
                    ],
                    "rows_differing": bank["parity_with_bank"]["rows_differing"],
                },
                "SUM(overage_amount) and the row-by-row comparison for the current period once the "
                "preceding period was banked: live Oracle evaluating its own rating statement with "
                "the silver bank rows supplied to it, vs the value recomputed from "
                f"{CATALOG}.{SCHEMA}.rating_results",
                rows_compared=bank["parity_with_bank"]["rows_compared"],
                per_column_mismatches=bank["parity_with_bank"]["per_column_mismatches"],
                mismatch_sample=bank["parity_with_bank"]["mismatch_sample"],
                silver_bank_rows_handed_to_oracle=bank["silver_bank_rows_handed_to_oracle"],
            )
        )
        checks.append(
            check(
                "BANK-PRECEDING-PERIOD-PARITY",
                {"rows_differing": 0},
                {"rows_differing": bank["preceding_period_parity"]["rows_differing"]},
                f"the preceding period ({PRECEDING_PERIOD_START}..{PRECEDING_PERIOD_END}) as this "
                "unit rated it, compared column by column against live Oracle for the same period",
                rows_compared=bank["preceding_period_parity"]["rows_compared"],
                per_column_mismatches=bank["preceding_period_parity"]["per_column_mismatches"],
                money=bank["preceding_period_money"],
                drivers=bank["runs"]["preceding_period"]["drivers"],
                note="all usage in this population falls in the current period, so the preceding "
                "period prices nothing and banks rollover: that is what the current period then "
                "reads",
            )
        )
        checks.append(
            check(
                "BANK-IDEM",
                {"rows_changed_on_the_identical_rerun": 0},
                {
                    "rows_changed_on_the_identical_rerun": sum(
                        m["merge_rows_inserted"] + m["merge_rows_updated"] + m["merge_rows_deleted"]
                        for m in bank["rerun_merge_metrics"].values()
                    )
                },
                "Delta MERGE operationMetrics from the second identical run of the current period "
                "while both periods were finalized: reading its own history back does not make the "
                "unit non-idempotent",
                merge_metrics=bank["rerun_merge_metrics"],
            )
        )

    if proration["performed"]:
        checks.append(
            check(
                "PRORATION-FRACTIONAL-DAY",
                {
                    "cases": [c["oracle"] for c in proration["cases"]],
                    "midday_differs_from_a_truncated_date": True,
                },
                {
                    "cases": [c["target"] for c in proration["cases"]],
                    "midday_differs_from_a_truncated_date": proration[
                        "midday_differs_from_truncated"
                    ],
                },
                "(p_period_end - v_suspended_on + 1) / (p_period_end - p_period_start + 1) with "
                "ROUND(billable * factor) and ROUND(overage * factor, 2) after it, evaluated by live "
                "Oracle on three synthetic suspension timestamps, against the same three timestamps "
                "pushed through the generated expression the job applies (DECIMAL whole-second "
                "arithmetic, never DOUBLE). A probe of both expressions on synthetic input: it is "
                "not a finding about the source and it writes nothing",
                cases=proration["cases"],
                inputs=proration["inputs"],
                period=proration["period"],
                consequence="a suspension at midday is 13.5 days into the period, not 14, so a "
                "to_date()-truncated subtraction moves overage_amount, which T1 holds exact to the "
                "cent",
            )
        )

    probe = run2.get("overflow_probe", {})
    probe_cases = probe.get("cases", [])
    checks.append(
        check(
            "QUAR-NUMERIC_OVERFLOW-REACHABLE",
            {"reasons": ["NUMERIC_OVERFLOW", None]},
            {"reasons": [c["quarantine_reason"] for c in probe_cases]},
            "a synthetic amount beyond DECIMAL(14,2) and an in-range control, pushed through the "
            "pinned-type cast and the same generated overflow predicate the load applies, evaluated "
            "by the job run. A probe of the target expression: it is not a finding about the source "
            "and it writes nothing",
            cases=probe_cases,
            predicate_reads="the pre-cast *_raw columns, so the cast cannot null or truncate the "
            "value before the guard sees it",
            live_overflow_rows=drivers["quarantine_by_reason"].get("NUMERIC_OVERFLOW", 0),
        )
    )
    checks.append(
        check(
            "QUAR-PERSISTED-BEFORE-HALT",
            {"quarantine_merged_before_halt_decision": True},
            {
                "quarantine_merged_before_halt_decision": bool(
                    run2.get("refinalize", {}).get("quarantine_persisted_before_halt_decision")
                )
            },
            "the job merges the rejected rows into the quarantine table and only then compares the "
            "rate with the 5% threshold and raises, so a halted run leaves the operator the payloads "
            "that caused it while no rating row is written",
            quarantine_merge_metrics=run2["merge_metrics"].get(f"quarantine_{UNIT}"),
            halt_threshold_pct=5,
            measured_quarantine_rate_pct=quar_pct,
        )
    )

    checks.extend(transcript_checks(snap["result_rows"], run2["usage_summary"], pinned_sha))

    anomalies = run2["anomaly_detections"]
    for aid in EXPECTED_ANOMALIES:
        det = anomalies.get(aid, {})
        checks.append(
            check(
                f"ANOMALY-{aid}",
                {"detected": True},
                {"detected": bool(det.get("detected"))},
                f"detector run by the job over ns = '{ns}': {det.get('detector', 'MISSING')}",
                evidence={k: v for k, v in det.items() if k not in ("detected", "detector")},
            )
        )

    failed = [c["id"] for c in checks if c["result"] == "fail"]
    actual_anomalies = [a for a in EXPECTED_ANOMALIES if anomalies.get(a, {}).get("detected")]
    unverified = [
        "Lakehouse Federation from the workspace to the OW_BILLING service is not reachable "
        "(wave 1 established this), so no single query joins source to target. Each side is "
        "measured independently — Oracle by a read-only session, the target by the SQL warehouse — "
        "and compared row by row here.",
        "The Oracle side of the parity comparison is compute_rating/sp_finalize_rating re-expressed "
        "as one read-only SQL statement evaluated by Oracle, not the PL/SQL package executed. The "
        "package itself is not run against the source (that would write RATING_PERIODS/"
        "RATING_RESULTS rows and mutate the estate); the eight pinned transcripts are what tie the "
        "re-expression to the real engine.",
        f"ANOM-ROWNUM-1: no tenant in ns = '{ns}' has two covering subscriptions with the same "
        "starts_on (measured: "
        f"{anomalies.get('ANOM-ROWNUM-1', {}).get('tenants_with_tied_starts_on')} tied, "
        f"{anomalies.get('ANOM-ROWNUM-1', {}).get('tenants_with_more_than_one_covering_subscription')} "
        "with more than one candidate), so the source's nondeterministic tie is not exercised. The "
        "target's ORDER BY starts_on DESC, id DESC tie-break (D-08) is therefore implemented but "
        "unverified against a tie.",
        "Quarantine is empty on this population: FK_ORPHAN (D-19 NO_COVERING_PLAN), CODE_UNKNOWN "
        "(D-16), KEY_NULL, KEY_DUPLICATE and NUMERIC_OVERFLOW are all implemented and their live "
        "exposure measured as zero, so the quarantine write path itself is exercised by no row "
        "here — implemented and unverified, not proven.",
        "Divergence — orphan RATING_PERIODS row on a failed finalize: sp_finalize_rating INSERTs the "
        "RATING_PERIODS row before it calls compute_rating, so a tenant whose RATING_RESULTS insert "
        "then raises (the D-19 NO_COVERING_PLAN case, NULL quota_units/subscription_id into NOT NULL "
        "columns) leaves an orphan period row with no result behind in the source. This port "
        "quarantines that tenant and writes neither a period nor a result row, preferring a "
        "quarantined reject over a period row whose money never landed. That is a real behavioural "
        "difference, invisible on this population only because quarantine is 0 rows: it becomes a "
        "rating_periods row-count parity delta of one row per affected tenant (source higher) as "
        "soon as quarantine is non-empty.",
        "D-05/T4 (two-digit years resolving into the current century) is not reached by this unit: "
        "rating reads DATE and TIMESTAMP columns only, so pkg_ow_util.f_str2dt and its swallowed "
        "WHEN OTHERS are never called on this path.",
        "compute_rating ends with a pkg_ow_util.log_msg autonomous-transaction audit write. That "
        "audit trail is bronze_hist's target (BILLING_AUDIT_LOG), not this unit's, so the rating "
        "run's audit rows are not produced here and no audit parity is claimed.",
        "Suspension proration is exercised by one tenant in this population (the only subscription "
        "with status_cd = 20 and a suspended_on inside the period), pinned by transcript RATING-003. "
        "Every suspended_on in the fixture sits at midnight, so the fractional-day half of Oracle's "
        "DATE arithmetic is reached by no source row: it is measured on three labelled synthetic "
        "timestamps (midday, midnight, one second before the next midnight) evaluated by both "
        "engines and compared (PRORATION-FRACTIONAL-DAY). Proration on a live row carrying a time "
        "component is therefore implemented and unverified against source data.",
        "The two-period bank proof rates "
        f"{PRECEDING_PERIOD_START}..{PRECEDING_PERIOD_END} into silver and then rates "
        f"{PERIOD_START}..{PERIOD_END} again, so the bank it reads back is a period this unit "
        "finalized rather than one the source finalized independently — the source has no such "
        "period, which is the reason the silver side of the bank exists at all. The with-bank "
        "reference is live Oracle evaluating its own rating statement with those silver rows "
        "supplied to it, not a source-executed two-period run (executing the package would write "
        "into the estate). The probe's rows are then removed from this unit's own two targets and "
        "the current period is rated once more, so every number outside rollover_bank_proof is "
        "measured in the source-equivalent state.",
        "The eight pinned transcripts and the headline money parity are measured in that "
        "source-equivalent state, where the bank holds exactly what the source's own RATING_RESULTS "
        "holds. In the two-period state the same tenants' billable_units and overage_amount "
        "legitimately differ, because the bank is larger by the rollover this unit banked for the "
        "preceding period; that state carries its own measured Oracle comparison "
        "(ACC-MONEY-overage_amount-WITH-SILVER-BANK) instead of being compared with transcripts "
        "pinned to a different bank.",
        "The re-finalize update set is proven on the target: one tenant is re-rated on a corrected "
        "plan supplied as a per-run notebook input (neither Oracle nor ow_tp.bronze.* is touched, and "
        "the deployed job declares no such parameter, so no operator run can rate from it), and the "
        "row is read back before, after and after undoing it. The source side of "
        "that behaviour is read from sp_finalize_rating's DUP_VAL_ON_INDEX handler rather than "
        "executed, because running the package would write RATING_PERIODS/RATING_RESULTS rows into "
        "the source. A source-executed re-rate is therefore unverified."
        if refinalize["performed"]
        else "The re-finalize update set could not be exercised on this population: "
        + refinalize.get("reason", "no reason recorded")
        + " The narrowed update is therefore implemented and unverified.",
        "The ns = 'demo' slice of the shared workspace is visible to other sessions holding the same "
        "PAT. This recon is re-runnable and every number is recomputed from the Delta targets after "
        "the second run, but it cannot prove no other session wrote between the two runs.",
    ]

    return {
        "kind": "recon-report",
        "unit": UNIT,
        "namespace": ns,
        "generated_at": now_iso(),
        "run_mode": "live",
        "recon_result": "green" if not failed else "red",
        "values_recomputed_from_target": True,
        "failed_checks": failed,
        "checks": checks,
        "idempotency_rerun": {
            "performed": True,
            "result": "pass" if idem_zero and run1["target_counts"] == run2["target_counts"] else "fail",
            "evidence": (
                f"run 1 = serverless run {run1['run_id']} (batch {run1['batch_id']}), "
                f"run 2 = serverless run {run2['run_id']} (batch {run2['batch_id']}), identical "
                f"parameters (ns={ns}, period {PERIOD_START}..{PERIOD_END}, no plan override). "
                f"These are the last two of {len(all_runs)} runs: the re-finalize probe and the run "
                f"that undoes it precede them, so the pair proves the no-op on the same state every "
                f"other number in this report is measured from. Second-run Delta MERGE "
                f"metrics: {json.dumps(idem_metrics, sort_keys=True)}. Row counts after each run: "
                f"{json.dumps({'run1': run1['target_counts'], 'run2': run2['target_counts']}, sort_keys=True)}"
            ),
        },
        "planted_anomaly_detections": {
            "expected_set": EXPECTED_ANOMALIES,
            "actual_set": actual_anomalies,
            "missing": [a for a in EXPECTED_ANOMALIES if a not in actual_anomalies],
            "unexpected": [a for a in anomalies if a not in EXPECTED_ANOMALIES],
            "detail": anomalies,
        },
        "unverified_paths": unverified,
        "refinalize_proof": refinalize,
        "rollover_bank_proof": bank,
        "suspension_proration_proof": proration,
        "provenance": {
            "source": {
                "system": "Oracle OW_BILLING (live)",
                "oracle_version": oracle["oracle_banner"],
                "db_name": os.getenv("DB_SERVICE", "FREEPDB1"),
                "schema": "OW_BILLING",
                "oracle_source_sha": oracle["oracle_source_sha"],
                "package": "services/legacy-billing/db/oracle/packages/03_pkg_rating.sql",
                "counts": src,
                "read_only": True,
            },
            "seeded_scale": seeded_scale(),
            "target": {
                "catalog": CATALOG,
                "schema": SCHEMA,
                "tables": [
                    f"{CATALOG}.{SCHEMA}.rating_periods",
                    f"{CATALOG}.{SCHEMA}.rating_results",
                    f"{CATALOG}.{SCHEMA}.quarantine_{UNIT}",
                ],
                "bronze_inputs_read_only": run2["bronze_inputs"],
                "compute": "serverless job compute for the notebook runs; pre-existing Serverless "
                "Starter Warehouse (565cd2fd713738c4) for the recon SQL. No cluster or warehouse "
                "was created.",
                "row_counts": snap["counts"],
                "money": snap["money"],
                "column_types": snap["column_types"],
            },
            "period": {"start": PERIOD_START, "end": PERIOD_END},
            "job_runs": [
                {
                    "batch_id": r["batch_id"],
                    "run_id": r["run_id"],
                    "run_page_path": r["run_page_path"],
                }
                for r in all_runs
            ],
            "baseline": {
                "transcripts": sorted(p.name for p in TRANSCRIPT_DIR.glob("RATING-*.json")),
                "pinned_sha_file": str(PINNED_SHA_FILE.relative_to(ROOT)),
                "note": "procs/transcripts/ (Postgres) is a cross-check set and is not the baseline",
            },
        },
    }


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ns = "demo"
    if "--ns" in argv:
        ns = argv[argv.index("--ns") + 1]

    pinned_sha = PINNED_SHA_FILE.read_text().strip()
    computed_sha = oracle_truth.oracle_source_sha()
    if pinned_sha != computed_sha:
        raise Halt(
            f"pinned Oracle source SHA {pinned_sha} != checked-out tree {computed_sha}: "
            "stop and report, the transcripts no longer describe this source"
        )
    print(f"[sha] {computed_sha} matches {PINNED_SHA_FILE.name}")

    oracle = oracle_truth.snapshot(PERIOD_START, PERIOD_END)
    print(f"[oracle] counts={oracle['source_counts']} rated_tenants={len(oracle['rating'])}")

    dbx = Dbx()
    deploy(dbx)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")
    first = run_notebook(dbx, ns, f"{stamp}a")
    print(f"[run a] {first['run_id']} drivers={first['drivers']}")

    if first["drivers"]["quarantine_rate_pct"] > 5:
        raise Halt(
            f"quarantine rate {first['drivers']['quarantine_rate_pct']}% exceeds 5%: halting the unit"
        )

    # The re-finalize path is measured on the loaded population, then undone, so every number the
    # report carries is measured after the tenant is back on its own plan.
    probe_base = run_notebook(dbx, ns, f"{stamp}b")
    print(f"[run b] {probe_base['run_id']} merge={json.dumps(probe_base['merge_metrics'])}")
    refinalize = refinalize_probe(dbx, ns, target_snapshot(dbx, ns), stamp)
    print(
        "[refinalize] performed={performed} held_unchanged={held} moved={moved} "
        "restored={restored}".format(
            performed=refinalize["performed"],
            held=refinalize.get("held_unchanged"),
            moved=refinalize.get("columns_updated_by_the_rerate"),
            restored=refinalize.get("restored_to_pre_probe_values"),
        )
    )

    # The rollover bank: rate the preceding period, rate this one again off the bank that now holds
    # it, prove the pickup and the money it moves, then undo the probe.
    bank = bank_proof(dbx, ns, stamp, target_snapshot(dbx, ns)["money_by_period"][PERIOD_START])
    print(
        "[bank] silver_rows={rows} money {before} -> {after} (moved {moved}) "
        "oracle_with_bank={oracle} parity_rows_differing={diff}".format(
            rows=bank["bank_read_by_the_current_run"]["bank_rows_from_silver"],
            before=bank["money"]["current_period_before_the_preceding_period_existed"][
                "overage_amount_total"
            ],
            after=bank["money"]["current_period_with_the_silver_bank"]["overage_amount_total"],
            moved=bank["money"]["moved_by"],
            oracle=bank["money"]["oracle_with_the_silver_bank"],
            diff=bank["parity_with_bank"]["rows_differing"],
        )
    )

    # The pair the idempotency proof is made on: two identical runs after both probes are undone,
    # back in the state whose bank is the source's own.
    run1 = run_notebook(dbx, ns, f"{stamp}g")
    print(f"[run g] {run1['run_id']} merge={json.dumps(run1['merge_metrics'])}")
    run2 = run_notebook(dbx, ns, f"{stamp}h")
    print(f"[run h] {run2['run_id']} merge={json.dumps(run2['merge_metrics'])}")

    proration = proration_cross_check(run2)
    print(f"[proration] all_agree={proration.get('all_agree')}")

    if run2["drivers"]["quarantine_rate_pct"] > 5:
        raise Halt(
            f"quarantine rate {run2['drivers']['quarantine_rate_pct']}% exceeds 5%: halting the unit"
        )

    snap = target_snapshot(dbx, ns)
    parity = compare_rating(oracle["rating"], snap["result_rows"])
    migrated = compare_migrated(
        [r for r in oracle["existing_results"] if r["period_start"] != PERIOD_START],
        snap["result_rows"],
    )
    all_runs = [first, probe_base]
    if refinalize["performed"]:
        all_runs += [
            {**refinalize["run3"], "run_page_path": None},
            {**refinalize["run4_restore"], "run_page_path": None},
        ]
    all_runs += [{**r, "run_page_path": r.get("run_page_path")} for r in bank["all_runs"]]
    all_runs += [run1, run2]
    report = build_report(
        ns,
        oracle,
        run1,
        run2,
        snap,
        parity,
        migrated,
        pinned_sha,
        refinalize,
        all_runs,
        bank,
        proration,
    )

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(f"[recon] {report['recon_result']} -> {REPORT_PATH.relative_to(ROOT)}")
    if report["failed_checks"]:
        print(f"[recon] FAILED: {report['failed_checks']}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
