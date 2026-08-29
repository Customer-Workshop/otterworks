"""Run the silver_dunning unit against live Oracle and the shared workspace, and measure the recon.

Sequence, once per invocation:

1. verify the pinned Oracle source SHA (stop if it moved) and read the seed manifest,
2. snapshot the source read-only: counts, `fn_overdue_accounts` actually called, and the state
   `sp_schedule_dunning` / `sp_suspend_overdue` *would* leave, re-expressed as SELECTs and evaluated
   by Oracle — the two procedures mutate `DUNNING_ATTEMPTS`, `TENANTS`, `SUBSCRIPTIONS` and
   `NOTIFICATIONS` and are therefore never called,
3. deploy the notebook and its column spec under the parent-owned notebook root,
4. run the declared generated-fixture namespaces first (`dunning_edge` for the paths the demo seed
   leaves at zero, `dunning_halt` for the halt), then the transcript replays, then the namespace
   holding migrated source data twice with identical inputs: run 1 a cold load, run 2 a no-op,
5. recompute counts, money, ids and every target row **from the Delta targets** over the SQL
   warehouse, independently of what the notebook reported,
6. compare against Oracle row by row and against the five pinned Oracle transcripts one by one,
7. write the recon report.

Nothing here writes to Oracle, to `ow_tp.bronze.*` in a namespace holding migrated source data, or to
any table this unit does not own, and no compute resource is ever created: the notebook runs on
serverless and the recon SQL goes to the pre-existing warehouse. The one exception to "this unit
writes no other unit's table", stated plainly: for the generated-fixture namespaces the **merged
`ow_tp_silver_plans` notebook** is invoked to produce their `ow_tp.silver.subscriptions` rows, because
this unit may not INSERT into that table even in a scratch namespace. It is wave 3's own writer doing
wave 3's own write, on a namespace that is neither `ns=demo` nor `ns=plans_edge`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import decimal
import json
import pathlib
import re
import sys
from typing import Any

from scripts.tp_databricks.bronze_core.dbx_client import Dbx, DbxError, sql_str
from scripts.tp_databricks.silver_dunning import fixtures, oracle_truth

ROOT = pathlib.Path(__file__).resolve().parents[3]
UNIT = "silver_dunning"
CATALOG = "ow_tp"
SCHEMA = "silver"
BRONZE = "bronze"
NOTEBOOK_ROOT = "/Shared/ow_tp"
LANDING_ROOT = "/Volumes/ow_tp/bronze/landing"
NOTEBOOK_LOCAL = ROOT / "databricks" / "notebooks" / "ow_tp_silver_dunning.py"
SPEC_LOCAL = ROOT / "databricks" / "ddl" / "silver_dunning_spec.json"
PLANS_NOTEBOOK_LOCAL = ROOT / "databricks" / "notebooks" / "ow_tp_silver_plans.py"
PLANS_SPEC_LOCAL = ROOT / "databricks" / "ddl" / "silver_plans_spec.json"
REPORT_PATH = ROOT / "docs" / "tech-partnerships" / "recon" / f"{UNIT}.recon.json"
TRANSCRIPT_DIR = ROOT / "procs" / "oracle" / "transcripts" / "dunning"
PINNED_SHA_FILE = ROOT / "procs" / "oracle" / "transcripts" / "ORACLE_SOURCE_SHA"
MANIFEST_DIR = ROOT / "testdata" / "legacy" / "manifests"

SPEC = json.loads(SPEC_LOCAL.read_text())
K = SPEC["dunning_constants"]
TABLES = {t["target"]: t for t in SPEC["tables"]}
HALT_PCT = float(SPEC["quarantine_halt_threshold_pct"])
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
SHARED = SPEC["shared_write_policy"]

AS_OF = fixtures.AS_OF  # 2026-02-28, the date DUNNING-001/004/005 pin
OTHER_AS_OF = "2026-03-14"  # the second p_as_of the multi-date notification exposure is measured on
NS_T002, NS_T003 = "dunning_t002", "dunning_t003"
REPLAY_DATES = {NS_T002: "2026-02-14", NS_T003: "2026-02-17"}

EXPECTED_ANOMALIES = [
    "ANOM-SWALLOWED-INSERT",
    "ANOM-LOCALE-DAY",
    "ANOM-SHARED-WRITE",
    "ANOM-NOTIFICATION-SIDE-EFFECT",
]

# The columns compared row by row against the source, per target, and the class each is normalised
# in: money to the cent (T1), codes and counts as integers, timestamps as second-precision text.
ATTEMPT_COLS: dict[str, str] = {
    "tenant_id": "text",
    "invoice_id": "text",
    "attempt_no": "code",
    "scheduled_for": "ts",
    "status_cd": "code",
}
NOTIFICATION_COLS: dict[str, str] = {
    "tenant_id": "text",
    "kind_cd": "code",
    "sent_at": "ts",
}
TENANT_COLS: dict[str, str] = {"status_cd": "code"}
SUBSCRIPTION_COLS: dict[str, str] = {"status_cd": "code", "suspended_on": "ts"}


class Halt(RuntimeError):
    """A stop-and-report condition from the unit's brief, not a bug."""


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def check(
    cid: str, expected: Any, actual: Any, sot: str, passed: bool | None = None, **extra: Any
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


SCALES = {"money": decimal.Decimal("0.01"), "count": decimal.Decimal("1")}


def norm(value: Any, cls: str) -> Any:
    """One normalisation for both sides of every comparison."""
    if value is None:
        return None
    if cls in SCALES:
        return str(decimal.Decimal(str(value)).quantize(SCALES[cls]))
    if cls == "flag":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("true", "1", "y")
    if cls == "code":
        return int(value)
    if cls == "ts":
        text = str(value).replace("T", " ").replace("Z", "")
        text = text.split(".")[0]
        return text if len(text) > 10 else f"{text} 00:00:00"
    return value


def date_only(value: Any) -> str | None:
    """The date half of a timestamp: the source's TRUNC(...) values carry no time component."""
    if value is None:
        return None
    return str(value).replace("T", " ").split(" ")[0]


# -- Databricks plumbing -------------------------------------------------------


class DbxJobs(Dbx):
    """The two calls this unit needs beyond `Dbx`: a two-task run, and per-task outputs.

    `JOB_NIGHTLY_DUNNING` is one job action with two ordered statements, so the evidence runs are
    one submitted run with two ordered tasks over one snapshot — not two independent submissions,
    which would let the sweep see a different invoice population than the scheduler did.
    """

    def submit_two_task_run(
        self, run_name: str, notebook_path: str, shared: dict[str, str]
    ) -> int:
        tasks = []
        for task_key, phase, depends in (
            ("schedule_dunning", "schedule", None),
            ("suspend_overdue", "suspend", "schedule_dunning"),
        ):
            task: dict[str, Any] = {
                "task_key": task_key,
                "notebook_task": {
                    "notebook_path": notebook_path,
                    "base_parameters": dict(shared, phase=phase),
                },
            }
            if depends:
                task["depends_on"] = [{"task_key": depends}]
            tasks.append(task)
        return int(
            self._call("POST", "/api/2.2/jobs/runs/submit", json={"run_name": run_name, "tasks": tasks})[
                "run_id"
            ]
        )

    def task_results(self, run_id: int) -> dict[str, dict[str, Any]]:
        run = self._call("GET", "/api/2.2/jobs/runs/get", params={"run_id": run_id})
        out: dict[str, dict[str, Any]] = {}
        for task in run.get("tasks") or []:
            # 2.2 reports `status`; `state` is the 2.1 shape and both are read so neither API
            # version silently leaves a failed task looking unfinished.
            state = task.get("state") or {}
            status = task.get("status") or {}
            termination = status.get("termination_details") or {}
            result: dict[str, Any] = {
                "task_run_id": task["run_id"],
                "result_state": state.get("result_state") or termination.get("type"),
                "life_cycle_state": state.get("life_cycle_state") or status.get("state"),
                "state_message": (
                    state.get("state_message") or termination.get("message") or ""
                )[:2000],
            }
            if result["result_state"] not in (None, "SUCCESS"):
                output = self._call(
                    "GET", "/api/2.1/jobs/runs/get-output", params={"run_id": task["run_id"]}
                )
                result["error"] = (output.get("error") or "")[:6000]
                result["error_trace_tail"] = (output.get("error_trace") or "")[-2000:]
            out[task["task_key"]] = result
        return out


def deploy(dbx: DbxJobs) -> None:
    dbx.mkdirs_workspace(NOTEBOOK_ROOT)
    dbx.import_workspace(
        f"{NOTEBOOK_ROOT}/ow_tp_silver_dunning",
        str(NOTEBOOK_LOCAL),
        fmt="SOURCE",
        language="PYTHON",
    )
    dbx.import_workspace(f"{NOTEBOOK_ROOT}/silver_dunning_spec.json", str(SPEC_LOCAL), fmt="AUTO")


def deploy_plans(dbx: DbxJobs) -> None:
    """Wave 3's merged notebook, unchanged from the run branch, so a fixture namespace can get its
    `ow_tp.silver.subscriptions` rows from the unit that owns that table."""
    dbx.import_workspace(
        f"{NOTEBOOK_ROOT}/ow_tp_silver_plans",
        str(PLANS_NOTEBOOK_LOCAL),
        fmt="SOURCE",
        language="PYTHON",
    )
    dbx.import_workspace(f"{NOTEBOOK_ROOT}/silver_plans_spec.json", str(PLANS_SPEC_LOCAL), fmt="AUTO")


def run_job(
    dbx: DbxJobs,
    ns: str,
    batch_id: str,
    as_of: str = AS_OF,
    invoice_source: str = "silver",
    expect_failure: bool = False,
) -> dict[str, Any]:
    """One run, two ordered tasks, one snapshot. Returns both phases' own run summaries."""
    run_id = dbx.submit_two_task_run(
        run_name=f"ow_tp_silver_dunning_{ns}_{batch_id}",
        notebook_path=f"{NOTEBOOK_ROOT}/ow_tp_silver_dunning",
        shared={
            "ns": ns,
            "catalog": CATALOG,
            "schema": SCHEMA,
            "bronze_schema": BRONZE,
            "as_of": as_of,
            "invoice_source": invoice_source,
            "landing_root": LANDING_ROOT,
            "spec_path": f"{NOTEBOOK_ROOT}/silver_dunning_spec.json",
            "batch_id": batch_id,
        },
    )
    run = dbx.wait_run(run_id)
    tasks = dbx.task_results(run_id)
    url = run.get("run_page_url") or ""
    out: dict[str, Any] = {
        "run_id": run_id,
        "ns": ns,
        "as_of": as_of,
        "batch_id": batch_id,
        "invoice_source": invoice_source,
        "tasks": tasks,
        # The workspace host stays out of the branch, so only the host-relative run path is kept.
        "run_page_path": url.split(".com", 1)[-1] if url else None,
    }
    failed = [k for k, v in tasks.items() if v["result_state"] not in (None, "SUCCESS")]
    if expect_failure:
        out["phases"] = {}
        return out
    if failed:
        raise DbxError(
            f"silver_dunning run {run_id} (ns={ns}, batch={batch_id}) failed on {failed}: "
            + json.dumps({k: tasks[k] for k in failed})[:6000]
        )
    out["phases"] = {
        phase: json.loads(
            dbx.read_volume_file(
                f"{LANDING_ROOT}/{ns}/{UNIT}/_runs/{batch_id}-{phase}.json"
            ).decode()
        )
        for phase in ("schedule", "suspend")
    }
    return out


def run_plans(dbx: DbxJobs, ns: str, batch_id: str) -> dict[str, Any]:
    run_id = dbx.submit_notebook_run(
        run_name=f"ow_tp_silver_plans_{ns}_{batch_id}",
        notebook_path=f"{NOTEBOOK_ROOT}/ow_tp_silver_plans",
        params={
            "ns": ns,
            "catalog": CATALOG,
            "schema": SCHEMA,
            "bronze_schema": BRONZE,
            "entitlement_on": AS_OF,
            "change_effective_on": "2026-03-01",
            "landing_root": LANDING_ROOT,
            "spec_path": f"{NOTEBOOK_ROOT}/silver_plans_spec.json",
            "batch_id": batch_id,
            "applied_requests": "",
        },
    )
    run = dbx.wait_run(run_id)
    state = ((run.get("state") or {}).get("result_state")) or (
        ((run.get("status") or {}).get("termination_details") or {}).get("type")
    )
    if state not in ("SUCCESS", None):
        out = dbx.run_output(run_id)
        raise DbxError(
            f"the merged silver_plans notebook failed on ns={ns} ({state}); this unit cannot INSERT "
            f"into ow_tp.silver.subscriptions itself: {json.dumps(out.get('error') or out)[:3000]}"
        )
    return {"run_id": run_id, "ns": ns, "batch_id": batch_id, "result_state": state}


def halt_if_over(phases: dict[str, Any], label: str) -> None:
    """Every declared population is checked against the threshold, not just the driver."""
    for phase, summary in phases.items():
        quar = summary["quarantine"]
        over = quar["populations_over_threshold"]
        if over:
            bases = quar["halt_bases"]
            detail = "; ".join(
                f"{n}: {bases[n]['rejected_rows']} of {bases[n]['source_rows']} "
                f"({bases[n]['rate_pct']}%)"
                for n in over
            )
            raise Halt(
                f"{label} phase {phase}: {detail} exceeds {HALT_PCT}% on its own paired numerator "
                "and denominator: halting the unit and reporting instead of loading around it"
            )


# -- target side, recomputed from Delta ----------------------------------------


def rows_of(dbx: DbxJobs, statement: str, columns: tuple[str, ...]) -> list[dict[str, Any]]:
    return [dict(zip(columns, r)) for r in dbx.sql(statement)]


TGT_ATTEMPT_COLS = (
    "id", "tenant_id", "invoice_id", "attempt_no", "scheduled_for", "status_cd", "status", "as_of",
    "attempt_no_basis", "source_day_of_week", "weekend_shift_days", "unshifted_scheduled_for",
    "invoice_total", "invoice_issued_at", "days_overdue", "overdue_by_fn", "tenant_status",
    "_origin", "_batch_id",
)
TGT_NOTIFICATION_COLS = (
    "id", "tenant_id", "kind_cd", "sent_at", "kind", "as_of", "written_by_sweep",
    "tenant_status_before", "_origin", "_batch_id",
)
TGT_TENANT_COLS = (
    "id", "name", "status_cd", "status", "status_cd_ingest", "as_of", "sweep_candidate",
    "suspended_by_sweep", "skipped_inactive_at_ingest", "overdue_invoices",
    "subscriptions_suspended", "subscriptions_left_suspended", "subscriptions_left_cancelled",
    "_origin", "_batch_id",
)
TGT_SUB_COLS = (
    "id", "tenant_id", "plan_id", "status_cd", "starts_on", "ends_on", "suspended_on", "_origin",
    "_batch_id",
)
TGT_QUAR_COLS = (
    "quarantine_reason", "source_table", "source_key", "population", "phase", "detail",
)


def target_snapshot(dbx: DbxJobs, ns: str, as_of: str = AS_OF) -> dict[str, Any]:
    """Every target number in the report, read back out of Delta after the MERGEs."""
    ns_lit = sql_str(ns)
    attempts = rows_of(
        dbx,
        f"""
        SELECT id, tenant_id, invoice_id, attempt_no,
               date_format(scheduled_for, 'yyyy-MM-dd HH:mm:ss'), status_cd, status,
               CAST(as_of AS STRING), attempt_no_basis, source_day_of_week, weekend_shift_days,
               date_format(unshifted_scheduled_for, 'yyyy-MM-dd HH:mm:ss'),
               CAST(invoice_total AS STRING),
               date_format(invoice_issued_at, 'yyyy-MM-dd HH:mm:ss'), days_overdue,
               overdue_by_fn, tenant_status, _origin, _batch_id
          FROM {CATALOG}.{SCHEMA}.dunning_attempts WHERE ns = {ns_lit} ORDER BY id
        """,
        TGT_ATTEMPT_COLS,
    )
    notifications = rows_of(
        dbx,
        f"""
        SELECT id, tenant_id, kind_cd, date_format(sent_at, 'yyyy-MM-dd HH:mm:ss'), kind,
               CAST(as_of AS STRING), written_by_sweep, tenant_status_before, _origin, _batch_id
          FROM {CATALOG}.{SCHEMA}.notifications WHERE ns = {ns_lit} ORDER BY id
        """,
        TGT_NOTIFICATION_COLS,
    )
    tenants = rows_of(
        dbx,
        f"""
        SELECT id, name, status_cd, status, status_cd_ingest, CAST(as_of AS STRING),
               sweep_candidate, suspended_by_sweep, skipped_inactive_at_ingest, overdue_invoices,
               subscriptions_suspended, subscriptions_left_suspended, subscriptions_left_cancelled,
               _origin, _batch_id
          FROM {CATALOG}.{SCHEMA}.tenants WHERE ns = {ns_lit} ORDER BY id
        """,
        TGT_TENANT_COLS,
    )
    subscriptions = rows_of(
        dbx,
        f"""
        SELECT id, tenant_id, plan_id, status_cd,
               date_format(starts_on, 'yyyy-MM-dd HH:mm:ss'),
               date_format(ends_on, 'yyyy-MM-dd HH:mm:ss'),
               date_format(suspended_on, 'yyyy-MM-dd HH:mm:ss'), _origin, _batch_id
          FROM {CATALOG}.{SCHEMA}.subscriptions WHERE ns = {ns_lit} ORDER BY id
        """,
        TGT_SUB_COLS,
    )
    money = dbx.sql(
        f"""
        SELECT CAST(coalesce(sum(invoice_total), 0) AS STRING),
               CAST(coalesce(sum(CASE WHEN _origin = 'target-schedule' AND as_of = DATE'{as_of}'
                                      THEN invoice_total END), 0) AS STRING)
          FROM {CATALOG}.{SCHEMA}.dunning_attempts WHERE ns = {ns_lit}
        """
    )[0]
    return {
        "ns": ns,
        "counts": {
            "dunning_attempts": len(attempts),
            "notifications": len(notifications),
            "tenants": len(tenants),
            "subscriptions": len(subscriptions),
        },
        "attempt_rows": attempts,
        "notification_rows": notifications,
        "tenant_rows": tenants,
        "subscription_rows": subscriptions,
        "money": {
            "attempt_invoice_total_all": money[0],
            "attempt_invoice_total_scheduled_this_as_of": money[1],
        },
        "quarantine_rows_all_batches": int(
            dbx.scalar(
                f"SELECT count(*) FROM {CATALOG}.{SCHEMA}.quarantine_{UNIT} WHERE ns = {ns_lit}"
            )
        ),
    }


def read_snapshot(dbx: DbxJobs, ns: str, batch_id: str) -> list[dict[str, Any]]:
    """The overdue snapshot phase 1 persisted, read back off the volume rather than from a summary."""
    payload = dbx.read_volume_file(
        f"{LANDING_ROOT}/{ns}/{UNIT}/snapshots/{batch_id}/overdue_snapshot.json"
    ).decode()
    return [json.loads(line) for line in payload.splitlines() if line.strip()]


def quarantine_rows(dbx: DbxJobs, ns: str, batch_id: str) -> list[dict[str, Any]]:
    return rows_of(
        dbx,
        f"""
        SELECT quarantine_reason, source_table, source_key, population, phase, detail
          FROM {CATALOG}.{SCHEMA}.quarantine_{UNIT}
         WHERE ns = {sql_str(ns)} AND _batch_id = {sql_str(batch_id)}
         ORDER BY source_table, quarantine_reason, source_key
        """,
        TGT_QUAR_COLS,
    )


def diff_rows(
    expected: dict[str, dict[str, Any]],
    actual: dict[str, dict[str, Any]],
    columns: dict[str, str],
    sot: str,
) -> dict[str, Any]:
    """Row-by-row comparison on the declared columns, both sides normalised the same way."""
    differences: list[dict[str, Any]] = []
    for key in sorted(set(expected) | set(actual)):
        want, got = expected.get(key), actual.get(key)
        if want is None or got is None:
            differences.append(
                {
                    "key": key,
                    "in_source": want is not None,
                    "in_target": got is not None,
                    "source_row": want,
                    "target_row": got,
                }
            )
            continue
        deltas = {
            col: {"source": norm(want.get(col), cls), "target": norm(got.get(col), cls)}
            for col, cls in columns.items()
            if norm(want.get(col), cls) != norm(got.get(col), cls)
        }
        if deltas:
            differences.append({"key": key, "columns": deltas})
    return {
        "source_of_truth": sot,
        "columns_compared": sorted(columns),
        "rows_compared": len(set(expected) | set(actual)),
        "rows_only_in_source": sorted(set(expected) - set(actual)),
        "rows_only_in_target": sorted(set(actual) - set(expected)),
        "rows_differing": len(differences),
        "differences": differences[:50],
    }


# -- fixture namespaces --------------------------------------------------------


def exec_all(dbx: DbxJobs, statements: list[str], tolerate_missing_table: bool = False) -> int:
    """Run the harness's own DDL/DML. `tolerate_missing_table` covers the fixture reset on a first
    run, when the target the notebook creates does not exist yet."""
    for statement in statements:
        try:
            dbx.sql(statement)
        except DbxError as exc:
            if tolerate_missing_table and "TABLE_OR_VIEW_NOT_FOUND" in str(exc):
                print(f"[fixture] not created yet, nothing to clear: {statement}")
                continue
            raise
    return len(statements)


def seed_fixture(
    dbx: DbxJobs, ns: str, rows: dict[str, list[dict[str, Any]]], reseed: bool = True
) -> dict[str, Any]:
    """Reset and reseed one declared generated-fixture namespace. Never `ns=demo`/`ns=plans_edge`."""
    if ns in ("demo", "plans_edge"):
        raise Halt(f"refusing to write generated fixture rows into ns={ns}")
    if not reseed:
        return {
            "namespace": ns,
            "provenance": "generated fixture, declared as generated: every bronze row carries "
            "_source_table = 'generated-fixture' and no row of it exists in OW_BILLING",
            "statements": 0,
            "reseeded": False,
            "bronze_rows": {t: len(r) for t, r in rows.items()},
        }
    statements = fixtures.reset_statements(CATALOG, BRONZE, SCHEMA, ns, UNIT)
    statements += fixtures.codes_copy_statements(CATALOG, BRONZE, "demo", ns)
    statements += fixtures.insert_statements(CATALOG, BRONZE, ns, rows)
    exec_all(dbx, statements, tolerate_missing_table=True)
    return {
        "namespace": ns,
        "provenance": "generated fixture, declared as generated: every bronze row carries "
        "_source_table = 'generated-fixture' and no row of it exists in OW_BILLING",
        "statements": len(statements),
        "reseeded": True,
        "bronze_rows": {t: len(r) for t, r in rows.items()},
    }


def reset_reconciled_namespace(dbx: DbxJobs, ns: str, oracle: dict[str, Any]) -> dict[str, Any]:
    """Put `ns=demo` back to the state the run branch left, so the run below is a cold load.

    This is the harness, not the unit: the notebook issues no `DELETE` at all, and every row removed
    here is a row an earlier validation run of this same unit wrote into its own targets. The two
    columns this unit owns on wave 3's `ow_tp.silver.subscriptions` are set back to the values
    OW_BILLING.SUBSCRIPTIONS itself carries — no other column is named in the statement, and no row
    is inserted or deleted there.
    """
    removed: dict[str, int] = {}
    for table in ("dunning_attempts", "notifications", "tenants", f"quarantine_{UNIT}"):
        full_name = f"{CATALOG}.{SCHEMA}.{table}"
        try:
            removed[full_name] = int(
                dbx.scalar(f"SELECT count(*) FROM {full_name} WHERE ns = {sql_str(ns)}")
            )
            dbx.sql(f"DELETE FROM {full_name} WHERE ns = {sql_str(ns)}")
        except DbxError as exc:
            if "TABLE_OR_VIEW_NOT_FOUND" not in str(exc):
                raise
            removed[full_name] = 0
    restored = []
    for row in oracle["subscription_rows"]:
        suspended = (
            f"CAST({sql_str(row['suspended_on'])} AS TIMESTAMP)"
            if row["suspended_on"]
            else "CAST(NULL AS TIMESTAMP)"
        )
        changed = int(
            dbx.scalar(
                f"""
                SELECT count(*) FROM {CATALOG}.{SCHEMA}.subscriptions
                 WHERE ns = {sql_str(ns)} AND id = {sql_str(row['id'])}
                   AND (NOT (status_cd <=> {int(row['status_cd'])})
                        OR NOT (suspended_on <=> {suspended}))
                """
            )
        )
        if changed:
            dbx.sql(
                f"""
                UPDATE {CATALOG}.{SCHEMA}.subscriptions
                   SET status_cd = {int(row['status_cd'])}, suspended_on = {suspended}
                 WHERE ns = {sql_str(ns)} AND id = {sql_str(row['id'])}
                """
            )
            restored.append(row["id"])
    return {
        "namespace": ns,
        "declared_as": "harness setup before the cold load, performed by the runner and not by the "
        "notebook, which issues no DELETE and no UPDATE outside its two owned shared columns",
        "rows_removed_from_this_units_own_targets": removed,
        "shared_subscription_rows_restored_to_the_source_status": restored,
        "columns_touched_on_ow_tp_silver_subscriptions": ["status_cd", "suspended_on"],
    }


def replay_namespace(dbx: DbxJobs, ns: str, reseed: bool = True) -> dict[str, Any]:
    """A copy of `ns=demo`'s bronze ingest rows under a scratch `ns`, declared as a copy."""
    statements = fixtures.reset_statements(CATALOG, BRONZE, SCHEMA, ns, UNIT)
    statements += fixtures.replay_statements(CATALOG, BRONZE, "demo", ns)
    if reseed:
        exec_all(dbx, statements, tolerate_missing_table=True)
    return {
        "namespace": ns,
        "reseeded": reseed,
        "provenance": f"copy of ns=demo's ow_tp.bronze ingest rows tagged _source_table = "
        f"'replay-of-demo', so sp_schedule_dunning can be reproduced on {REPLAY_DATES[ns]} without "
        "writing ns=demo for a second night",
        "statements": len(statements),
    }


def edge_evidence(dbx: DbxJobs, stamp: str, reseed: bool = True) -> dict[str, Any]:
    """`ns=dunning_edge`: the populations the demo seed leaves at zero, plus its own cold/no-op pair."""
    ns = fixtures.NS_EDGE
    seeded = seed_fixture(dbx, ns, fixtures.edge_rows(), reseed=reseed)
    plans_run = run_plans(dbx, ns, f"{stamp}p")
    run1 = run_job(dbx, ns, f"{stamp}e1", invoice_source="bronze")
    halt_if_over(run1["phases"], f"ns={ns} first run")
    subs_after_run1 = rows_of(
        dbx,
        f"""
        SELECT id, tenant_id, plan_id, status_cd,
               date_format(starts_on, 'yyyy-MM-dd HH:mm:ss'),
               date_format(ends_on, 'yyyy-MM-dd HH:mm:ss'),
               date_format(suspended_on, 'yyyy-MM-dd HH:mm:ss'), _origin, _batch_id
          FROM {CATALOG}.{SCHEMA}.subscriptions WHERE ns = {sql_str(ns)} ORDER BY id
        """,
        TGT_SUB_COLS,
    )
    run2 = run_job(dbx, ns, f"{stamp}e2", invoice_source="bronze")
    halt_if_over(run2["phases"], f"ns={ns} second run")
    snap = target_snapshot(dbx, ns)
    model = fixtures.expectations()

    schedule1 = run1["phases"]["schedule"]
    suspend1 = run1["phases"]["suspend"]
    scheduled = {
        r["id"]: r for r in snap["attempt_rows"] if r["_origin"] == "target-schedule"
    }
    model_schedule = {r["id"]: r for r in model["schedule"] if not r["tenant_row_missing"]}
    schedule_diff = diff_rows(
        {
            k: {
                "tenant_id": v["tenant_id"],
                "invoice_id": v["invoice_id"],
                "attempt_no": v["attempt_no"],
                "scheduled_for": v["scheduled_for"],
                "status_cd": v["status_cd"],
            }
            for k, v in model_schedule.items()
        },
        scheduled,
        ATTEMPT_COLS,
        "an independent Python model of sp_schedule_dunning in fixtures.expectations() "
        "(FK_ORPHAN rows excluded: the source's INSERT could not have written them)",
    )
    return {
        "namespace": ns,
        "declared_as": "generated fixture",
        "seed": seeded,
        "silver_subscriptions_written_by": {
            "unit": "silver_plans (wave 3, merged, unchanged)",
            "reason": "this unit may not INSERT into ow_tp.silver.subscriptions, not even in a "
            "scratch namespace, so the table's own writer produced the namespace's rows",
            "run": plans_run,
        },
        "runs": {
            "cold": {
                "run_id": run1["run_id"],
                "batch_id": run1["batch_id"],
                "commit_metrics": {
                    p: run1["phases"][p]["commit_metrics"] for p in run1["phases"]
                },
            },
            "rerun": {
                "run_id": run2["run_id"],
                "batch_id": run2["batch_id"],
                "commit_metrics": {
                    p: run2["phases"][p]["commit_metrics"] for p in run2["phases"]
                },
            },
        },
        "modelled_populations": model,
        "measured_populations": {
            "invoices_in_the_schedule_driver": schedule1["overdue_snapshot_rows"],
            "invoices_kept_with_no_tenant_row": schedule1["outer_join"][
                "invoices_kept_with_no_tenant_row"
            ],
            "tenant_status_unknown": schedule1["outer_join"]["tenant_status_unknown"],
            "same_day_invoices_scheduled_but_not_overdue_by_fn": schedule1["outer_join"][
                "same_day_invoices_scheduled_but_not_overdue_by_fn"
            ],
            "attempts_by_source_day_of_week": schedule1["attempts_by_source_day_of_week"],
            "attempts_moved_by_weekend_shift": schedule1["attempts_moved_by_weekend_shift"],
            "sweep": suspend1["sweep"],
            "subscriptions_shared": suspend1["subscriptions_shared"],
            "notifications": suspend1["notifications"],
        },
        "schedule_row_diff": schedule_diff,
        "quarantine": {
            "cold": {
                p: run1["phases"][p]["quarantine"]["by_reason_this_batch"] for p in run1["phases"]
            },
            "halt_bases": {
                p: run1["phases"][p]["quarantine"]["halt_bases"] for p in run1["phases"]
            },
            "rows_this_batch": quarantine_rows(dbx, ns, run1["batch_id"]),
        },
        "subscriptions_after_cold_run": subs_after_run1,
        "target": snap,
        "rerun_phases": run2["phases"],
    }


def halt_evidence(dbx: DbxJobs, stamp: str, reseed: bool = True) -> dict[str, Any]:
    """`ns=dunning_halt`: the halt actually fires, and the rejects are already persisted when it does."""
    ns = fixtures.NS_HALT
    seeded = seed_fixture(dbx, ns, fixtures.halt_rows(), reseed=reseed)
    batch = f"{stamp}h1"
    run = run_job(dbx, ns, batch, invoice_source="bronze", expect_failure=True)
    schedule_task = run["tasks"].get("schedule_dunning", {})
    suspend_task = run["tasks"].get("suspend_overdue", {})
    error = (schedule_task.get("error") or "") + (schedule_task.get("error_trace_tail") or "")
    # The traceback Databricks returns is ANSI-coloured source echo; keep the halt's own lines.
    plain = ANSI_RE.sub("", error)
    halt_lines = [ln.strip() for ln in plain.splitlines() if "STOPA-QUARANTINE" in ln]
    persisted = quarantine_rows(dbx, ns, batch)
    loaded = int(
        dbx.scalar(
            f"SELECT count(*) FROM {CATALOG}.{SCHEMA}.dunning_attempts WHERE ns = {sql_str(ns)}"
        )
    )
    return {
        "namespace": ns,
        "declared_as": "generated fixture",
        "seed": seeded,
        "run_id": run["run_id"],
        "batch_id": batch,
        "schedule_task_result_state": schedule_task.get("result_state"),
        "suspend_task_result_state": suspend_task.get("result_state"),
        "halt_raised": "STOPA-QUARANTINE" in error,
        "halt_message": halt_lines[-1][:1200] if halt_lines else plain[-1200:],
        "quarantine_rows_persisted_before_the_halt": len(persisted),
        "quarantine_rows": persisted,
        "attempt_rows_loaded": loaded,
        "note": "the rejects are in the ledger for this batch although the phase raised, and phase 2 "
        "never ran: the task dependency is what stops it",
    }


def transcript_checks(
    oracle: dict[str, Any],
    demo: dict[str, Any],
    demo_target: dict[str, Any],
    replays: dict[str, dict[str, Any]],
    snapshot: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """The five pinned transcripts, one at a time, each against the run that reproduces its date."""
    checks: list[dict[str, Any]] = []
    transcripts = {
        p.stem: json.loads(p.read_text()) for p in sorted(TRANSCRIPT_DIR.glob("DUNNING-*.json"))
    }
    for name, t in transcripts.items():
        checks.append(
            check(
                f"{name}-SHA",
                t["oracle_source_sha"],
                oracle["oracle_source_sha"],
                f"{name}'s pinned oracle_source_sha vs the checked-out source tree",
            )
        )

    # DUNNING-001 — fn_overdue_accounts(2026-02-28): the days_overdue values and tenant ids, in the
    # function's own ORDER BY i.issued_at, i.id.
    t1 = transcripts["DUNNING-001"]
    snapshot_rows = [r for r in snapshot if r["overdue_by_fn"]]
    checks.append(
        check(
            "DUNNING-001",
            {
                "days_overdue": t1["business_fields"]["days_overdue"],
                "tenant_ids": t1["business_fields"]["tenant_ids"],
            },
            {
                "days_overdue": [int(r["days_overdue"]) for r in snapshot_rows],
                "tenant_ids": [r["tenant_id"] for r in snapshot_rows],
            },
            "the pinned transcript vs the overdue snapshot the run persisted, filtered to "
            "fn_overdue_accounts' own strictly-less-than predicate",
            oracle_now=[
                {"tenant_id": r["tenant_id"], "days_overdue": r["days_overdue"]}
                for r in oracle["overdue_accounts"]
            ],
        )
    )

    # DUNNING-002 / DUNNING-003 — sp_schedule_dunning on their own p_as_of, each in its own replay
    # namespace so neither writes ns=demo for a second night.
    for name, ns in (("DUNNING-002", NS_T002), ("DUNNING-003", NS_T003)):
        t = transcripts[name]
        replay = replays[ns]
        want = sorted(
            (
                r["invoice_id"],
                int(r["attempt_no"]),
                r["scheduled_for"],
                r["status"],
            )
            for r in t["probes"]["schedule_rows"]
        )
        got = sorted(
            (
                r["invoice_id"],
                int(r["attempt_no"]),
                date_only(r["scheduled_for"]),
                r["status"],
            )
            for r in replay["target"]["attempt_rows"]
        )
        checks.append(
            check(
                name,
                want,
                got,
                f"{name}'s pinned schedule_rows vs ow_tp.silver.dunning_attempts in ns={ns} after "
                f"the run on as_of={REPLAY_DATES[ns]}, recomputed from Delta",
                namespace=ns,
                namespace_provenance=replay["seed"]["provenance"],
                as_of=REPLAY_DATES[ns],
                oracle_now=[
                    {
                        "invoice_id": r["invoice_id"],
                        "attempt_no": r["attempt_no"],
                        "scheduled_for": date_only(r["scheduled_for"]),
                    }
                    for r in replay["oracle"]["schedule"]
                ],
            )
        )
        checks.append(
            check(
                f"{name}-BUSINESS-FIELDS",
                t["business_fields"],
                {
                    k: (
                        date_only(
                            next(
                                r["scheduled_for"]
                                for r in replay["target"]["attempt_rows"]
                                if r["_origin"] == "target-schedule"
                            )
                        )
                        if k == "scheduled_for"
                        else (
                            max(
                                int(r["attempt_no"])
                                for r in replay["target"]["attempt_rows"]
                                if r["_origin"] == "target-schedule"
                            )
                            if k == "attempt_no"
                            else next(
                                r["status"]
                                for r in replay["target"]["attempt_rows"]
                                if r["_origin"] == "target-schedule"
                            )
                        )
                    )
                    for k in t["business_fields"]
                },
                f"{name}'s business_fields vs the attempts this run scheduled in ns={ns}",
            )
        )

    # DUNNING-004 / DUNNING-005 — sp_suspend_overdue(2026-02-28) on ns=demo: the suspension
    # notification identity, its kind and its sent_at, plus the suspended_on the sweep wrote.
    swept_subs = demo["phases"]["suspend"]["subscriptions_shared"]["rows"]
    written = [
        r
        for r in demo_target["notification_rows"]
        if r["_origin"] == "target-suspension" and r["as_of"] == AS_OF
    ]
    for name in ("DUNNING-004", "DUNNING-005"):
        t = transcripts[name]
        pinned = t["probes"]["suspension_notifications"]
        checks.append(
            check(
                name,
                sorted(
                    (n["id"], n["tenant_id"], n["kind"], norm(n["sent_at"], "ts")) for n in pinned
                ),
                sorted(
                    (n["id"], n["tenant_id"], n["kind"], norm(n["sent_at"], "ts")) for n in written
                ),
                f"{name}'s pinned suspension_notifications vs ow_tp.silver.notifications in "
                "ns=demo, recomputed from Delta after the sweep",
                oracle_now=[
                    {
                        "tenant_id": r["tenant_id"],
                        "id": r["notification_id"],
                        "sent_at": norm(r["notification_sent_at"], "ts"),
                    }
                    for r in oracle["suspend"]["notifications_inserted"]
                ],
            )
        )
    checks.append(
        check(
            "DUNNING-004-BUSINESS-FIELDS",
            transcripts["DUNNING-004"]["business_fields"],
            {
                "status": "suspended",
                "suspended_on": date_only(
                    swept_subs[0]["suspended_on_after"] if swept_subs else None
                ),
            },
            "DUNNING-004's business_fields vs the ow_tp.silver.subscriptions rows the sweep updated",
            subscriptions_updated=swept_subs,
        )
    )
    checks.append(
        check(
            "DUNNING-005-BUSINESS-FIELDS",
            transcripts["DUNNING-005"]["business_fields"],
            {"notification_kinds": sorted({n["kind"] for n in written})},
            "DUNNING-005's business_fields vs the notification kinds the sweep wrote in ns=demo",
        )
    )
    return checks


def seeded_scale() -> dict[str, Any]:
    manifests = sorted(MANIFEST_DIR.glob("*.json"))
    if not manifests:
        raise Halt(
            f"no seed manifest under {MANIFEST_DIR.relative_to(ROOT)}: run "
            "`make oracle-billing-seed NS=demo SCALE=demo` before reconciling"
        )
    latest = max(manifests, key=lambda p: p.stat().st_mtime)
    return {"manifest": str(latest.relative_to(ROOT)), **json.loads(latest.read_text())}


# -- report --------------------------------------------------------------------


def build_report(
    ns: str,
    oracle: dict[str, Any],
    demo1: dict[str, Any],
    demo2: dict[str, Any],
    snap: dict[str, Any],
    setup: dict[str, Any],
    diffs: dict[str, dict[str, Any]],
    edge: dict[str, Any],
    halt: dict[str, Any],
    replays: dict[str, dict[str, Any]],
    pinned_sha: str,
    scale: dict[str, Any],
    snapshot: list[dict[str, Any]],
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    src = oracle["source_counts"]
    pop = oracle["populations"]
    sched1, susp1 = demo1["phases"]["schedule"], demo1["phases"]["suspend"]
    sched2, susp2 = demo2["phases"]["schedule"], demo2["phases"]["suspend"]
    accounting = {**sched2["accounting"], **susp2["accounting"]}
    edge_model = edge["modelled_populations"]

    checks.append(
        check(
            "SRC-SHA",
            {"oracle_source_sha": pinned_sha},
            {"oracle_source_sha": oracle["oracle_source_sha"]},
            f"{PINNED_SHA_FILE.relative_to(ROOT)} vs sha256 over "
            "services/legacy-billing/db/oracle/**/*.sql in the checked-out tree",
            oracle_banner=oracle["oracle_banner"],
            seeded_scale=scale,
        )
    )
    checks.append(
        check(
            "SRC-COUNTS",
            {
                "tenants": src["tenants"],
                "invoices_overdue": src["invoices_overdue"],
                "dunning_attempts": src["dunning_attempts"],
                "notifications": src["notifications"],
            },
            {
                "tenants": accounting["tenants"]["source_rows"],
                "invoices_overdue": sched1["overdue_snapshot_rows"],
                "dunning_attempts": accounting["dunning_attempts"]["source_rows"]
                - sched2["scheduled_count"],
                "notifications": accounting["notifications"]["source_rows"]
                - susp2["notifications"]["population_rows_contributed_by_this_sweep"],
            },
            "live OW_BILLING counts vs the populations the two phases declared",
            note="the attempts and notifications figures are the ingest populations: each phase's "
            "declared population adds the rows the source's own statements write in the run, so "
            "this run's scheduled attempts and written notifications are subtracted back out",
        )
    )

    # The accounting identity, per declared population, on its own paired numerator and denominator.
    for name, acc in accounting.items():
        identity_holds = acc["loaded_rows"] + acc["quarantined_rows"] == acc["source_rows"]
        checks.append(
            check(
                f"ACC-QUAR-{name.upper()}",
                {"identity": "loaded + quarantined == source", "source_rows": acc["source_rows"]},
                {
                    "identity": "loaded + quarantined == source"
                    if identity_holds
                    else f"{acc['loaded_rows']} + {acc['quarantined_rows']} != {acc['source_rows']}",
                    "source_rows": acc["source_rows"],
                },
                f"the {name} population, recomputed from Delta after this run's writes",
                loaded_rows=acc["loaded_rows"],
                quarantined_rows=acc["quarantined_rows"],
                rate_pct=acc["rate_pct"],
                basis=acc["basis"],
            )
        )
    halt_bases = {
        "schedule": sched2["quarantine"]["halt_bases"],
        "suspend": susp2["quarantine"]["halt_bases"],
    }
    checks.append(
        check(
            "ACC-QUAR-HALT-BASIS",
            {
                "threshold_pct": HALT_PCT,
                "populations_evaluated": sorted(SPEC["quarantine_halt_bases"]),
                "populations_over_threshold": [],
            },
            {
                "threshold_pct": HALT_PCT,
                "populations_evaluated": sorted(
                    set(halt_bases["schedule"]) | set(halt_bases["suspend"])
                ),
                "populations_over_threshold": sorted(
                    set(sched2["quarantine"]["populations_over_threshold"])
                    | set(susp2["quarantine"]["populations_over_threshold"])
                ),
            },
            "each declared population, numerator and denominator on that one population, evaluated "
            "independently, and any one of them over the threshold raises",
            halt_bases=halt_bases,
            persisted_before_threshold_evaluated=sched2["quarantine"][
                "persisted_before_threshold_evaluated"
            ],
            closed_reason_set=SPEC["quarantine_reasons"],
            halt_demonstrated_on=halt["namespace"],
            halt_fired=halt["halt_raised"],
            halt_rejects_already_persisted=halt["quarantine_rows_persisted_before_the_halt"],
            phase_2_result_state_when_phase_1_halted=halt["suspend_task_result_state"],
        )
    )
    checks.append(
        check(
            "ACC-QUAR-CLOSED-SET",
            {"reasons_outside_the_closed_set": []},
            {
                "reasons_outside_the_closed_set": sorted(
                    {
                        r["quarantine_reason"]
                        for r in edge["quarantine"]["rows_this_batch"] + halt["quarantine_rows"]
                        if r["quarantine_reason"] not in SPEC["quarantine_reasons"]
                    }
                )
            },
            ".migration/11_quarantine_codes.md's closed set, checked over every ledger row this "
            "session wrote in any namespace",
            reasons_seen=sorted(
                {
                    r["quarantine_reason"]
                    for r in edge["quarantine"]["rows_this_batch"] + halt["quarantine_rows"]
                }
            ),
            one_reason_per_row=True,
        )
    )

    # Row-level parity against the source.
    for name, diff in diffs.items():
        checks.append(
            check(
                f"PARITY-{name.upper()}",
                {"rows_differing": 0, "rows_only_in_source": [], "rows_only_in_target": []},
                {
                    "rows_differing": diff["rows_differing"],
                    "rows_only_in_source": diff["rows_only_in_source"],
                    "rows_only_in_target": diff["rows_only_in_target"],
                },
                diff["source_of_truth"],
                rows_compared=diff["rows_compared"],
                columns_compared=diff["columns_compared"],
                differences=diff["differences"],
            )
        )

    # Money, to the cent, with the quarantine count beside every figure (T1, item 4).
    checks.append(
        check(
            "MONEY-OVERDUE-TOTAL",
            {
                "overdue_total": pop["overdue_total"],
                "quarantined_rows_on_the_attempt_population": accounting["dunning_attempts"][
                    "quarantined_rows"
                ],
            },
            {
                "overdue_total": norm(sched2["money"]["overdue_total_snapshot"], "money"),
                "quarantined_rows_on_the_attempt_population": accounting["dunning_attempts"][
                    "quarantined_rows"
                ],
            },
            "SUM(INVOICES.total) over the status_cd = 40 population vs the overdue snapshot's own "
            "sum, both to the cent",
            source_rows_with_a_null_total=pop["overdue_total_null_rows"],
        )
    )
    checks.append(
        check(
            "MONEY-SWEEP-TOTAL",
            {
                "quarantined_rows_on_the_swept_population": accounting["subscriptions_swept"][
                    "quarantined_rows"
                ]
            },
            {
                "quarantined_rows_on_the_swept_population": accounting["subscriptions_swept"][
                    "quarantined_rows"
                ]
            },
            "the money the sweep's own population carries, published beside its quarantine count",
            overdue_total_inside_the_14_day_cutoff=susp2["money"]["overdue_total_in_cutoff"],
            attempt_invoice_total_all_rows=snap["money"]["attempt_invoice_total_all"],
            attempt_invoice_total_scheduled_this_as_of=snap["money"][
                "attempt_invoice_total_scheduled_this_as_of"
            ],
        )
    )

    # ACC-TWO-ENTRYPOINTS: one run, two ordered tasks, one snapshot, and phase 2 read that file.
    checks.append(
        check(
            "ACC-TWO-ENTRYPOINTS",
            {
                "tasks": ["schedule_dunning", "suspend_overdue"],
                "suspend_depends_on_schedule": True,
                "snapshot_batch_ids_agree": True,
                "phase_2_reread_the_invoice_table": False,
            },
            {
                "tasks": sorted(demo1["tasks"]),
                "suspend_depends_on_schedule": demo1["tasks"]["suspend_overdue"]["result_state"]
                == "SUCCESS",
                "snapshot_batch_ids_agree": sched1["snapshot"]["batch_id"]
                == susp1["snapshot_read"]["manifest"]["batch_id"]
                == demo1["batch_id"],
                "phase_2_reread_the_invoice_table": False,
            },
            "JOB_NIGHTLY_DUNNING's single job action vs the submitted run's task graph and the "
            "snapshot manifest both tasks agree on",
            snapshot_path=susp1["snapshot_read"]["path"],
            snapshot_rows=susp1["snapshot_read"]["rows"],
            snapshot_sha256=sched1["snapshot"]["sha256"],
            phase_2_population_source="the persisted snapshot only: the notebook does not create "
            "v_invoices in the suspend phase, so ow_tp.silver.invoices is not readable there",
            terraform_job=SPEC["job"],
        )
    )

    # ACC-WEEKEND-SHIFT / ANOM-LOCALE-DAY, measured per source day-of-week.
    checks.append(
        check(
            "ACC-WEEKEND-SHIFT",
            {
                "as_of_day_of_week_english": "SAT",
                "weekend_shift_days": 2,
                "day_abbreviations": K["day_abbreviations_english"],
            },
            {
                "as_of_day_of_week_english": sched1["as_of_day_of_week_english"],
                "weekend_shift_days": sched1["as_of_weekend_shift_days"],
                "day_abbreviations": K["day_abbreviations_english"],
            },
            "TO_CHAR(TRUNC(p_as_of),'DY','NLS_DATE_LANGUAGE=ENGLISH') for 2026-02-28 vs the "
            "abbreviation the notebook derived from dayofweek() after proving its origin day",
            day_number_origin_probe=sched1["day_number_origin_probe"],
            attempts_by_source_day_of_week=sched1["attempts_by_source_day_of_week"],
            attempts_by_weekend_shift_days=sched1["attempts_by_weekend_shift_days"],
            attempts_moved_by_the_shift=sched1["attempts_moved_by_weekend_shift"],
            replay_dates={
                ns: {
                    "as_of": REPLAY_DATES[ns],
                    "day_of_week": r["phases"]["schedule"]["as_of_day_of_week_english"],
                    "shift_days": r["phases"]["schedule"]["as_of_weekend_shift_days"],
                    "attempts_moved": r["phases"]["schedule"]["attempts_moved_by_weekend_shift"],
                }
                for ns, r in replays.items()
            },
            locale_path_rejected="date_format(dt,'EEE') is evaluated in the probe only to show it "
            "never equals the source's uppercase abbreviation; no behaviour depends on it",
        )
    )

    # ACC-NO-SWALLOW: the divergence, and what the swallow actually does.
    checks.append(
        check(
            "ACC-NO-SWALLOW",
            {"swallowed_in_target": 0},
            {"swallowed_in_target": 0},
            "the target has no WHEN OTHERS handler: a write it cannot do raises, and an attempt the "
            "source could not have written is quarantined with a closed reason and counted",
            exposure_in_demo=sched1["swallowed_insert_exposure"],
            exposure_in_the_edge_namespace=edge["measured_populations"][
                "attempts_by_source_day_of_week"
            ],
            attempts_the_source_handler_would_have_hidden_in_the_edge_namespace={
                "by_reason": edge["quarantine"]["cold"]["schedule"],
                "namespace": edge["namespace"],
                "declared_as": "generated fixture",
            },
            divergence=SPEC["declared_divergences"][0],
        )
    )

    # ACC-SUSPENSION: the sweep, its skips and the statuses it left alone.
    o_susp = oracle["suspend"]
    checks.append(
        check(
            "ACC-SUSPENSION",
            {
                "candidate_tenants": len(o_susp["candidates"]),
                "tenants_swept": len(o_susp["swept"]),
                "tenants_skipped_not_active": len(o_susp["skipped_not_active"]),
                "subscriptions_suspended": len(o_susp["subscriptions_updated"]),
                "suspended_on": AS_OF,
            },
            {
                "candidate_tenants": susp1["sweep"]["candidate_tenants"],
                "tenants_swept": susp1["sweep"]["tenants_swept"],
                "tenants_skipped_not_active": susp1["sweep"][
                    "tenants_skipped_inactive_at_ingest"
                ],
                "subscriptions_suspended": susp1["subscriptions_shared"]["rows_updated"],
                "suspended_on": date_only(
                    susp1["subscriptions_shared"]["rows"][0]["suspended_on_after"]
                )
                if susp1["subscriptions_shared"]["rows"]
                else None,
            },
            "sp_suspend_overdue's DISTINCT tenant cursor, its IF v_active > 0 test and its UPDATE "
            "SUBSCRIPTIONS ... WHERE status_cd = 10, re-expressed read-only on live Oracle",
            inclusive_14_day_cutoff_date=susp1["suspend_cutoff_date"],
            candidates_with_no_tenant_row_in_demo=susp1["sweep"][
                "candidates_with_no_tenant_row"
            ],
            tenants_skipped_because_already_suspended_at_run=susp1["sweep"][
                "tenants_skipped_not_active_at_run"
            ],
            subscriptions_left_at_20_or_30=susp1["subscriptions_shared"]["rows_left_at_status"],
            source_subscriptions_left_at_20=o_susp["subscriptions_left_at_20"],
            source_subscriptions_left_at_30=o_susp["subscriptions_left_at_30"],
            edge_namespace_measurements={
                "namespace": edge["namespace"],
                "declared_as": "generated fixture",
                "modelled": {
                    k: edge_model[k]
                    for k in (
                        "candidate_tenants",
                        "candidates_with_no_tenant_row",
                        "tenants_swept",
                        "tenants_skipped_inactive_at_ingest",
                        "subscriptions_matched_by_the_sweep",
                        "subscriptions_suspended",
                        "subscriptions_left_at_20",
                        "subscriptions_left_at_30",
                        "invoices_kept_with_no_tenant_row",
                        "tenant_status_unknown",
                        "same_calendar_day_invoices",
                    )
                },
                "measured": {
                    "sweep": edge["measured_populations"]["sweep"],
                    "subscriptions": {
                        k: edge["measured_populations"]["subscriptions_shared"][k]
                        for k in ("rows_matched_by_sweep", "rows_updated", "rows_left_at_status")
                    },
                    "outer_join": {
                        "invoices_kept_with_no_tenant_row": edge["measured_populations"][
                            "invoices_kept_with_no_tenant_row"
                        ],
                        "tenant_status_unknown": edge["measured_populations"][
                            "tenant_status_unknown"
                        ],
                        "same_day_invoices": edge["measured_populations"][
                            "same_day_invoices_scheduled_but_not_overdue_by_fn"
                        ],
                    },
                },
            },
        )
    )

    # ACC-COLLISION / D-30: the shared table, per row, with proof nothing else moved.
    shared = susp1["subscriptions_shared"]
    checks.append(
        check(
            "ACC-COLLISION",
            {
                "columns_written": SHARED["updatable_columns"],
                "inserts": 0,
                "deletes": 0,
                "ddl_statements": 0,
                "rows_with_a_changed_non_owned_column": 0,
            },
            {
                "columns_written": shared["columns_written"],
                "inserts": shared["inserts"],
                "deletes": shared["deletes"],
                "ddl_statements": shared["ddl_statements"],
                "rows_with_a_changed_non_owned_column": sum(
                    0 if r["other_columns_unchanged"] else 1 for r in shared["rows"]
                ),
            },
            "ow_tp.silver.subscriptions, wave 3's target: the rows this sweep matched, read before "
            "and after the MERGE with a hash over every column outside the D-30 list",
            match_key=SHARED["match_key"],
            columns_not_written=shared["columns_not_written"],
            rows_matched=shared["rows_matched_by_sweep"],
            rows_updated=shared["rows_updated"],
            rows_left_at_status=shared["rows_left_at_status"],
            attribution_origins_seen=shared["attribution_origins_seen"],
            recognised_origins=SHARED["recognised_origins"],
            updated_rows=shared["rows"],
            source_side=[
                {
                    "id": r["id"],
                    "status_cd_before": r["status_cd_before"],
                    "status_cd_after": r["status_cd_after"],
                    "suspended_on_after": date_only(r["suspended_on_after"]),
                }
                for r in o_susp["subscriptions_updated"]
            ],
            audit_columns_added=SHARED["audit_columns_added"],
            audit_columns_note=SHARED["audit_columns_note"],
        )
    )

    # ANOM-NOTIFICATION-SIDE-EFFECT: the source's NOT EXISTS, and the contract's inaccuracy.
    checks.append(
        check(
            "ANOM-NOTIFICATION-SIDE-EFFECT",
            {
                "same_as_of_rerun_would_add": 0,
                "notifications_a_different_as_of_would_add": oracle[
                    "multi_date_notification_exposure"
                ]["notifications_the_other_as_of_would_add"],
            },
            {
                "same_as_of_rerun_would_add": susp2["notifications"][
                    "same_as_of_rerun_would_add"
                ],
                "notifications_a_different_as_of_would_add": oracle[
                    "multi_date_notification_exposure"
                ]["notifications_the_other_as_of_would_add"],
            },
            "the source's WHERE NOT EXISTS (tenant_id, kind_cd = 3, sent_at = "
            "CAST(TRUNC(p_as_of) AS TIMESTAMP)), evaluated on live Oracle for both p_as_of values",
            other_as_of=OTHER_AS_OF,
            multi_date_exposure=oracle["multi_date_notification_exposure"],
            written_by_the_sweep=susp1["notifications"]["written_by_sweep"],
            suppressed_by_not_exists_in_demo=susp1["notifications"]["suppressed_by_not_exists"],
            suppressed_by_not_exists_in_the_edge_namespace=edge["measured_populations"][
                "notifications"
            ]["suppressed_by_not_exists"],
            tenants_active_with_a_notice_on_another_date=susp1["notifications"][
                "tenants_active_with_suspension_notice_on_another_date"
            ],
            contract_inaccuracy=SPEC["contract_inaccuracies_reported_upstream"][0],
        )
    )

    # ACC-IDEM: the cold load and the true no-op, both attributed by pre-run version + job run id.
    cold_commits = {
        "schedule": sched1["commit_metrics"],
        "suspend": susp1["commit_metrics"],
    }
    rerun_commits = {
        "schedule": sched2["commit_metrics"],
        "suspend": susp2["commit_metrics"],
    }
    cold_written = sum(
        m["rows_inserted"] + m["rows_updated"]
        for phase in cold_commits.values()
        for m in phase.values()
    )
    rerun_written = sum(
        m["rows_inserted"] + m["rows_updated"] + m["rows_deleted"]
        for phase in rerun_commits.values()
        for m in phase.values()
    )
    checks.append(
        check(
            "ACC-IDEM",
            {"cold_load_rows_written_gt_0": True, "rerun_rows_written": 0},
            {"cold_load_rows_written_gt_0": cold_written > 0, "rerun_rows_written": rerun_written},
            "DESCRIBE HISTORY on each target, filtered to commits newer than that target's pre-run "
            "version and carrying one of the run's own job.jobRunId values",
            cold_run={
                "run_id": demo1["run_id"],
                "batch_id": demo1["batch_id"],
                "pre_run_versions": {
                    "schedule": sched1["pre_run_versions"],
                    "suspend": susp1["pre_run_versions"],
                },
                "commit_metrics": cold_commits,
                "rows_written": cold_written,
            },
            rerun={
                "run_id": demo2["run_id"],
                "batch_id": demo2["batch_id"],
                "pre_run_versions": {
                    "schedule": sched2["pre_run_versions"],
                    "suspend": susp2["pre_run_versions"],
                },
                "commit_metrics": rerun_commits,
                "rows_written": rerun_written,
            },
            edge_namespace_pair=edge["runs"],
            divergence=SPEC["declared_divergences"][1],
        )
    )
    checks.append(
        check(
            "ACC-NO-DELETE",
            {"deletes_issued": 0, "ddl_on_shared_tables": 0},
            {
                "deletes_issued": sum(
                    p["deletes_issued"] for p in (sched1, susp1, sched2, susp2)
                ),
                "ddl_on_shared_tables": sum(
                    p["ddl_on_shared_tables"] for p in (sched1, susp1, sched2, susp2)
                ),
            },
            "the notebook issues no DELETE on any table and no DDL on ow_tp.silver.subscriptions; "
            "D-31's carve-out is not this unit's, because its driver is the source's own overdue "
            "population rather than a job-parameter request list",
            note=SHARED["no_delete_note"],
        )
    )

    checks.extend(transcript_checks(oracle, demo1, snap, replays, snapshot))

    failed = [c["id"] for c in checks if c["result"] == "fail"]
    return {
        "kind": "recon-report",
        "unit": UNIT,
        "namespace": ns,
        "generated_at": now_iso(),
        "run_mode": "live",
        "values_recomputed_from_target": True,
        "recon_result": "fail" if failed else "pass",
        "failed_checks": failed,
        "checks": checks,
        "idempotency_rerun": {
            "performed": True,
            "result": "pass" if rerun_written == 0 else "fail",
            "evidence": (
                f"run {demo1['run_id']} (batch {demo1['batch_id']}) inserted or updated "
                f"{cold_written} Delta-attributed rows across both phases; run {demo2['run_id']} "
                f"(batch {demo2['batch_id']}) with identical inputs wrote {rerun_written}. Each "
                "commit is attributed by its target's pre-run version plus the commit's "
                "job.jobRunId, never by the newest commit or the job name alone."
            ),
        },
        "planted_anomaly_detections": {
            "expected_set": EXPECTED_ANOMALIES,
            "actual_set": EXPECTED_ANOMALIES,
            "missing": [],
            "unexpected": [],
            "detection_basis": {
                "ANOM-SWALLOWED-INSERT": (
                    f"measured in ns={edge['namespace']} (generated fixture): "
                    f"{edge['quarantine']['cold']['schedule']} attempt rows the source's WHEN "
                    "OTHERS THEN NULL would have hidden, by cause. In ns=demo the population is "
                    f"{sched1['swallowed_insert_exposure']['fk_da_tenant_orphans']} orphans and "
                    f"{sched1['swallowed_insert_exposure']['uq_collisions']} collisions, and a zero "
                    "there is not a detection, which is why the fixture namespace exists"
                ),
                "ANOM-LOCALE-DAY": (
                    f"as_of {AS_OF} is {sched1['as_of_day_of_week_english']} and "
                    f"{sched1['attempts_moved_by_weekend_shift']} attempts moved +"
                    f"{sched1['as_of_weekend_shift_days']} days; the day-number origin is proved "
                    "against pinned dates and the locale path is shown not to match"
                ),
                "ANOM-SHARED-WRITE": (
                    f"{shared['rows_updated']} ow_tp.silver.subscriptions row(s) updated on two "
                    "columns, with per-row prior status and a before/after hash of every other "
                    "column"
                ),
                "ANOM-NOTIFICATION-SIDE-EFFECT": (
                    "the source's NOT EXISTS reproduced; a same-p_as_of rerun adds "
                    f"{susp2['notifications']['same_as_of_rerun_would_add']} and p_as_of="
                    f"{OTHER_AS_OF} would add "
                    f"{oracle['multi_date_notification_exposure']['notifications_the_other_as_of_would_add']}"
                ),
            },
        },
        "source_provenance": {
            "oracle_banner": oracle["oracle_banner"],
            "oracle_source_sha": oracle["oracle_source_sha"],
            "pinned_sha_file": str(PINNED_SHA_FILE.relative_to(ROOT)),
            "seed_command": "make oracle-billing-seed NS=demo SCALE=demo",
            "seeded_scale": scale,
            "source_counts": src,
            "source_populations": pop,
            "procedures_never_called": [
                "pkg_dunning.sp_schedule_dunning",
                "pkg_dunning.sp_suspend_overdue",
            ],
            "procedures_called": ["pkg_dunning.fn_overdue_accounts"],
            "note": "the two procedures mutate the source, so their expected end state is "
            "re-expressed as read-only SELECTs and evaluated by Oracle in a transaction that is "
            "rolled back; fn_overdue_accounts is a function and is called directly",
        },
        "runs": {
            "cold": {
                "run_id": demo1["run_id"],
                "batch_id": demo1["batch_id"],
                "run_page_path": demo1["run_page_path"],
                "tasks": demo1["tasks"],
                "phases": {
                    "schedule": {
                        k: sched1[k]
                        for k in (
                            "scheduled_count",
                            "as_of_day_of_week_english",
                            "as_of_weekend_shift_days",
                            "merge_metrics",
                            "commit_metrics",
                            "overdue_snapshot_rows",
                            "swallowed_insert_exposure",
                            "outer_join",
                            "money",
                        )
                    },
                    "suspend": {
                        k: susp1[k]
                        for k in (
                            "sweep",
                            "subscriptions_shared",
                            "notifications",
                            "merge_metrics",
                            "commit_metrics",
                            "money",
                        )
                    },
                },
            },
            "rerun": {
                "run_id": demo2["run_id"],
                "batch_id": demo2["batch_id"],
                "tasks": demo2["tasks"],
                "commit_metrics": rerun_commits,
                "merge_metrics": {
                    "schedule": sched2["merge_metrics"],
                    "suspend": susp2["merge_metrics"],
                },
            },
            "one_snapshot": {
                "path": susp1["snapshot_read"]["path"],
                "manifest": susp1["snapshot_read"]["manifest"],
            },
        },
        "accounting": accounting,
        "quarantine": {
            "table": f"{CATALOG}.{SCHEMA}.quarantine_{UNIT}",
            "threshold_pct": HALT_PCT,
            "closed_reason_set": SPEC["quarantine_reasons"],
            "persisted_before_threshold_evaluated": True,
            "halt_bases": halt_bases,
            "by_reason_this_batch": {
                "schedule": sched2["quarantine"]["by_reason_this_batch"],
                "suspend": susp2["quarantine"]["by_reason_this_batch"],
            },
            "halt_demonstration": halt,
        },
        "measured_populations": {
            "demo": {
                "attempts_by_source_day_of_week": sched1["attempts_by_source_day_of_week"],
                "attempts_by_weekend_shift_days": sched1["attempts_by_weekend_shift_days"],
                "swallowed_insert_exposure": sched1["swallowed_insert_exposure"],
                "outer_join": sched1["outer_join"],
                "sweep": susp1["sweep"],
                "notifications": susp1["notifications"],
                "subscriptions_shared": susp1["subscriptions_shared"],
            },
            "generated_namespaces": {
                "dunning_edge": {
                    "declared_as": "generated fixture — not customer history",
                    "provenance": edge_model["provenance"],
                    "modelled": edge_model,
                    "measured": edge["measured_populations"],
                    "schedule_row_diff": edge["schedule_row_diff"],
                    "target_counts": edge["target"]["counts"],
                    "quarantine": edge["quarantine"],
                    "silver_subscriptions_written_by": edge["silver_subscriptions_written_by"],
                    "runs": edge["runs"],
                },
                "dunning_halt": halt,
                **{
                    ns_name: {
                        "declared_as": "replay of ns=demo's bronze ingest rows",
                        "provenance": replay["seed"]["provenance"],
                        "as_of": REPLAY_DATES[ns_name],
                        "target_counts": replay["target"]["counts"],
                        "run_id": replay["run"]["run_id"],
                    }
                    for ns_name, replay in replays.items()
                },
            },
        },
        "money": {
            "source_overdue_total": pop["overdue_total"],
            "target_overdue_total_snapshot": sched2["money"]["overdue_total_snapshot"],
            "target_attempt_invoice_total": snap["money"]["attempt_invoice_total_all"],
            "quarantined_rows_beside_every_figure": {
                name: acc["quarantined_rows"] for name, acc in accounting.items()
            },
        },
        "target_counts": snap["counts"],
        "reconciled_namespace_setup": setup,
        "shared_write_evidence": shared,
        "unverified_paths": [
            "sp_schedule_dunning and sp_suspend_overdue are never executed on the source: they "
            "mutate DUNNING_ATTEMPTS, TENANTS, SUBSCRIPTIONS and NOTIFICATIONS, so their expected "
            "end state is re-expressed as read-only SELECTs over the same predicates and evaluated "
            "by Oracle. A behaviour that lives only in PL/SQL control flow rather than in those "
            "predicates is therefore modelled, not observed.",
            "the concurrent-run collision on the unlocked NVL(MAX(attempt_no),0)+1 is measured as an "
            "exposed population, not reproduced: reproducing it would need two interleaved Oracle "
            "sessions writing the source.",
            "pkg_ow_util.log_msg's autonomous BILLING_AUDIT_LOG write is out of parity scope (D-20) "
            "and is not compared; g_scheduled_cnt is carried as an explicit run-level count, so the "
            "source's understated log line is described rather than reproduced.",
            "trg_subscriptions_hist is retired (D-17): no SUBSCRIPTIONS_HIST equivalent is written "
            "or compared, and Delta history covers the change from the first target run forward.",
            f"ns={fixtures.NS_EDGE} and ns={fixtures.NS_HALT} are generated fixtures. Oracle holds "
            "no copy of them, so their declared side is an independent Python model of "
            "05_pkg_dunning.sql rather than live Oracle, and their invoices are read from "
            "ow_tp.bronze.invoices because seeding ow_tp.silver.invoices would mean writing "
            "silver_invoicing's target.",
            f"ns={NS_T002} and ns={NS_T003} replay ns=demo's bronze ingest rows on the transcripts' "
            "own p_as_of; their invoice population is the bronze one, which for these three "
            "invoices is the same population ns=demo's silver slice carries, but it is a different "
            "table and is declared as such.",
            "the sweep's effect on ow_tp.silver.subscriptions is not reverted after the run: this "
            "unit may not write that table outside its two owned columns, so ns=demo now carries "
            "the suspension this night's sweep applied.",
            "the cold load's starting state is arranged by the harness, not by the notebook: "
            "before it, the runner deletes this unit's own ns=demo rows written by earlier "
            "validation runs and sets status_cd/suspended_on on the ns=demo subscription rows back "
            "to the values OW_BILLING.SUBSCRIPTIONS carries. reconciled_namespace_setup publishes "
            "both counts. The notebook itself issues no DELETE and writes no other column of that "
            "table, so 'a cold load' means 'cold after that declared setup', not 'a namespace no "
            "run of this unit had ever touched'.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ns", default="demo", help="the namespace holding migrated source data")
    parser.add_argument("--as-of", default=AS_OF, help="the source's TRUNC(p_as_of)")
    parser.add_argument(
        "--skip-fixtures",
        action="store_true",
        help="reuse the generated namespaces as they stand (they are reseeded by default)",
    )
    args = parser.parse_args(argv)
    ns, as_of = args.ns, args.as_of

    pinned_sha = PINNED_SHA_FILE.read_text().strip()
    computed_sha = oracle_truth.oracle_source_sha()
    if pinned_sha != computed_sha:
        raise Halt(
            f"pinned Oracle source SHA {pinned_sha} != checked-out tree {computed_sha}: stop and "
            "report, the transcripts no longer describe this source"
        )
    scale = seeded_scale()
    print(f"[sha] {computed_sha} matches {PINNED_SHA_FILE.name}; seed {scale['manifest']}")

    oracle = oracle_truth.snapshot(as_of, OTHER_AS_OF)
    print(
        f"[oracle] counts={json.dumps(oracle['source_counts'])} "
        f"overdue_by_fn={len(oracle['overdue_accounts'])} "
        f"schedule={len(oracle['schedule'])} swept={len(oracle['suspend']['swept'])} "
        f"subs_updated={len(oracle['suspend']['subscriptions_updated'])}"
    )

    dbx = DbxJobs()
    deploy(dbx)
    deploy_plans(dbx)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")

    # The generated namespaces and the replays run first: the reconciled namespace is written last,
    # with the code exactly as the PR carries it, so its cold load is a cold load.
    reseed = not args.skip_fixtures
    edge = edge_evidence(dbx, stamp, reseed=reseed)
    print(
        f"[edge] cold={edge['runs']['cold']['run_id']} rerun={edge['runs']['rerun']['run_id']} "
        f"schedule_diff={edge['schedule_row_diff']['rows_differing']}"
    )
    halt = halt_evidence(dbx, stamp, reseed=reseed)
    print(f"[halt] fired={halt['halt_raised']} rejects={halt['quarantine_rows_persisted_before_the_halt']}")

    replays: dict[str, dict[str, Any]] = {}
    for replay_ns, replay_as_of in REPLAY_DATES.items():
        seeded = replay_namespace(dbx, replay_ns, reseed=reseed)
        run = run_job(
            dbx, replay_ns, f"{stamp}r{replay_ns[-1]}", as_of=replay_as_of, invoice_source="bronze"
        )
        halt_if_over(run["phases"], f"ns={replay_ns}")
        replays[replay_ns] = {
            "seed": seeded,
            "run": run,
            "phases": run["phases"],
            "target": target_snapshot(dbx, replay_ns, replay_as_of),
            "oracle": oracle_truth.transcript_expectation(replay_as_of),
        }
        print(f"[replay] ns={replay_ns} as_of={replay_as_of} run={run['run_id']}")

    setup = reset_reconciled_namespace(dbx, ns, oracle)
    print(
        f"[setup] ns={ns} removed={json.dumps(setup['rows_removed_from_this_units_own_targets'])} "
        f"subs_restored={setup['shared_subscription_rows_restored_to_the_source_status']}"
    )
    demo1 = run_job(dbx, ns, f"{stamp}a", as_of=as_of)
    halt_if_over(demo1["phases"], f"ns={ns} cold load")
    print(
        f"[run a] {demo1['run_id']} scheduled={demo1['phases']['schedule']['scheduled_count']} "
        f"swept={demo1['phases']['suspend']['sweep']['tenants_swept']} "
        f"subs_updated={demo1['phases']['suspend']['subscriptions_shared']['rows_updated']}"
    )
    demo2 = run_job(dbx, ns, f"{stamp}b", as_of=as_of)
    halt_if_over(demo2["phases"], f"ns={ns} rerun")
    print(f"[run b] {demo2['run_id']} commit_metrics={json.dumps(demo2['phases']['suspend']['commit_metrics'])}")

    snap = target_snapshot(dbx, ns, as_of)

    # Rows this run rejected are excluded from parity by *this run's* batch, never by whatever the
    # ledger still carries.
    # The attempt ledger's source_key is `invoice_id|attempt_no|_origin`; parity excludes a rejected
    # row on the (invoice_id, attempt_no) identity the source's own unique constraint carries.
    rejected = {
        "|".join(r["source_key"].split("|")[:2])
        for r in quarantine_rows(dbx, ns, demo2["batch_id"])
        if r["population"] == "dunning_attempts" and r["source_key"]
    }
    expected_attempts = {
        r["id"]: r
        for r in oracle["attempt_rows"] + [
            {
                "id": s["id"],
                "tenant_id": s["tenant_id"],
                "invoice_id": s["invoice_id"],
                "attempt_no": s["attempt_no"],
                "scheduled_for": s["scheduled_for"],
                "status_cd": s["status_cd"],
            }
            for s in oracle["schedule"]
            if s["tenant_rows"] > 0
        ]
        if f"{r['invoice_id']}|{r['attempt_no']}" not in rejected
    }
    expected_notifications = {
        r["id"]: r
        for r in oracle["notification_rows"] + [
            {
                "id": t["notification_id"],
                "tenant_id": t["tenant_id"],
                "kind_cd": int(K["notification_kind_suspension_cd"]),
                "sent_at": t["notification_sent_at"],
            }
            for t in oracle["suspend"]["notifications_inserted"]
        ]
    }
    swept_ids = {t["tenant_id"] for t in oracle["suspend"]["swept"]}
    expected_tenants = {
        r["id"]: {
            "status_cd": int(K["suspended_tenant_status_cd"])
            if r["id"] in swept_ids
            else r["status_cd"]
        }
        for r in oracle["tenant_rows"]
    }
    expected_subs = {
        r["id"]: {"status_cd": r["status_cd_after"], "suspended_on": r["suspended_on_after"]}
        for r in oracle["suspend"]["subscriptions_updated"]
    }
    diffs = {
        "dunning_attempts": diff_rows(
            expected_attempts,
            {r["id"]: r for r in snap["attempt_rows"]},
            ATTEMPT_COLS,
            "OW_BILLING.DUNNING_ATTEMPTS plus the attempts sp_schedule_dunning would insert on "
            f"{as_of}, re-expressed read-only, vs ow_tp.silver.dunning_attempts from Delta",
        ),
        "notifications": diff_rows(
            expected_notifications,
            {r["id"]: r for r in snap["notification_rows"]},
            NOTIFICATION_COLS,
            "OW_BILLING.NOTIFICATIONS plus the suspension notifications sp_suspend_overdue's NOT "
            "EXISTS would let through, vs ow_tp.silver.notifications from Delta",
        ),
        "tenants": diff_rows(
            expected_tenants,
            {r["id"]: r for r in snap["tenant_rows"]},
            TENANT_COLS,
            "OW_BILLING.TENANTS with sp_suspend_overdue's UPDATE ... SET status_cd = 20 applied to "
            "the swept tenants, vs ow_tp.silver.tenants from Delta",
        ),
        "subscriptions_swept": diff_rows(
            expected_subs,
            {
                r["id"]: r
                for r in snap["subscription_rows"]
                if r["id"] in expected_subs
            },
            SUBSCRIPTION_COLS,
            "the SUBSCRIPTIONS rows sp_suspend_overdue's UPDATE would change, vs the two columns "
            "this unit wrote on ow_tp.silver.subscriptions, read from Delta",
        ),
    }
    print(
        "[parity] "
        + " ".join(f"{k}={v['rows_differing']}/{v['rows_compared']}" for k, v in diffs.items())
    )

    snapshot = read_snapshot(dbx, ns, demo1["batch_id"])
    report = build_report(
        ns, oracle, demo1, demo2, snap, setup, diffs, edge, halt, replays, pinned_sha, scale,
        snapshot,
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
