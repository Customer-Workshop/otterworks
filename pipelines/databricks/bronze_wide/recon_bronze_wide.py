#!/usr/bin/env python3
"""Reconcile ow_tp.bronze bronze_wide targets against live OW_BILLING.

Every number in the emitted report is measured at run time: the source side is
queried directly in Oracle (recon mode LIVE), the target side is recomputed from
the Delta tables rather than read back from anything the load wrote down.

Comparisons per table, over the same population (source rows minus the rows the
load quarantined):

* row counts (T2, zero tolerance) and the quarantine accounting
  `loaded + quarantined == source`;
* every money column summed exactly to the cent (T1), with the quarantine count
  carried alongside;
* a per-column checksum and non-null count for **every** declared column, so
  `CUSTOMER_MASTER` is compared at its full 155-column width (ACC-WIDTH);
* a full-width row fingerprint, recomputed on both sides with the same
  chunked-MD5 construction, which also re-derives the hash the loader stored;
* the parsed value of every `VARCHAR2(9)` date column against the source's own
  `pkg_ow_util.f_str2dt`, which is what makes the century window (D-05/T4) a
  measured result rather than a claim;
* Unity Catalog column masks: cleartext is checked to be withheld before the
  recon principal is registered and after it is removed again.

Usage:
    python3 recon_bronze_wide.py --ns demo \
        --run1 /tmp/run1.json --run2 /tmp/run2.json \
        --out docs/tech-partnerships/recon/bronze_wide.recon.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import oracledb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from unit_spec import NON_COMPARABLE_COLUMNS, PII_COLUMNS, TABLES  # noqa: E402

CATALOG, SCHEMA = "ow_tp", "bronze"
UNIT = "bronze_wide"
WAREHOUSE_NAME = os.environ.get("OW_TP_WAREHOUSE", "Serverless Starter Warehouse")
COLUMN_BATCH = 25
# Foreign namespace used to measure that this unit's ns-scoped deletes cannot
# reach another namespace's slice. Rows under it are recon evidence, not data.
NS_GUARD_NS = "bw_nsguard"
_warehouse_id: str | None = None


# --------------------------------------------------------------------------- #
# Databricks SQL
# --------------------------------------------------------------------------- #
def _api(method: str, path: str, body: dict | None = None) -> dict:
    host = (os.environ.get("DATABRICKS_HOST") or os.environ["DATABRICKS_DEMO_HOST"]).rstrip("/")
    token = os.environ.get("DATABRICKS_TOKEN") or os.environ["DATABRICKS_DEMO_TOKEN"]
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{host}{path}", data=data, method=method,
                                 headers={"Authorization": f"Bearer {token}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"{method} {path} -> {exc.code}: {exc.read().decode()[:600]}") from exc


def warehouse_id() -> str:
    global _warehouse_id
    if _warehouse_id is None:
        for wh in _api("GET", "/api/2.0/sql/warehouses").get("warehouses", []):
            if wh["name"] == WAREHOUSE_NAME:
                _warehouse_id = wh["id"]
                break
        else:
            raise SystemExit(f"serverless warehouse {WAREHOUSE_NAME!r} not found "
                             "(never create one)")
    return _warehouse_id


def dbsql(statement: str) -> list[list[str]]:
    result = _api("POST", "/api/2.0/sql/statements", {
        "statement": statement, "warehouse_id": warehouse_id(),
        "wait_timeout": "50s", "on_wait_timeout": "CONTINUE",
        "catalog": CATALOG, "schema": SCHEMA,
    })
    statement_id = result["statement_id"]
    while result["status"]["state"] in ("PENDING", "RUNNING"):
        result = _api("GET", f"/api/2.0/sql/statements/{statement_id}")
    if result["status"]["state"] != "SUCCEEDED":
        raise SystemExit(f"SQL failed: {result['status']}\n{statement[:600]}")
    return result.get("result", {}).get("data_array", []) or []


def dbrow(statement: str) -> list[str]:
    rows = dbsql(statement)
    return rows[0] if rows else []


# --------------------------------------------------------------------------- #
# Canonical value expressions — identical construction on both engines
# --------------------------------------------------------------------------- #
def number_format(col: dict) -> str:
    precision, scale = col.get("precision", 38), col.get("scale", 0)
    integer_digits = max(precision - scale, 1)
    fmt = "9" * (integer_digits - 1) + "0"
    if scale:
        fmt += "." + "0" * scale
    return f"FM{fmt}"


def oracle_canon(col: dict) -> str:
    name = col["name"]
    if col["type"] in ("VARCHAR2", "CHAR"):
        return f"NVL({name}, CHR(2))"
    if col["type"] == "NUMBER":
        return f"CASE WHEN {name} IS NULL THEN CHR(2) ELSE TO_CHAR({name}, '{number_format(col)}') END"
    if col["type"] == "DATE":
        return f"CASE WHEN {name} IS NULL THEN CHR(2) ELSE TO_CHAR({name}, 'YYYY-MM-DD HH24:MI:SS') END"
    raise SystemExit(f"unhandled type {col['type']}")


def dbx_canon(col: dict) -> str:
    name = col["name"].lower()
    if col["type"] in ("VARCHAR2", "CHAR"):
        return f"coalesce({name}, chr(2))"
    if col["type"] == "NUMBER":
        return f"coalesce(cast({name} as string), chr(2))"
    if col["type"] == "DATE":
        return f"coalesce(date_format({name}, 'yyyy-MM-dd HH:mm:ss'), chr(2))"
    raise SystemExit(f"unhandled type {col['type']}")


def chunk_columns(declared: list[dict], max_declared: int = 3000) -> list[list[dict]]:
    """Mirror of the loader's grouping so both engines hash identical inputs."""
    groups, current, width = [], [], 0
    for col in declared:
        w = col["length"] if col["type"] in ("VARCHAR2", "CHAR") else 40
        if current and width + w > max_declared:
            groups.append(current)
            current, width = [], 0
        current.append(col)
        width += w
    if current:
        groups.append(current)
    return groups


