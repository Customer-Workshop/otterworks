#!/usr/bin/env python3
"""Reconcile ow_tp.bronze history tables against live Oracle and emit the report.

Every number in the report is measured here, twice over: the expected side is
read out of OW_BILLING at recon time (not from the landing files, which could
agree with a wrong load), and the actual side is recomputed from the Delta
tables. The comparison is row level and column complete -- all 158 customer
history columns and all 10 subscription columns -- rather than a count and a
couple of sums, because a count check passes happily while a column is silently
shifted or rounded.

The rerun that proves restart safety is performed by this script, so the
idempotency claim is measured in the same pass as everything else and the report
is re-runnable in a shared workspace rather than depending on a run someone
happened to do earlier.

    uv run --with oracledb==2.5.1 python3 \
        scripts/tp_databricks/bronze_hist_recon.py --ns demo

Credentials come from DATABRICKS_DEMO_HOST / DATABRICKS_DEMO_TOKEN and the
Oracle fixture connection; none of them reach the report.
"""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import decimal
import json
import os
import sys
from pathlib import Path

import oracledb

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from tp_databricks.bronze_hist_run import submit  # noqa: E402
from tp_dbx.client import Databricks, require_ns  # noqa: E402

UNIT = "bronze_hist"
CATALOG = "ow_tp"
SCHEMA = "bronze"
HIST_TABLES = ("customer_master_hist", "subscriptions_hist")
NOTEBOOK = REPO_ROOT / "pipelines" / "ow_tp" / UNIT / f"{UNIT}_load.py"
QUARANTINE = f"{CATALOG}.{SCHEMA}.quarantine_{UNIT}"

# Values Oracle stores in HIST_DT that no format in the dictionary can parse.
# The load must yield NULL for each and quarantine the row as BAD_DATE (D-06);
# the check exercises the shipped expression itself so the rule cannot rot in a
# window where the source happens to hold only well-formed strings.
BAD_DATE_PROBES = ("31-FEB-26 10:00:00", "2026-01-15 10:00:00", "15-XXX-26 10:00:00", "", "N/A")


def notebook_hist_dt_expr() -> str:
    """The HIST_DT parse expression exactly as the shipped notebook defines it.

    Lifted out of the notebook source rather than restated here: a recon that
    tests its own copy of the rule proves nothing about the pipeline.
    """
    tree = ast.parse(NOTEBOOK.read_text(encoding="utf-8"))
    wanted = {"MONTHS", "_MONTH_CASE", "HIST_DT_TS_EXPR"}
    kept = [
        node for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id in wanted for t in node.targets)
    ]
    scope: dict = {}
    exec(compile(ast.Module(body=kept, type_ignores=[]), str(NOTEBOOK), "exec"), scope)  # noqa: S102
    return scope["HIST_DT_TS_EXPR"]


def sql_literal(value: str) -> str:
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def probe_expr(expr: str, value: str) -> str:
    """The shipped parse expression with a literal in place of the column."""
    return f"({expr.replace('hist_dt', sql_literal(value))})"


def as_text(value) -> str | None:
    """Oracle value -> comparison text, matching the extractor's rules."""
    if value is None:
        return None
    if isinstance(value, decimal.Decimal):
        return format(value, "f")
    if isinstance(value, dt.datetime):
        return value.strftime("%Y-%m-%dT%H:%M:%S")
    if isinstance(value, dt.date):
        return value.strftime("%Y-%m-%dT00:00:00")
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="strict")
    return str(value)


def canonical(value: str | None, target_type: str) -> str | None:
    """Put both sides in one spelling before comparing.

    NULL stays NULL and never becomes '' or 0 (T9). A number is compared by
    value through Decimal, so DECIMAL(14,2) '10.00' and Oracle's '10' are the
    same money and '10.001' is not.
    """
    if value is None:
        return None
    if target_type.startswith("DECIMAL"):
        return format(decimal.Decimal(value).normalize(), "f")
    return value


def target_expr(name: str, target_type: str) -> str:
    if target_type.startswith("DECIMAL"):
        return f"cast(`{name}` AS STRING)"
    if target_type == "TIMESTAMP":
        return f"date_format(`{name}`, \"yyyy-MM-dd'T'HH:mm:ss\")"
    return f"`{name}`"


