#!/usr/bin/env python3
"""Local control CLI for the wave-0 CUSTBILL Databricks scaffold."""
from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from client import Databricks, DbxError, require_custbill_ns

CATALOG = "ow_tp"
LANDING = f"/Volumes/{CATALOG}/bronze/landing"
BRONZE = f"{CATALOG}.bronze.custbill_raw"
SILVER = f"{CATALOG}.silver.custbill_records"
QUARANTINE = f"{CATALOG}.silver.custbill_quarantine"
GOLD = f"{CATALOG}.gold.finance_billing"
TABLES = (BRONZE, SILVER, QUARANTINE, GOLD)
BATCH_SIZE = 200


def esc(value: str) -> str:
    """Escape a Databricks SQL string literal as the showcase does."""
    return value.replace("\\", "\\\\").replace("'", "''")


def legacy_dat_files(root: Path, history: bool = False) -> list[tuple[str, Path]]:
    if history:
        candidates = sorted((root / "sftp-drop" / "history").glob("*/CUSTBILL*.dat"))
    else:
        candidates = sorted((root / "incoming").glob("CUSTBILL*.dat*"))
        if not candidates:
            candidates = sorted((root / "sftp-drop" / "upload").glob("CUSTBILL*.dat"))
    by_name: dict[str, Path] = {}
    for path in candidates:
        if not path.is_file():
            continue
        marker = path.name.find(".dat")
        normalized = path.name[:marker + len(".dat")] if marker >= 0 else f"{path.name}.dat"
        by_name.setdefault(normalized, path)
    return sorted(by_name.items())


def bronze_rows_from_file(path: Path, source_file: str) -> list[dict]:
    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    lines = payload.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    rows = []
    for line_no, raw in enumerate(lines, start=1):
        text = raw.decode("latin-1")
        if text.startswith("HDR"):
            kind = "HDR"
        elif text.startswith("TRL"):
            kind = "TRL"
        else:
            kind = "BODY"
        rows.append({
            "source_file": source_file,
            "line_no": line_no,
            "record_kind": kind,
            "raw_line": text,
            "file_sha256": digest,
        })
    return rows


def _decimal_literal(value: str) -> str:
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"invalid bill amount {value!r}") from exc
    if not amount.is_finite() or amount.as_tuple().exponent < -2:
        raise ValueError(f"bill amount must be a finite value with at most two decimals: {value!r}")
    return format(amount.quantize(Decimal("0.01")), "f")


def _date_literal(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"invalid bill date {value!r}") from exc
    return value


def silver_rows_from_file(path: Path) -> list[dict]:
    rows = []
    source_file = f"{path.stem}.dat"
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        fields = line.split("|")
        if len(fields) != 6:
            raise ValueError(f"{path}:{line_no}: expected six pipe-delimited fields")
        cust_id, cust_name, bill_date, bill_amt, currency, rec_type = fields
        rows.append({
            "source_file": source_file,
            "line_no": line_no,
            "cust_id": cust_id,
            "cust_name": cust_name,
            "bill_date": _date_literal(bill_date),
            "bill_amt": _decimal_literal(bill_amt),
            "currency": currency,
            "rec_type": rec_type,
        })
    return rows


def _batches(rows: list[dict]):
    for start in range(0, len(rows), BATCH_SIZE):
        yield rows[start:start + BATCH_SIZE]


def _insert(dbx: Databricks, table: str, columns: tuple[str, ...], values: list[str]) -> None:
    for batch in _batches(values):
        dbx.sql_ok(f"INSERT INTO {table} ({', '.join(columns)}) VALUES {', '.join(batch)}")


def _landing_root(ns: str, part: str) -> str:
    return f"{LANDING}/{ns}/{part}"


def _delete_tree(dbx: Databricks, volume_path: str) -> None:
    """Files API directory deletes are non-recursive; empty the tree bottom-up first.

    list_dir returns one page; re-list after each pass until the directory is empty.
    """
    for _ in range(10_000):
        entries = dbx.list_dir(volume_path)
        if not entries:
            break
        for entry in entries:
            child = entry.get("path") or f"{volume_path}/{entry['name']}"
            if entry.get("is_directory"):
                _delete_tree(dbx, child)
            else:
                status = dbx.delete_file(child)
                if status not in (200, 204, 404):
                    raise DbxError(f"DELETE {child} -> HTTP {status}")
    else:
        raise DbxError(f"{volume_path} still non-empty after 10000 delete passes")
    status = dbx.delete_dir(volume_path)
    if status not in (200, 204, 404):
        raise DbxError(f"DELETE {volume_path} -> HTTP {status}")