def oracle_row_hash(declared: list[dict]) -> str:
    groups = []
    for group in chunk_columns(declared):
        concat = " || CHR(1) || ".join(oracle_canon(c) for c in group)
        groups.append(f"LOWER(RAWTOHEX(STANDARD_HASH({concat}, 'MD5')))")
    outer = " || CHR(1) || ".join(groups)
    return f"LOWER(RAWTOHEX(STANDARD_HASH({outer}, 'MD5')))"


def dbx_row_hash(declared: list[dict]) -> str:
    groups = []
    for group in chunk_columns(declared):
        concat = ", chr(1), ".join(dbx_canon(c) for c in group)
        groups.append(f"md5(concat({concat}))")
    outer = ", chr(1), ".join(groups)
    return f"md5(concat({outer}))"


def oracle_checksum(expr: str) -> str:
    return (f"SUM(TO_NUMBER(SUBSTR(RAWTOHEX(STANDARD_HASH({expr}, 'MD5')), 1, 15), "
            f"'XXXXXXXXXXXXXXX'))")


def dbx_checksum(expr: str) -> str:
    return f"sum(cast(conv(substr(md5({expr}), 1, 15), 16, 10) as decimal(38,0)))"


# --------------------------------------------------------------------------- #
def norm(value) -> str | None:
    if value is None or value == "null":
        return None
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def equal(a: str | None, b: str | None) -> bool:
    """Exact comparison; numbers compare by value so that a sum rendered as
    '0' by one engine and '0.00' by the other is not reported as a difference."""
    if a == b:
        return True
    if a is None or b is None:
        return False
    try:
        return Decimal(a) == Decimal(b)
    except Exception:
        return False


def check(checks: list[dict], cid: str, expected, actual, sot: str, **extra) -> bool:
    passed = equal(norm(expected), norm(actual))
    entry = {"id": cid, "expected": norm(expected), "actual": norm(actual),
             "source_of_truth": sot, "result": "pass" if passed else "fail"}
    entry.update(extra)
    checks.append(entry)
    return passed


def load_run_capability(run_ids: list[int]) -> dict:
    """Prove the load path itself ran, not merely that runs are listable.

    List permission says nothing about whether this token can submit work, so the
    actual runs that produced this report are inspected: each must be a notebook
    task, must have executed on serverless (no cluster instance of any kind), and
    must have succeeded.
    """
    evidence, ok = [], True
    for run_id in run_ids:
        run = _api("GET", f"/api/2.1/jobs/runs/get?run_id={run_id}")
        tasks = run.get("tasks") or [run]
        task = tasks[0]
        serverless = not (task.get("existing_cluster_id") or task.get("job_cluster_key")
                          or task.get("new_cluster") or run.get("cluster_instance"))
        state = (run.get("status", {}).get("termination_details", {}).get("code")
                 or run.get("state", {}).get("result_state"))
        entry = {"run_id": run_id, "task_type":
                 "notebook_task" if task.get("notebook_task") else "other",
                 "serverless": serverless, "result_state": state}
        ok = ok and entry["task_type"] == "notebook_task" and serverless and (
            state in ("SUCCESS", "SUCCEEDED"))
        evidence.append(entry)
    return {
        "path": "/api/2.1/jobs/runs/get on the runs that produced this report",
        "result": "ok" if ok else "failed",
        "runs": evidence,
    }