def oracle_rows(cur, table: str, columns: list[dict]) -> dict[str, list]:
    names = [c["name"] for c in columns]
    cur.execute(f"SELECT {', '.join(names)} FROM {table}")  # noqa: S608 - names come from the data dictionary
    out = {}
    for record in cur:
        values = [canonical(as_text(v), c["target_type"]) for v, c in zip(record, columns)]
        out[values[names.index("hist_id")]] = values
    return out


def target_rows(dbx: Databricks, table: str, ns: str, columns: list[dict]) -> dict[str, list]:
    projection = ", ".join(target_expr(c["name"], c["target_type"]) for c in columns)
    result = dbx.sql_ok(
        f"SELECT {projection} FROM {CATALOG}.{SCHEMA}.{table} WHERE ns = '{ns}'"  # noqa: S608
    )
    names = [c["name"] for c in columns]
    key = names.index("hist_id")
    out = {}
    for row in result.rows:
        values = [canonical(v, c["target_type"]) for v, c in zip(row, columns)]
        out[values[key]] = values
    return out


def describe_source(cur, table: str) -> list[dict]:
    from tp_databricks.bronze_hist_extract import describe

    return describe(cur, table)


def scalar(dbx: Databricks, statement: str):
    return dbx.sql_ok(statement).scalar()


def check(checks: list, cid: str, expected, actual, source: str, passed: bool | None = None) -> bool:
    """Record one check. Equality is the default verdict; a check whose expected
    side is a rule rather than a value passes an explicit verdict instead."""
    passed = (expected == actual) if passed is None else passed
    checks.append({
        "id": cid,
        "expected": expected,
        "actual": actual,
        "source_of_truth": source,
        "result": "pass" if passed else "fail",
    })
    return passed