def _clean_landing(dbx: Databricks, ns: str) -> None:
    for part in ("incoming", "archive", "reports"):
        _delete_tree(dbx, _landing_root(ns, part))


def _listed_names(result, preferred: tuple[str, ...], fallback_index: int = -1) -> set[str]:
    names = set()
    for index, row in enumerate(result.dicts()):
        for key in preferred:
            if key in row and row[key] is not None:
                names.add(str(row[key]))
                break
        else:
            if result.rows:
                names.add(str(result.rows[index][fallback_index]))
    return names


def _try_names(dbx: Databricks, statement: str, preferred: tuple[str, ...],
               fallback_index: int = -1) -> set[str]:
    try:
        return _listed_names(dbx.sql_ok(statement), preferred, fallback_index)
    except DbxError:
        return set()


def cmd_provision_check(dbx: Databricks, _args: argparse.Namespace) -> int:
    checks: list[tuple[str, bool]] = []
    catalogs = _try_names(dbx, "SHOW CATALOGS", ("catalog",), 0)
    checks.append((CATALOG, CATALOG in catalogs))
    for schema in ("bronze", "silver", "gold"):
        schemas = _try_names(dbx, f"SHOW SCHEMAS IN {CATALOG}", ("databaseName", "schema_name"))
        checks.append((f"{CATALOG}.{schema}", schema in schemas))
    volumes = _try_names(dbx, f"SHOW VOLUMES IN {CATALOG}.bronze", ("volume_name",), 2)
    checks.append((f"{CATALOG}.bronze.landing", "landing" in volumes))
    for schema, expected in (("bronze", "custbill_raw"), ("silver", "custbill_records"),
                             ("silver", "custbill_quarantine"), ("gold", "finance_billing")):
        tables = _try_names(dbx, f"SHOW TABLES IN {CATALOG}.{schema}", ("tableName",), 1)
        checks.append((f"{CATALOG}.{schema}.{expected}", expected in tables))
    checks.append(("job ow_tp_custbill", dbx.find_job("ow_tp_custbill") is not None))
    print("OBJECT\tSTATUS")
    for name, present in checks:
        print(f"{name}\t{'OK' if present else 'MISSING'}")
    return 0 if all(present for _, present in checks) else 1


def cmd_land(dbx: Databricks, args: argparse.Namespace) -> int:
    if args.clean:
        _clean_landing(dbx, args.ns)
        print(f"cleaned landing directories for ns={args.ns}")
        return 0
    root = Path(args.legacy_root)
    files = legacy_dat_files(root)
    for source_file, path in files:
        dbx.put_file(f"{_landing_root(args.ns, 'incoming')}/{source_file}", path.read_bytes())
    print(f"uploaded {len(files)} CUSTBILL file(s) for ns={args.ns}")
    return 0


def cmd_seed_fixture(dbx: Databricks, args: argparse.Namespace) -> int:
    if args.ns == "demo":
        raise SystemExit("seed-fixture refuses --ns demo; use a non-demo fixture namespace")
    root = Path(args.legacy_root)
    if args.layer == "bronze":
        files = legacy_dat_files(root, history=args.history)
        rows = [row for source_file, path in files
                for row in bronze_rows_from_file(path, source_file)]
        table = BRONZE
        columns = ("ns", "source_file", "line_no", "record_kind", "raw_line",
                   "file_sha256", "ingested_at")
        values = [
            f"('{esc(args.ns)}','{esc(row['source_file'])}',{row['line_no']},"
            f"'{row['record_kind']}','{esc(row['raw_line'])}','{row['file_sha256']}',current_timestamp())"
            for row in rows
        ]
    else:
        files = sorted((root / "parsed").glob("CUSTBILL*.psv"))
        files = [path for path in files if path.is_file()]
        rows = [row for path in files for row in silver_rows_from_file(path)]
        table = SILVER
        columns = ("ns", "source_file", "line_no", "cust_id", "cust_name", "bill_date",
                   "bill_amt", "currency", "rec_type", "parsed_at")
        values = [
            f"('{esc(args.ns)}','{esc(row['source_file'])}',{row['line_no']},"
            f"'{esc(row['cust_id'])}','{esc(row['cust_name'])}',DATE '{row['bill_date']}',"
            f"CAST('{row['bill_amt']}' AS DECIMAL(12,2)),'{esc(row['currency'])}',"
            f"'{esc(row['rec_type'])}',current_timestamp())"
            for row in rows
        ]
    dbx.sql_ok(f"DELETE FROM {table} WHERE ns = '{esc(args.ns)}'")
    _insert(dbx, table, columns, values)
    print(f"seeded {len(rows)} {args.layer} row(s) for ns={args.ns}")
    return 0