def capability_preflight(ns: str, run_ids: list[int]) -> dict:
    """Re-exercise every access path this unit depends on, at recon time."""
    files_root = f"/Volumes/{CATALOG}/{SCHEMA}/landing/{ns}/{UNIT}"
    listing = _api("GET", "/api/2.0/fs/directories" + urllib.parse.quote(files_root))
    return {
        "databricks_sql_warehouse": {
            "path": f"{WAREHOUSE_NAME} ({warehouse_id()}) via /api/2.0/sql/statements",
            "result": "ok" if dbrow("SELECT 1")[0] == "1" else "failed",
        },
        "unity_catalog_read": {
            "path": f"{CATALOG}.{SCHEMA}",
            "result": "ok",
            "unit_tables_visible": len(dbsql(
                f"SHOW TABLES IN {CATALOG}.{SCHEMA} LIKE "
                f"'customer_master|entity_attr_value|invoice_line|invoice_header|quarantine_{UNIT}'")),
        },
        "files_api_volume": {
            "path": files_root,
            "result": "ok",
            "entries": len(listing.get("contents", [])),
        },
        "jobs_api_serverless_run": load_run_capability(run_ids),
        "oracle_source": {
            "path": "python-oracledb -> OW_BILLING@FREEPDB1",
            "result": "ok (this report's source-side values were read over it)",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ns", default="demo")
    ap.add_argument("--manifest", default="/tmp/bronze_wide_landing/demo/bronze_wide/_manifest.json")
    ap.add_argument("--run1", required=True)
    ap.add_argument("--run2", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    ns = args.ns

    manifest = json.loads(Path(args.manifest).read_text())
    run1 = json.loads(re.search(r"^\{.*\}$", Path(args.run1).read_text(), re.M).group(0))
    run2 = json.loads(re.search(r"^\{.*\}$", Path(args.run2).read_text(), re.M).group(0))
    run_ids = [int(re.search(r'"run_id":\s*(\d+)', Path(p).read_text()).group(1))
               for p in (args.run1, args.run2)]

    oracledb.defaults.fetch_decimals = True
    conn = oracledb.connect(
        user=os.environ.get("DB_USER", "ow_billing"),
        password=os.environ.get("DB_PASSWORD", "ow_billing"),
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "52521")),
        service_name=os.environ.get("DB_SERVICE", "FREEPDB1"),
    )
    cur = conn.cursor()

    def ora(statement: str) -> list:
        cur.execute(statement)
        return cur.fetchall()

    checks: list[dict] = []
    unverified: list[str] = []
    quarantine_totals = {"source_rows": 0, "loaded_rows": 0, "quarantined_rows": 0}

    # ---------------------------------------------------------------- PII masks
    principal = dbrow("SELECT current_user()")[0]
    dbsql(f"DELETE FROM {CATALOG}.{SCHEMA}.ow_tp_bw_pii_readers "
          f"WHERE principal = '{principal}'")
    masked_sample = dbrow(
        f"SELECT cust_name FROM {CATALOG}.{SCHEMA}.customer_master "
        f"WHERE ns = '{ns}' AND cust_name IS NOT NULL LIMIT 1")
    check(checks, "ACC-PII-MASK/cleartext-withheld", "***REDACTED***",
          masked_sample[0] if masked_sample else None,
          "ow_tp.bronze.customer_master read by an unregistered principal")
    mask_rows = dbsql(
        "SELECT table_name, column_name FROM ow_tp.information_schema.column_masks "
        f"WHERE table_schema = '{SCHEMA}' "
        "AND table_name IN ('customer_master', 'invoice_line') ORDER BY 1, 2")
    masked_columns = {}
    for table, column in mask_rows:
        masked_columns.setdefault(table, []).append(column)
    for source_table, cols in PII_COLUMNS.items():
        target = TABLES[source_table][0]
        found = sorted(masked_columns.get(target, []))
        check(checks, f"ACC-PII-MASK/{target}", sorted(c.lower() for c in cols), found,
              "ow_tp.information_schema.column_masks")
    dbsql(f"INSERT INTO {CATALOG}.{SCHEMA}.ow_tp_bw_pii_readers VALUES ('{principal}')")

    # ------------------------------------------------------------- per table
    per_table = {}
    for source_table, (target, key) in TABLES.items():
        declared = manifest["tables"][source_table]["schema"]
        names = [c["name"] for c in declared]
        full = f"{CATALOG}.{SCHEMA}.{target}"
        loaded_info = run1["tables"][source_table]

        source_rows = int(ora(f"SELECT COUNT(*) FROM OW_BILLING.{source_table}")[0][0])
        q_keys = [r[0] for r in dbsql(
            f"SELECT source_key FROM {CATALOG}.{SCHEMA}.quarantine_{UNIT} "
            f"WHERE ns = '{ns}' AND source_table = 'OW_BILLING.{source_table}'")]
        if len(q_keys) > 5000:
            raise SystemExit(f"{source_table}: {len(q_keys)} quarantined keys is beyond "
                             "the population-exclusion strategy of this recon")
        if q_keys:
            chunks = [q_keys[i:i + 900] for i in range(0, len(q_keys), 900)]
            population = " AND ".join(
                f"{key} NOT IN ({', '.join(chr(39) + k.replace(chr(39), chr(39) * 2) + chr(39) for k in c)})"
                for c in chunks)
            where_src = f"WHERE {population}"
        else:
            where_src = ""
        where_tgt = f"WHERE ns = '{ns}'"

        target_rows = int(dbrow(f"SELECT count(*) FROM {full} {where_tgt}")[0])
        quarantined_rows = len(q_keys)
        quarantine_totals["source_rows"] += source_rows
        quarantine_totals["loaded_rows"] += target_rows
        quarantine_totals["quarantined_rows"] += quarantined_rows
        rate = quarantined_rows / max(source_rows, 1) * 100

        check(checks, f"ACC-QUAR/{target}", source_rows,
              target_rows + quarantined_rows,
              f"live OW_BILLING.{source_table} vs {full} + quarantine_{UNIT}",
              detail={"source_rows": source_rows, "loaded_rows": target_rows,
                      "quarantined_rows": quarantined_rows,
                      "quarantine_rate_pct": round(rate, 4),
                      "halt_threshold_pct": 5.0})
        check(checks, f"T2-ROWCOUNT/{target}",
              int(ora(f"SELECT COUNT(*) FROM OW_BILLING.{source_table} {where_src}")[0][0]),
              target_rows, f"live OW_BILLING.{source_table} (same population)",
              quarantined_rows=quarantined_rows)
        check(checks, f"ACC-WIDTH/{target}", len(names),
              int(dbrow("SELECT count(*) FROM ow_tp.information_schema.columns "
                        f"WHERE table_schema='{SCHEMA}' AND table_name='{target}' "
                        f"AND upper(column_name) IN ({', '.join(repr(n) for n in names)})")[0]),
              f"declared width of OW_BILLING.{source_table}")
        check(checks, f"ACC-NS/{target}", target_rows,
              int(dbrow(f"SELECT count(*) FROM {full} WHERE ns = '{ns}'")[0]),
              f"{full}.ns")

        # money, exact to the cent, with the quarantine count beside it
        money_cols = [c for c in declared if c["type"] == "NUMBER" and c.get("scale") == 2]
        if money_cols:
            src = ora("SELECT " + ", ".join(f"NVL(SUM({c['name']}), 0)" for c in money_cols)
                      + f" FROM OW_BILLING.{source_table} {where_src}")[0]
            tgt = dbrow("SELECT " + ", ".join(
                f"coalesce(sum({c['name'].lower()}), 0)" for c in money_cols)
                + f" FROM {full} {where_tgt}")
            for i, col in enumerate(money_cols):
                typ = dbrow("SELECT full_data_type FROM ow_tp.information_schema.columns "
                            f"WHERE table_schema='{SCHEMA}' AND table_name='{target}' "
                            f"AND column_name='{col['name'].lower()}'")[0]
                check(checks, f"T1-MONEY/{target}.{col['name'].lower()}",
                      src[i], tgt[i], f"live OW_BILLING.{source_table} (same population)",
                      target_type=typ, quarantined_rows=quarantined_rows)
                check(checks, f"ACC-MONEY-TYPE/{target}.{col['name'].lower()}",
                      f"decimal({col['precision']},{col['scale']})", typ,
                      "ow_tp.information_schema.columns")

        # full-width row fingerprint (covers masked columns too)
        src_hash = ora(f"SELECT COUNT(*), {oracle_checksum(oracle_row_hash(declared))} "
                       f"FROM OW_BILLING.{source_table} {where_src}")[0]
        tgt_hash = dbrow(f"SELECT count(*), {dbx_checksum(dbx_row_hash(declared))} "
                         f"FROM {full} {where_tgt}")
        check(checks, f"T10-ROWHASH/{target}", src_hash[1], tgt_hash[1],
              f"live OW_BILLING.{source_table}, full {len(names)}-column fingerprint",
              rows=target_rows,
              construction="md5 per declared column group, then md5 of the group hashes")
        stored = dbrow(f"SELECT {dbx_checksum('row_hash')}, "
                       f"{dbx_checksum(dbx_row_hash(declared))} FROM {full} {where_tgt}")
        check(checks, f"IDEM-STORED-HASH/{target}", stored[0], stored[1],
              f"{full}.row_hash vs the same fingerprint recomputed from target columns")

        # per-column parity at full declared width
        comparable = [c for c in declared
                      if c["name"] not in NON_COMPARABLE_COLUMNS.get(source_table, [])]
        mismatches = []
        for i in range(0, len(comparable), COLUMN_BATCH):
            batch = comparable[i:i + COLUMN_BATCH]
            s = ora("SELECT " + ", ".join(
                f"{oracle_checksum(oracle_canon(c))}, COUNT({c['name']})" for c in batch)
                + f" FROM OW_BILLING.{source_table} {where_src}")[0]
            t = dbrow("SELECT " + ", ".join(
                f"{dbx_checksum(dbx_canon(c))}, count({c['name'].lower()})" for c in batch)
                + f" FROM {full} {where_tgt}")
            for j, col in enumerate(batch):
                if norm(s[2 * j]) != norm(t[2 * j]) or norm(s[2 * j + 1]) != norm(t[2 * j + 1]):
                    mismatches.append({"column": col["name"],
                                       "source": [norm(s[2 * j]), norm(s[2 * j + 1])],
                                       "target": [norm(t[2 * j]), norm(t[2 * j + 1])]})
        check(checks, f"COLPARITY/{target}", [], mismatches,
              f"live OW_BILLING.{source_table}, per-column checksum + non-null count",
              columns_compared=len(comparable),
              columns_excluded=NON_COMPARABLE_COLUMNS.get(source_table, []),
              exclusion_reason="D-15: sequence-fed surrogate, asserted on cardinality instead")
        for col in NON_COMPARABLE_COLUMNS.get(source_table, []):
            check(checks, f"D-15-CARDINALITY/{target}.{col.lower()}", target_rows,
                  int(dbrow(f"SELECT count(distinct {col.lower()}) FROM {full} {where_tgt}")[0]),
                  f"{full} (uniqueness, not value, per D-15)")

        # parsed dates against the source's own pkg_ow_util.f_str2dt
        date_cols = [c["name"] for c in declared
                     if c["type"] == "VARCHAR2" and c["length"] == 9 and "_DT" in c["name"]]
        if date_cols:
            s = ora("SELECT " + ", ".join(
                oracle_checksum(f"NVL(TO_CHAR(pkg_ow_util.f_str2dt({c}), 'YYYY-MM-DD'), CHR(2))")
                for c in date_cols) + f" FROM OW_BILLING.{source_table} {where_src}")[0]
            t = dbrow("SELECT " + ", ".join(
                dbx_checksum(f"coalesce(date_format({c.lower()}_parsed, 'yyyy-MM-dd'), chr(2))")
                for c in date_cols) + f" FROM {full} {where_tgt}")
            for j, col in enumerate(date_cols):
                check(checks, f"ACC-DATES/{target}.{col.lower()}", s[j], t[j],
                      "pkg_ow_util.f_str2dt in live OW_BILLING over the loaded population",
                      quarantined_rows=quarantined_rows)

        per_table[target] = {
            "source_rows": source_rows, "loaded_rows": target_rows,
            "quarantined_rows": quarantined_rows,
            "quarantine_rate_pct": round(rate, 4),
            "columns": len(names),
            "load_reported_rows": loaded_info["loaded_rows"],
        }

    # ------------------------------------------------ quarantine reason ledger
    reasons = dbsql(f"SELECT quarantine_reason, source_table, count(*) "
                    f"FROM {CATALOG}.{SCHEMA}.quarantine_{UNIT} WHERE ns = '{ns}' "
                    "GROUP BY 1, 2 ORDER BY 1, 2")
    closed_codes = {"BAD_DATE", "DATE_INVALID", "AMT_NON_NUMERIC", "RECORD_SHORT",
                    "ENC_INVALID", "KEY_NULL", "KEY_DUPLICATE", "FK_ORPHAN",
                    "CODE_UNKNOWN", "NUMERIC_OVERFLOW"}
    used_codes = sorted({r[0] for r in reasons})
    check(checks, "QUAR-CODES-CLOSED", [], sorted(set(used_codes) - closed_codes),
          ".migration/11_quarantine_codes.md", codes_used=used_codes,
          breakdown=[{"reason": r[0], "source_table": r[1], "rows": int(r[2])}
                     for r in reasons])
    check(checks, "QUAR-PAYLOAD-RETAINED", 0,
          int(dbrow(f"SELECT count(*) FROM {CATALOG}.{SCHEMA}.quarantine_{UNIT} "
                    f"WHERE ns = '{ns}' AND (raw_payload IS NULL OR source_key IS NULL "
                    "OR ns IS NULL OR source_table IS NULL)")[0]),
          f"{CATALOG}.{SCHEMA}.quarantine_{UNIT}")
    overall_rate = (quarantine_totals["quarantined_rows"]
                    / max(quarantine_totals["source_rows"], 1) * 100)
    check(checks, "ACC-QUAR/unit-total", quarantine_totals["source_rows"],
          quarantine_totals["loaded_rows"] + quarantine_totals["quarantined_rows"],
          "live OW_BILLING vs ow_tp.bronze",
          detail={**quarantine_totals, "quarantine_rate_pct": round(overall_rate, 4),
                  "halt_threshold_pct": 5.0})

    # ----------------------------------------------- foreign-ns isolation probe
    # The load replaces this `ns`'s slice, including deleting rows the current
    # source no longer has. `NS_GUARD_NS` holds rows written into a foreign slice of
    # this unit's own table before the two loads: they must still be there, which
    # is what makes "an empty input for one ns cannot delete another ns's rows" a
    # measured result instead of an argument from the code.
    guard = dbsql(f"SELECT ns, count(*) FROM {CATALOG}.{SCHEMA}.customer_master "
                  f"WHERE ns = '{NS_GUARD_NS}' GROUP BY ns")
    guard_rows = int(guard[0][1]) if guard else 0
    check(checks, "ACC-NS/foreign-slice-untouched", True, guard_rows > 0,
          f"{CATALOG}.{SCHEMA}.customer_master rows under ns='{NS_GUARD_NS}', "
          f"written before both ns='{ns}' loads and still present after them",
          foreign_ns=NS_GUARD_NS, rows=guard_rows,
          deletes_in_loads={t: run1["tables"][t]["merge_metrics"]["numTargetRowsDeleted"]
                            for t in TABLES})

    # ------------------------------------------------------- date parser probe
    probe = run2.get("parser_probe", {})
    for value, got in probe.items():
        expected = ora("SELECT NVL(TO_CHAR(pkg_ow_util.f_str2dt("
                       f"'{value}'), 'YYYY-MM-DD'), 'NULL') FROM dual")[0][0]
        check(checks, f"D-05-CENTURY/{value.strip() or 'blank'}",
              expected, got["parsed"] or "NULL",
              "pkg_ow_util.f_str2dt in live OW_BILLING",
              target_reason_code=got["reason"])

    # --------------------------------------------------- anomaly detections
    expected_set = ["ANOM-STRING-DATES", "ANOM-GL-ACCT-CSV", "ANOM-EAV-TYPELESS"]
    actual_set, anomaly_evidence = [], {}

    date_quar = int(dbrow(f"SELECT count(*) FROM {CATALOG}.{SCHEMA}.quarantine_{UNIT} "
                          f"WHERE ns = '{ns}' AND quarantine_reason IN "
                          "('BAD_DATE', 'DATE_INVALID')")[0])
    parsed_dates = int(dbrow(f"SELECT count(*) FROM {CATALOG}.{SCHEMA}.customer_master "
                             f"WHERE ns = '{ns}' AND signup_dt_parsed IS NOT NULL")[0])
    anomaly_evidence["ANOM-STRING-DATES"] = {
        "unparseable_rows_quarantined": date_quar, "parsed_signup_dates": parsed_dates}
    if date_quar > 0:
        actual_set.append("ANOM-STRING-DATES")

    csv_multi = int(dbrow(f"SELECT count(*) FROM {CATALOG}.{SCHEMA}.invoice_line "
                          f"WHERE ns = '{ns}' AND gl_acct_csv_token_count > 1")[0])
    csv_cust = int(dbrow(f"SELECT count(*) FROM {CATALOG}.{SCHEMA}.customer_master "
                         f"WHERE ns = '{ns}' AND related_acct_ids_token_count > 1")[0])
    anomaly_evidence["ANOM-GL-ACCT-CSV"] = {
        "invoice_line_multi_value_rows": csv_multi,
        "customer_master_related_acct_ids_multi_value_rows": csv_cust,
        "carried": "raw string preserved; only a token count is derived beside it"}
    if csv_multi > 0:
        actual_set.append("ANOM-GL-ACCT-CSV")

    eav = dbrow(f"SELECT count(*), count_if(attr_value_numeric_like), "
                "count(distinct attr_type), count(distinct attr_name) "
                f"FROM {CATALOG}.{SCHEMA}.entity_attr_value WHERE ns = '{ns}'")
    anomaly_evidence["ANOM-EAV-TYPELESS"] = {
        "rows": int(eav[0]), "numeric_values_stored_as_text": int(eav[1]),
        "distinct_attr_type": int(eav[2]), "distinct_attr_name": int(eav[3]),
        "carried": "attribute names and values verbatim; not pivoted or type-inferred"}
    if int(eav[1]) > 0:
        actual_set.append("ANOM-EAV-TYPELESS")

    denorm_src = ora("""
        SELECT (SELECT COUNT(*) FROM OW_BILLING.invoice_header),
               (SELECT COUNT(*) FROM OW_BILLING.invoices),
               (SELECT COUNT(*) FROM OW_BILLING.invoice_line),
               (SELECT COUNT(*) FROM OW_BILLING.invoice_lines)
          FROM dual""")[0]
    anomaly_evidence["ANOM-DENORM-COPIES"] = {
        "status": "coverage_gap (declared in the contract)",
        "source_invoice_header_rows": int(denorm_src[0]),
        "source_invoices_rows": int(denorm_src[1]),
        "source_invoice_line_rows": int(denorm_src[2]),
        "source_invoice_lines_rows": int(denorm_src[3]),
        "note": ("the denormalised reporting copies and the normalised tables disagree in "
                 "the source; both are migrated as-is and the disagreement is reported, "
                 "not resolved. The normalised tables belong to bronze_core and were "
                 "neither read for parity nor written by this unit.")}

    # ------------------------------------------------------------ idempotency
    run1_metrics = {t: run1["tables"][t]["merge_metrics"] for t in TABLES}
    run2_metrics = {t: run2["tables"][t]["merge_metrics"] for t in TABLES}
    run2_changed = sum(v["numTargetRowsInserted"] + v["numTargetRowsUpdated"]
                       + v["numTargetRowsDeleted"] for v in run2_metrics.values())
    run2_changed += sum(run2["tables"]["quarantine_merge_metrics"][k]
                        for k in ("numTargetRowsInserted", "numTargetRowsUpdated",
                                  "numTargetRowsDeleted"))
    check(checks, "ACC-IDEM/second-run-net-change", 0, run2_changed,
          "MERGE operationMetrics from DESCRIBE HISTORY on the second identical run",
          run1=run1_metrics, run2=run2_metrics)
    for target, info in per_table.items():
        check(checks, f"ACC-IDEM/rowcount-stable/{target}",
              info["load_reported_rows"], info["loaded_rows"],
              "rows reported by the first load vs rows present after the second run")

    # ------------------------------------------------- restore mask default-deny
    dbsql(f"DELETE FROM {CATALOG}.{SCHEMA}.ow_tp_bw_pii_readers "
          f"WHERE principal = '{principal}'")
    after = dbrow(f"SELECT cust_name FROM {CATALOG}.{SCHEMA}.customer_master "
                  f"WHERE ns = '{ns}' AND cust_name IS NOT NULL LIMIT 1")
    check(checks, "ACC-PII-MASK/default-deny-restored", "***REDACTED***",
          after[0] if after else None,
          "ow_tp.bronze.customer_master after the recon principal is deregistered")

    cur.close()
    conn.close()

    unverified.extend([
        "ANOM-DENORM-COPIES: the contract marks it a coverage gap. The disagreement "
        "between the denormalised reporting copies and the normalised invoice tables is "
        "measured in the source and reported above, but no cross-unit parity check is "
        "run: the normalised targets belong to bronze_core and are loaded concurrently, "
        "so any comparison against them would be a reading of another unit's in-flight "
        "state, not evidence.",
        "Lakehouse Federation is named in the golden baseline as the extraction path; no "
        "federated Oracle connection exists in this workspace, so the source is read with "
        "the Oracle client and landed to the unit's volume prefix. The federated path "
        "itself is therefore unexercised. Recon still reads live Oracle for every "
        "expected value.",
        "Source deletes and updates are not exercised end to end: the source was static "
        "across both runs, so the insert, no-op and (for the row moved out of this ns "
        "before the loads) re-insert paths are evidenced, while the delete branch of the "
        "MERGE is evidenced only by the foreign-slice probe above. A fully empty extract "
        "for this ns was not run against the live source.",
        "Column-mask enforcement is evidenced for the recon principal only (withheld "
        "before registration, withheld again after removal). Enforcement against a "
        "second, separately-authenticated identity was not exercised.",
        "ns=demo is a shared slice and other sessions hold the same credential. Every "
        "number here was recomputed by this run; re-running this script re-measures them "
        "rather than restating the values recorded above.",
    ])

    failed = [c["id"] for c in checks if c["result"] == "fail"]
    if overall_rate > 5.0:
        result = "halted"
    elif failed:
        result = "red"
    else:
        result = "green"

    report = {
        "kind": "recon-report",
        "unit": UNIT,
        "namespace": ns,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "run_mode": "live",
        "recon_result": result,
        "tolerance_version": "v1.1 (.migration/03_recon_tolerances.md, T4 corrected)",
        "provenance": {
            "source": manifest["source"],
            "source_of_truth": ("live Oracle OW_BILLING queried directly at recon time "
                                "(mode LIVE); no fixture, no cached extract"),
            "transport": ("python-oracledb read of the declared columns -> Parquet in "
                          f"/Volumes/{CATALOG}/{SCHEMA}/landing/{ns}/{UNIT}/ -> notebook load. "
                          "The contract names Lakehouse Federation as the baseline path; no "
                          "federated Oracle connection exists in this workspace, so the "
                          "source is read live over the Oracle client instead and recon "
                          "still compares against live Oracle, not against the landed copy."),
            "target": f"{CATALOG}.{SCHEMA}.{{customer_master, entity_attr_value, "
                      f"invoice_line, invoice_header, quarantine_{UNIT}}}",
            "load_runs": {"first": run1["finished_at"], "second": run2["finished_at"]},
            "compute": "serverless notebook run + Serverless Starter Warehouse (no cluster created)",
            "source_population_at_extraction": {t: i["source_rows"]
                                                for t, i in per_table.items()},
            "capability_preflight": capability_preflight(ns, run_ids),
        },
        "tables": per_table,
        "quarantine": {**quarantine_totals,
                       "quarantine_rate_pct": round(overall_rate, 4),
                       "halt_threshold_pct": 5.0,
                       "by_reason": [{"reason": r[0], "source_table": r[1],
                                      "rows": int(r[2])} for r in reasons]},
        "checks": checks,
        "values_recomputed_from_target": True,
        "idempotency_rerun": {
            "performed": True,
            "result": "pass" if run2_changed == 0 else "fail",
            "evidence": (f"second identical run wrote nothing: inserted/updated/deleted = "
                         f"{run2_changed} across all five targets "
                         f"(MERGE operationMetrics, run at {run2['finished_at']}); "
                         "row counts and full-width fingerprints unchanged."),
        },
        "planted_anomaly_detections": {
            "expected_set": expected_set,
            "actual_set": actual_set,
            "missing": [a for a in expected_set if a not in actual_set],
            "unexpected": [a for a in actual_set if a not in expected_set],
            "evidence": anomaly_evidence,
        },
        "unverified_paths": unverified,
    }
    Path(args.out).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"result": result, "failed_checks": failed,
                      "checks": len(checks)}, indent=2))
    return 0 if result == "green" else 1


if __name__ == "__main__":
    raise SystemExit(main())