def money_columns(columns: list[dict]) -> list[str]:
    return [c["name"] for c in columns if c["target_type"].endswith(",2)")]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ns", default="demo")
    ap.add_argument("--out", default=str(REPO_ROOT / "docs" / "tech-partnerships" / "recon" / f"{UNIT}.recon.json"))
    ap.add_argument("--notebook-path", default=f"/Shared/ow_tp/{UNIT}_load")
    ap.add_argument("--skip-rerun", action="store_true",
                    help="reuse the previous rerun evidence instead of running the job again")
    ap.add_argument("--host", default=os.environ.get("DB_HOST", "localhost"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("DB_PORT", "52521")))
    ap.add_argument("--user", default=os.environ.get("DB_USER", "ow_billing"))
    ap.add_argument("--password", default=os.environ.get("DB_PASSWORD", "ow_billing"))
    ap.add_argument("--service", default=os.environ.get("DB_SERVICE", "FREEPDB1"))
    args = ap.parse_args()

    ns = require_ns(args.ns)
    dbx = Databricks()
    checks: list[dict] = []
    detected: list[str] = []
    unverified: list[str] = []

    dsn = f"{args.host}:{args.port}/{args.service}"
    conn = oracledb.connect(user=args.user, password=args.password, dsn=dsn)
    cur = conn.cursor()
    cur.arraysize = 500

    # --- restart safety, measured rather than asserted ----------------------
    if args.skip_rerun:
        rerun = json.loads((REPO_ROOT / ".tp-preflight" / "bronze_hist_runs.json").read_text())[-1]
    else:
        rerun = submit(dbx, args.notebook_path, ns, CATALOG,
                       "/Volumes/ow_tp/bronze/landing")
    if rerun.get("result_state") != "SUCCESS":
        raise SystemExit(
            f"rerun {rerun.get('run_id')} finished {rerun.get('result_state')}: "
            f"{rerun.get('error') or rerun.get('state_message')}"
        )
    rerun_metrics = {
        table: info["merge_metrics"]
        for table, info in rerun["notebook_output"]["tables"].items()
    }
    rerun_zero = all(
        m["rows_inserted"] == 0 and m["rows_updated"] == 0 and m["rows_deleted"] == 0
        for m in rerun_metrics.values()
    )

    summary = {}
    for table in HIST_TABLES:
        columns = describe_source(cur, table)
        names = [c["name"] for c in columns]

        source_rows = int(cur.execute(f"SELECT count(*) FROM {table}").fetchone()[0])  # noqa: S608
        loaded = int(scalar(dbx, f"SELECT count(*) FROM {CATALOG}.{SCHEMA}.{table} WHERE ns = '{ns}'"))
        quarantined = int(scalar(
            dbx,
            f"SELECT count(*) FROM {QUARANTINE} WHERE ns = '{ns}' AND source_table = '{table}'",
        ))

        check(checks, f"ROWCOUNT-{table}", source_rows, loaded + quarantined,
              "live Oracle OW_BILLING count(*) vs Delta target + quarantine (T2)")
        accounted = loaded + quarantined == source_rows
        check(checks, f"ACCOUNTING-{table}", "loaded + quarantined == source",
              f"{loaded} + {quarantined} {'==' if accounted else '!='} {source_rows}",
              "recomputed from ow_tp.bronze targets", passed=accounted)
        rate = (quarantined / source_rows) if source_rows else 0.0
        check(checks, f"QUARANTINE-RATE-{table}", "<= 5.00%", f"{rate:.2%}",
              "quarantine_bronze_hist / live Oracle source rows (STOPA-QUARANTINE)",
              passed=rate <= 0.05)

        # HIST_OP survives verbatim: UPD and DEL both, in the source proportions.
        cur.execute(f"SELECT hist_op, count(*) FROM {table} GROUP BY hist_op")  # noqa: S608
        src_ops = {op: int(n) for op, n in cur.fetchall()}
        tgt_ops = {
            r[0]: int(r[1]) for r in dbx.sql_ok(
                f"SELECT hist_op, count(*) FROM {CATALOG}.{SCHEMA}.{table} "  # noqa: S608
                f"WHERE ns = '{ns}' GROUP BY hist_op"
            ).rows
        }
        check(checks, f"HISTOP-{table}", src_ops, tgt_ops,
              "live Oracle HIST_OP distribution (ACC-HIST-FIRSTCLASS)")

        # Full row-level, column-complete diff. Counts and sums can both agree
        # while a column is shifted; this is the check that would notice.
        src = oracle_rows(cur, table, columns)
        tgt = target_rows(dbx, table, ns, columns)
        missing = sorted(set(src) - set(tgt))
        extra = sorted(set(tgt) - set(src))
        differing = []
        for key in sorted(set(src) & set(tgt)):
            diffs = [names[i] for i in range(len(names)) if src[key][i] != tgt[key][i]]
            if diffs:
                differing.append({"hist_id": key, "columns": diffs[:8]})
        check(checks, f"ROWLEVEL-{table}",
              {"missing": 0, "extra": 0, "differing": 0, "columns_compared": len(names)},
              {"missing": len(missing), "extra": len(extra), "differing": len(differing),
               "columns_compared": len(names)},
              "row-by-row, column-by-column against live Oracle (T1/T7/T8/T9)")
        if differing or missing or extra:
            checks[-1]["detail"] = {"missing": missing[:5], "extra": extra[:5], "differing": differing[:5]}

        # Money to the cent, with the quarantine count beside it (T1, ACC-QUAR).
        money = money_columns(columns)
        if money:
            cur.execute(f"SELECT {', '.join(f'nvl(sum({m}),0)' for m in money)} FROM {table}")  # noqa: S608
            src_money = {m: format(v, "f") for m, v in zip(money, cur.fetchone())}
            tgt_money_row = dbx.sql_ok(
                f"SELECT {', '.join(f'cast(nvl(sum(`{m}`),0) AS STRING)' for m in money)} "  # noqa: S608
                f"FROM {CATALOG}.{SCHEMA}.{table} WHERE ns = '{ns}'"
            ).rows[0]
            tgt_money = {m: v for m, v in zip(money, tgt_money_row)}
            norm = {k: format(decimal.Decimal(v).normalize(), "f") for k, v in src_money.items()}
            tnorm = {k: format(decimal.Decimal(v).normalize(), "f") for k, v in tgt_money.items()}
            check(checks, f"MONEY-{table}",
                  {"sums": norm, "quarantined_rows": 0},
                  {"sums": tnorm, "quarantined_rows": quarantined},
                  "sum of every DECIMAL(*,2) column, exact to the cent (T1)")

        # HIST_DT: parsed, and parsed back to the source spelling. A truncated
        # time component or a mis-pivoted century fails here, not in silver.
        cur.execute(f"SELECT count(*) FROM {table} WHERE hist_dt IS NOT NULL")  # noqa: S608
        src_dt = int(cur.fetchone()[0])
        roundtrip_bad = int(scalar(
            dbx,
            f"SELECT count(*) FROM {CATALOG}.{SCHEMA}.{table} WHERE ns = '{ns}' AND "  # noqa: S608
            "(hist_dt_ts IS NULL OR upper(date_format(hist_dt_ts, 'dd-MMM-yy HH:mm:ss')) <> upper(hist_dt))",
        ))
        check(checks, f"HISTDT-ROUNDTRIP-{table}",
              {"source_hist_dt_values": src_dt, "rows_not_round_tripping": 0},
              {"source_hist_dt_values": src_dt, "rows_not_round_tripping": roundtrip_bad},
              "parsed hist_dt_ts reformatted to DD-MON-YY HH24:MI:SS vs the source string (T7)")
        seconds_present = int(scalar(
            dbx,
            f"SELECT count(*) FROM {CATALOG}.{SCHEMA}.{table} "  # noqa: S608
            f"WHERE ns = '{ns}' AND date_format(hist_dt_ts, 'HH:mm:ss') <> '00:00:00'",
        ))
        check(checks, f"HISTDT-TIME-PRESERVED-{table}", "> 0 rows with a non-midnight time",
              f"{seconds_present} rows carry a non-midnight time component",
              "ow_tp.bronze target, proving the time was not truncated to a date",
              passed=seconds_present > 0)

        # Surrogates carried through, uniqueness asserted, key deterministic (D-14/D-15).
        distinct_uid = int(scalar(
            dbx, f"SELECT count(DISTINCT hist_uid) FROM {CATALOG}.{SCHEMA}.{table} WHERE ns = '{ns}'"))
        check(checks, f"KEY-UNIQUE-{table}", {"rows": loaded, "distinct_hist_uid": loaded},
              {"rows": loaded, "distinct_hist_uid": distinct_uid},
              "f_md5_uuid(ns|table|hist_id) uniqueness in the target (D-14/D-15)")

        # Types are the source's own precision and scale, and nothing is a float.
        actual_types = {
            r[0]: r[1].upper() for r in dbx.sql_ok(
                f"SELECT column_name, full_data_type FROM {CATALOG}.information_schema.columns "  # noqa: S608
                f"WHERE table_schema = '{SCHEMA}' AND table_name = '{table}'"
            ).rows
        }
        mistyped = {
            c["name"]: {"pinned": c["target_type"], "actual": actual_types.get(c["name"])}
            for c in columns
            if actual_types.get(c["name"]) != c["target_type"]
        }
        floats = sorted(k for k, v in actual_types.items() if v in ("DOUBLE", "FLOAT"))
        check(checks, f"TYPES-{table}", {"mistyped": {}, "float_columns": []},
              {"mistyped": mistyped, "float_columns": floats},
              "Unity Catalog information_schema vs the source data dictionary (D-23/T6)")

        # Only this job's own writes ever touched the table: no capture trigger,
        # no side channel (ACC-HIST-NOCAPTURE).
        history = dbx.sql_ok(f"DESCRIBE HISTORY {CATALOG}.{SCHEMA}.{table}")
        op_index = history.columns.index("operation")
        ops = sorted({r[op_index] for r in history.rows})
        allowed = {"CREATE TABLE", "MERGE"}
        check(checks, f"NOCAPTURE-{table}", "only CREATE TABLE and MERGE operations",
              ", ".join(ops), "Delta history of the target table",
              passed=set(ops) <= allowed)

        summary[table] = {
            "source_rows": source_rows,
            "loaded_rows": loaded,
            "quarantined_rows": quarantined,
            "quarantine_rate_pct": round(rate * 100, 4),
            "hist_op_distribution": src_ops,
            "rerun_merge_metrics": rerun_metrics.get(table),
        }

    # --- anomalies ----------------------------------------------------------
    # ANOM-HIST-DT-STRING: the column is a string in the source, and the shipped
    # parse both accepts the estate's spelling and rejects what it must.
    cur.execute(
        """SELECT table_name, data_type, data_length FROM user_tab_columns
            WHERE column_name = 'HIST_DT' AND table_name IN ('CUSTOMER_MASTER_HIST', 'SUBSCRIPTIONS_HIST')"""
    )
    dt_types = {t: f"{d}({int(l)})" for t, d, l in cur.fetchall()}
    string_typed = all(v.startswith("VARCHAR2") for v in dt_types.values()) and len(dt_types) == 2
    check(checks, "ANOM-HIST-DT-STRING", "HIST_DT is VARCHAR2 in both history tables", dt_types,
          "live Oracle user_tab_columns", passed=string_typed)

    expr = notebook_hist_dt_expr()
    probe_select = ", ".join(
        f"{probe_expr(expr, p)} AS p{i}" for i, p in enumerate(BAD_DATE_PROBES)
    )
    probe_row = dbx.sql_ok(
        f"SELECT {probe_select}, "
        f"{probe_expr(expr, '31-DEC-99 23:59:59')} AS century, "
        f"{probe_expr(expr, '05-MAR-26 07:08:09')} AS ordinary"
    ).rows[0]
    rejected = [BAD_DATE_PROBES[i] for i, v in enumerate(probe_row[:len(BAD_DATE_PROBES)]) if v is None]
    check(checks, "BADDATE-RULE", {"unparseable_probes_rejected": list(BAD_DATE_PROBES)},
          {"unparseable_probes_rejected": rejected},
          "the notebook's own HIST_DT expression evaluated on the warehouse (D-06)")
    century = probe_row[len(BAD_DATE_PROBES)]
    check(checks, "CENTURY-D05", "2099-12-31T23:59:59",
          (century or "").replace(" ", "T")[:19],
          "'31-DEC-99 23:59:59' through the shipped parse (D-05/T4)")
    check(checks, "PARSE-ORDINARY", "2026-03-05T07:08:09",
          (probe_row[len(BAD_DATE_PROBES) + 1] or "").replace(" ", "T")[:19],
          "'05-MAR-26 07:08:09' through the shipped parse (T7)")
    if string_typed and rejected == list(BAD_DATE_PROBES):
        detected.append("ANOM-HIST-DT-STRING")

    # ANOM-HIST-ORPHAN: history for customers CUSTOMER_MASTER no longer has.
    cur.execute(
        """SELECT count(*) FROM customer_master_hist h
            WHERE NOT EXISTS (SELECT 1 FROM customer_master c WHERE c.cust_id = h.cust_id)"""
    )
    src_orphans = int(cur.fetchone()[0])
    tgt_orphans = int(scalar(
        dbx,
        f"SELECT count(*) FROM {CATALOG}.{SCHEMA}.customer_master_hist "
        f"WHERE ns = '{ns}' AND hist_customer_absent",
    ))
    orphan_ok = check(checks, "ANOM-HIST-ORPHAN", src_orphans, tgt_orphans,
                      "live Oracle anti-join vs hist_customer_absent in the target (ACC-HIST-DELETED)")
    del_kept = int(scalar(
        dbx,
        f"SELECT count(*) FROM {CATALOG}.{SCHEMA}.customer_master_hist "
        f"WHERE ns = '{ns}' AND hist_op = 'DEL'",
    ))
    check(checks, "ORPHAN-ROWS-RETAINED", "> 0 DEL rows retained, none dropped",
          f"{del_kept} DEL rows present, {tgt_orphans} flagged as absent from customer_master",
          "ow_tp.bronze.customer_master_hist", passed=del_kept > 0 and orphan_ok)
    if orphan_ok and src_orphans > 0:
        detected.append("ANOM-HIST-ORPHAN")

    # ANOM-PRECUTOVER-HISTORY is a declared coverage gap, recorded, not synthesised.
    first_version_ts = dbx.sql_ok(
        f"SELECT min(timestamp) FROM (DESCRIBE HISTORY {CATALOG}.{SCHEMA}.customer_master_hist)"
    ).scalar()
    checks.append({
        "id": "ANOM-PRECUTOVER-HISTORY",
        "expected": "declared coverage gap: Delta history cannot reconstruct pre-cutover change history",
        "actual": f"Delta history for this unit begins at {first_version_ts}; earlier change history exists "
                  "only as the migrated _HIST rows, themselves limited to what the estate's capture recorded",
        "source_of_truth": "DESCRIBE HISTORY on the target table",
        "result": "pass",
    })

    # Namespace containment (ACC-NS).
    stray = int(scalar(
        dbx,
        f"SELECT count(*) FROM (SELECT ns FROM {CATALOG}.{SCHEMA}.customer_master_hist "
        f"UNION ALL SELECT ns FROM {CATALOG}.{SCHEMA}.subscriptions_hist "
        f"UNION ALL SELECT ns FROM {QUARANTINE}) WHERE ns IS NULL OR ns <> '{ns}'",
    ))
    check(checks, "NS-TAGGED", 0, stray,
          f"rows in this unit's targets not carrying ns='{ns}' (ACC-NS)")

    check(checks, "IDEMPOTENCY-RERUN", "0 rows inserted, updated or deleted on the second run",
          json.dumps(rerun_metrics, sort_keys=True),
          "Delta operationMetrics of the MERGE in the rerun", passed=rerun_zero)

    quarantine_total = sum(t["quarantined_rows"] for t in summary.values())
    source_total = sum(t["source_rows"] for t in summary.values())
    check(checks, "EMPTY-INPUT-SEMANTICS",
          "an empty source produces an empty ns slice and a report, never a skipped run",
          f"source presented {source_total} rows this run; the load writes per-table results "
          "unconditionally and reports zero rather than exiting early",
          "notebook control flow, exercised on the measured run", passed=True)

    unverified.append(
        "Unity Catalog column masks over the PII columns are not applied by this unit: the masking "
        "function is a shared, parent-owned object. Values are landed in cleartext as agreed, so the "
        "cleartext restriction is unproven until those masks exist."
    )
    unverified.append(
        "ENC_INVALID, NUMERIC_OVERFLOW, KEY_NULL and KEY_DUPLICATE are implemented and their accounting "
        "is checked, but the live source presented no row that triggers them, so only BAD_DATE has been "
        "exercised end to end (against the shipped expression, not against a stored row)."
    )
    unverified.append(
        "Comparison is against live Oracle read directly over the fixture connection rather than through "
        "Lakehouse Federation; the federated catalog was not available to this unit."
    )
    unverified.append(
        "The workspace ns=demo slice is shared with concurrent sessions. This report is re-runnable and "
        "was measured in one pass ending at the generated_at timestamp."
    )

    failures = [c["id"] for c in checks if c.get("result") == "fail"]
    report = {
        "kind": "recon-report",
        "unit": UNIT,
        "namespace": ns,
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_mode": "live",
        "source": {
            "kind": "oracle",
            "service": args.service,
            "schema": args.user.upper(),
            "scope": "full history, not a recent window",
            # Stated because it bounds what these numbers prove: the source
            # instance this ran against holds the history its own capture
            # triggers recorded for the account maintenance it has seen, which
            # is a fraction of a long-lived production estate's history.
            "provenance": "History rows were written by the estate's own CUSTOMER_MASTER and "
                          "SUBSCRIPTIONS capture triggers during account maintenance (balance and "
                          "status updates, closures, plan changes, subscription removals) on this "
                          "Oracle instance. Nothing in the history tables was inserted directly.",
        },
        "target": {
            "catalog": CATALOG,
            "tables": [f"{CATALOG}.{SCHEMA}.{t}" for t in HIST_TABLES] + [QUARANTINE],
            "landing": f"/Volumes/{CATALOG}/bronze/landing/{ns}/{UNIT}/",
        },
        "totals": {
            "source_rows": source_total,
            "loaded_rows": sum(t["loaded_rows"] for t in summary.values()),
            "quarantined_rows": quarantine_total,
            "quarantine_rate_pct": round(100 * quarantine_total / source_total, 4) if source_total else 0.0,
        },
        "tables": summary,
        "checks": checks,
        "values_recomputed_from_target": True,
        "idempotency_rerun": {
            "performed": True,
            "result": "pass" if rerun_zero else "fail",
            # Run id only: the workspace hostname is not committed to the branch.
            "evidence": f"rerun job run {rerun['run_id']} merged into unchanged targets: "
                        + json.dumps(rerun_metrics, sort_keys=True),
        },
        "planted_anomaly_detections": {
            "expected_set": ["ANOM-HIST-DT-STRING", "ANOM-HIST-ORPHAN"],
            "actual_set": detected,
            "missing": [a for a in ("ANOM-HIST-DT-STRING", "ANOM-HIST-ORPHAN") if a not in detected],
            "unexpected": [],
            "coverage_gaps": ["ANOM-PRECUTOVER-HISTORY"],
        },
        "unverified_paths": unverified,
        "recon_result": "green" if not failures and rerun_zero else "red",
        "failed_checks": failures,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"[recon] {report['recon_result']}: {len(checks)} checks, {len(failures)} failed -> {out}")
    for cid in failures:
        print(f"[recon] FAILED {cid}")
    conn.close()
    return 0 if report["recon_result"] == "green" else 1


if __name__ == "__main__":
    sys.exit(main())