def cmd_run_job(dbx: Databricks, args: argparse.Namespace) -> int:
    job = dbx.find_job("ow_tp_custbill")
    if not job:
        raise SystemExit("job ow_tp_custbill not found")
    params = {"ns": args.ns}
    if args.report_date:
        params["report_date"] = args.report_date
    run_id = dbx.run_job(int(job["job_id"]), params)
    print(f"triggered run: {dbx.run_url(run_id)}")
    if not args.wait:
        return 0
    run = dbx.wait_run(run_id)
    state = run.get("state", {})
    print(f"result: {state.get('result_state')} — {str(state.get('state_message', ''))[:400]}")
    return 0 if state.get("result_state") == "SUCCESS" else 1


def cmd_verify_trigger(dbx: Databricks, _args: argparse.Namespace) -> int:
    job = dbx.find_job("ow_tp_custbill")
    if not job:
        raise SystemExit("job ow_tp_custbill not found")
    job_id = int(job["job_id"])
    fetched = dbx.ok("GET", f"/api/2.1/jobs/get?job_id={job_id}")
    settings = fetched.get("settings", {})
    trigger = settings.get("trigger", {})
    file_arrival = trigger.get("file_arrival") if isinstance(trigger, dict) else None
    print(f"file-arrival trigger present: {bool(file_arrival)}")
    print(f"trigger: {trigger}")
    return 0


def cmd_wipe(dbx: Databricks, args: argparse.Namespace) -> int:
    if args.ns == "demo" and not args.i_mean_demo:
        raise SystemExit("wipe refuses --ns demo unless --i-mean-demo is supplied")
    for table in TABLES:
        dbx.sql_ok(f"DELETE FROM {table} WHERE ns = '{esc(args.ns)}'")
    _clean_landing(dbx, args.ns)
    print(f"wiped namespace {args.ns}")
    return 0


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser()
    cli.add_argument("--ns", required=True, type=require_custbill_ns)
    commands = cli.add_subparsers(dest="command", required=True)

    commands.add_parser("provision-check")
    land = commands.add_parser("land")
    land.add_argument("--legacy-root", required=False)
    land.add_argument("--clean", action="store_true")
    seed = commands.add_parser("seed-fixture")
    seed.add_argument("--layer", required=True, choices=("bronze", "silver"))
    seed.add_argument("--legacy-root", required=True)
    seed.add_argument("--history", action="store_true",
                      help="bronze only: seed sftp-drop/history/*/CUSTBILL*.dat (gen_history_data.pl output)")
    run = commands.add_parser("run-job")
    run.add_argument("--wait", action="store_true")
    run.add_argument("--report-date", type=_date_literal)
    commands.add_parser("verify-trigger")
    wipe = commands.add_parser("wipe")
    wipe.add_argument("--i-mean-demo", action="store_true")
    return cli


def main() -> int:
    args = parser().parse_args()
    if args.command == "land" and not args.clean and not args.legacy_root:
        raise SystemExit("land requires --legacy-root unless --clean is supplied")
    if args.command == "land" and args.legacy_root is None:
        args.legacy_root = "."
    try:
        dbx = Databricks()
        return {
            "provision-check": cmd_provision_check,
            "land": cmd_land,
            "seed-fixture": cmd_seed_fixture,
            "run-job": cmd_run_job,
            "verify-trigger": cmd_verify_trigger,
            "wipe": cmd_wipe,
        }[args.command](dbx, args)
    except DbxError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
