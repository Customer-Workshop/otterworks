#!/usr/bin/env python3
"""Wave-0 tooling for the Commission Pay COMMISSION_DW -> Databricks migration.

Subcommands (all parameterised by --ns, default cdw):
  provision   CREATE CATALOG/SCHEMA/VOLUME IF NOT EXISTS for the ow_tp layout (W0-1).
  extract     Read-only extract of the 9 baseline objects from the legacy Oracle
              warehouse into ordered UTF-8 CSV + manifest.json (W0-3). Runs sqlplus
              inside the legacy container; issues SELECT statements only.
  upload      Land the extract under /Volumes/ow_tp/bronze/landing/<ns>/{feed,baseline}/
              through the Files API, re-read every byte and compare with the
              manifest sha256 (W0-3).
  load-feed   CREATE OR REPLACE the four bronze feed tables from the landed CSVs and
              assert row counts against the manifest (W0-3; same statement text the
              job's T0 task uses).

Every statement is fixed text parameterised only by namespace, so the wave-0 run and
the recon harness provably read the same objects.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from client import Databricks, require_ns

CATALOG = "ow_tp"
SCHEMAS = {
    "bronze": "Landed legacy snapshots (feeds and recon baselines)",
    "silver": "Conformed warehouse tables",
    "gold": "Report surfaces",
    "ops": "Run logs, quarantine, recon runs",
}

# object -> (group, ordered SELECT, ORDER BY key columns)
# Money/percent columns are rendered with fixed scale so cents compare exactly;
# DATE -> YYYY-MM-DD; TIMESTAMP -> ISO-8601 UTC. loaded_at is excluded from the
# warehouse baseline by tolerance rule (03_recon_tolerances.md).
EXTRACTS: dict[str, tuple[str, str, list[str]]] = {
    "AGENTS": ("feed",
        ("SELECT agent_id, agent_code, full_name, license_no, status, "
         "TO_CHAR(hired_date,'YYYY-MM-DD') AS hired_date "
         "FROM commission_pay.agents ORDER BY agent_id"),
        ["agent_id"]),
    "PRODUCTS": ("feed",
        ("SELECT product_code, product_name, line_of_business "
         "FROM commission_pay.products ORDER BY product_code"),
        ["product_code"]),
    "POLICIES": ("feed",
        ("SELECT policy_id, policy_no, product_code, holder_name, "
         "TO_CHAR(annual_premium,'FM9999999990.00') AS annual_premium, "
         "TO_CHAR(issued_date,'YYYY-MM-DD') AS issued_date, status "
         "FROM commission_pay.policies ORDER BY policy_id"),
        ["policy_id"]),
    "COMMISSION_LEDGER": ("feed",
        ("SELECT ledger_id, policy_id, agent_id, period_month, rate_id, "
         "TO_CHAR(split_pct,'FM990.00') AS split_pct, "
         "TO_CHAR(base_premium,'FM9999999990.00') AS base_premium, "
         "TO_CHAR(commission_amt,'FM9999999990.00') AS commission_amt, "
         "TO_CHAR(SYS_EXTRACT_UTC(calculated_at),'YYYY-MM-DD\"T\"HH24:MI:SS.FF6\"Z\"') AS calculated_at "
         "FROM commission_pay.commission_ledger ORDER BY ledger_id"),
        ["ledger_id"]),
    "DIM_AGENT": ("baseline",
        ("SELECT agent_key, agent_id, agent_code, full_name, status "
         "FROM commission_dw.dim_agent ORDER BY agent_key"),
        ["agent_key"]),
    "DIM_PRODUCT": ("baseline",
        ("SELECT product_key, product_code, product_name, line_of_business "
         "FROM commission_dw.dim_product ORDER BY product_key"),
        ["product_key"]),
    "DIM_PERIOD": ("baseline",
        ("SELECT period_key, period_month, year_num, month_num, quarter_num "
         "FROM commission_dw.dim_period ORDER BY period_key"),
        ["period_key"]),
    "FACT_COMMISSION": ("baseline",
        ("SELECT fact_id, agent_key, product_key, period_key, policy_id, "
         "TO_CHAR(split_pct,'FM990.00') AS split_pct, "
         "TO_CHAR(base_premium,'FM9999999990.00') AS base_premium, "
         "TO_CHAR(commission_amt,'FM9999999990.00') AS commission_amt "
         "FROM commission_dw.fact_commission ORDER BY fact_id"),
        ["fact_id"]),
    "MV_AGENT_COMMISSION_SUMMARY": ("baseline",
        ("SELECT agent_code, full_name, period_month, line_of_business, policy_rows, "
         "TO_CHAR(total_commission,'FM9999999990.00') AS total_commission "
         "FROM commission_dw.mv_agent_commission_summary "
         "ORDER BY agent_code, full_name, period_month, line_of_business"),
        ["agent_code", "full_name", "period_month", "line_of_business"]),
}

# bronze feed table -> explicit schema (Oracle NUMBER(p,s) -> DECIMAL(p,s))
FEED_SCHEMAS: dict[str, str] = {
    "AGENTS": "agent_id BIGINT, agent_code STRING, full_name STRING, license_no STRING, status STRING, hired_date DATE",
    "PRODUCTS": "product_code STRING, product_name STRING, line_of_business STRING",
    "POLICIES": "policy_id BIGINT, policy_no STRING, product_code STRING, holder_name STRING, "
                "annual_premium DECIMAL(12,2), issued_date DATE, status STRING",
    "COMMISSION_LEDGER": "ledger_id BIGINT, policy_id BIGINT, agent_id BIGINT, period_month STRING, rate_id BIGINT, "
                         "split_pct DECIMAL(5,2), base_premium DECIMAL(12,2), commission_amt DECIMAL(12,2), "
                         "calculated_at TIMESTAMP",
}


def landing(ns: str) -> str:
    return f"/Volumes/{CATALOG}/bronze/landing/{ns}"


def local_dir(ns: str) -> Path:
    return Path("etl/legacy-extra/commission_dw") / ns


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def get_file(dbx: Databricks, path: str) -> bytes:
    url = dbx.host + f"/api/2.0/fs/files{urllib.parse.quote(path, safe='/')}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {dbx.token}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.read()
    except urllib.error.URLError as exc:
        raise SystemExit(f"failed to GET {path}: {exc}") from exc


# --- provision -------------------------------------------------------------
def provision_statements() -> list[str]:
    stmts = [f"CREATE CATALOG IF NOT EXISTS {CATALOG} COMMENT 'OtterWorks tech-partnerships migration (prefix ow_tp)'"]
    for schema, comment in SCHEMAS.items():
        stmts.append(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{schema} COMMENT '{comment}'")
    stmts.append(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.bronze.landing COMMENT 'Landed legacy files by namespace'")
    return stmts


def cmd_provision(args) -> int:
    dbx = Databricks(warehouse_id=args.warehouse)
    for stmt in provision_statements():
        dbx.sql_ok(stmt)
        print(f"OK  {stmt.split(' COMMENT')[0]}")
    rows = dbx.sql_ok(f"SHOW SCHEMAS IN {CATALOG}").rows
    print("schemas:", sorted(r[0] for r in rows))
    return 0


# --- extract ---------------------------------------------------------------
SQLPLUS_PREAMBLE = """SET MARKUP CSV ON DELIMITER , QUOTE ON
SET FEEDBACK OFF HEADING ON PAGESIZE 0 LINESIZE 32767 TRIMSPOOL ON TERMOUT OFF ECHO OFF VERIFY OFF
SET NULL ''
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,';
"""


def run_sqlplus(container: str, script: str) -> str:
    cmd = ["docker", "exec", "-i", container, "sqlplus", "-s",
           "commission_dw/commission_dw@localhost:1521/FREEPDB1"]
    proc = subprocess.run(cmd, input=script, capture_output=True, text=True, timeout=300, check=False)
    if proc.returncode != 0 or "ORA-" in proc.stdout or "SP2-" in proc.stdout:
        raise SystemExit(f"sqlplus failed (rc={proc.returncode}):\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}")
    return proc.stdout


def normalise_csv(raw: str) -> tuple[bytes, int]:
    """sqlplus CSV -> canonical UTF-8 CSV (\\n line ends, header row kept). Returns
    bytes and data-row count."""
    lines = [ln for ln in raw.replace("\r\n", "\n").split("\n") if ln.strip() != ""]
    if not lines:
        raise SystemExit("empty sqlplus output")
    reader = list(csv.reader(lines))
    header = [h.strip('"').lower() for h in reader[0]]
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(header)
    for row in reader[1:]:
        writer.writerow(row)
    return out.getvalue().encode("utf-8"), len(reader) - 1


def cmd_extract(args) -> int:
    ns = require_ns(args.ns)
    container = f"otterworks-insurance-{ns}-insurance-oracle-1"
    outdir = local_dir(ns)
    outdir.mkdir(parents=True, exist_ok=True)
    extracted_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    manifest = {"kind": "baseline-manifest", "namespace": ns, "source": "COMMISSION_DW@FREEPDB1 (read-only)",
                "extracted_at": extracted_at, "files": {}}
    for obj, (group, select, keys) in EXTRACTS.items():
        script = SQLPLUS_PREAMBLE + select + ";\nEXIT;\n"
        payload, nrows = normalise_csv(run_sqlplus(container, script))
        path = outdir / f"{obj}.csv"
        path.write_bytes(payload)
        manifest["files"][f"{obj}.csv"] = {
            "group": group, "source_object": obj, "rows": nrows, "sha256": sha256(payload),
            "bytes": len(payload), "order_key": keys, "extracted_at": extracted_at,
        }
        print(f"{obj:30s} rows={nrows:5d} sha256={manifest['files'][f'{obj}.csv']['sha256'][:16]}…")
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    fact_rows = manifest["files"]["FACT_COMMISSION.csv"]["rows"]
    if fact_rows == 0:
        print("HALT: FACT_COMMISSION baseline has 0 rows (DEC-011 gate)", file=sys.stderr)
        return 2
    print(f"manifest -> {outdir / 'manifest.json'}")
    return 0


# --- upload ----------------------------------------------------------------
def cmd_upload(args) -> int:
    ns = require_ns(args.ns)
    dbx = Databricks(warehouse_id=args.warehouse)
    src = local_dir(ns)
    manifest = json.loads((src / "manifest.json").read_text())
    failures = 0
    for name, meta in manifest["files"].items():
        payload = (src / name).read_bytes()
        if sha256(payload) != meta["sha256"]:
            raise SystemExit(f"local {name} does not match manifest sha256")
        target = f"{landing(ns)}/{meta['group']}/{name}"
        dbx.put_file(target, payload)
        remote = get_file(dbx, target)
        ok = sha256(remote) == meta["sha256"]
        failures += 0 if ok else 1
        print(f"{'OK ' if ok else 'BAD'} {target} bytes={len(remote)}")
    for group in ("feed", "baseline"):
        dbx.put_file(f"{landing(ns)}/{group}/manifest.json", (src / "manifest.json").read_bytes())
    print("checksum mismatches:", failures)
    return 1 if failures else 0


# --- load-feed -------------------------------------------------------------
def feed_table(ns: str, obj: str) -> str:
    return f"{CATALOG}.bronze.{obj.lower()}_{ns}"


def load_feed_statements(ns: str) -> list[tuple[str, str]]:
    stmts = []
    for obj, schema in FEED_SCHEMAS.items():
        path = f"{landing(ns)}/feed/{obj}.csv"
        stmts.append((obj,
            (f"CREATE OR REPLACE TABLE {feed_table(ns, obj)} AS "
             f"SELECT * FROM read_files('{path}', format => 'csv', header => true, "
             f"schema => '{schema}', mode => 'FAILFAST', timestampFormat => \"yyyy-MM-dd'T'HH:mm:ss.SSSSSS'Z'\")")))
    return stmts


def cmd_load_feed(args) -> int:
    ns = require_ns(args.ns)
    dbx = Databricks(warehouse_id=args.warehouse)
    manifest_path = local_dir(ns) / "manifest.json"
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"failed to read local manifest {manifest_path}: {exc}") from exc
    remote_manifest = get_file(dbx, f"{landing(ns)}/feed/manifest.json")
    if remote_manifest != manifest_bytes:
        raise SystemExit(f"remote feed manifest does not match local {manifest_path}")
    for obj in FEED_SCHEMAS:
        name = f"{obj}.csv"
        payload = get_file(dbx, f"{landing(ns)}/feed/{name}")
        try:
            meta = manifest["files"][name]
            expected_sha256 = meta["sha256"]
            expected_rows = meta["rows"]
        except (KeyError, TypeError) as exc:
            raise SystemExit(f"local manifest is missing feed metadata for {name}") from exc
        rows = len(payload.splitlines()) - 1
        if sha256(payload) != expected_sha256:
            raise SystemExit(f"remote feed {name} does not match manifest sha256")
        if rows != expected_rows:
            raise SystemExit(f"remote feed {name} has {rows} rows; manifest has {expected_rows}")
    bad = 0
    for obj, stmt in load_feed_statements(ns):
        dbx.sql_ok(stmt)
        n = int(dbx.sql_ok(f"SELECT COUNT(*) FROM {feed_table(ns, obj)}").scalar())
        want = manifest["files"][f"{obj}.csv"]["rows"]
        ok = n == want
        bad += 0 if ok else 1
        print(f"{'OK ' if ok else 'BAD'} {feed_table(ns, obj)} rows={n} manifest={want}")
    return 1 if bad else 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("action", choices=["provision", "extract", "upload", "load-feed"])
    p.add_argument("--ns", default="cdw")
    p.add_argument("--warehouse", default="565cd2fd713738c4")
    args = p.parse_args()
    return {"provision": cmd_provision, "extract": cmd_extract,
            "upload": cmd_upload, "load-feed": cmd_load_feed}[args.action](args)


if __name__ == "__main__":
    raise SystemExit(main())
