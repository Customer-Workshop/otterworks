#!/usr/bin/env python3
"""Convert etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh to a silver load
with declared expectations (contract
docs/tech-partnerships/contracts/parse_custbill_fixedwidth.json).

Namespace-scoped (`--ns`) and `ow_tp`-prefixed like scripts/tp_dbx/showcase.py:
the workspace is shared, so nothing here touches an object outside its own
namespace suffix and all compute is the existing serverless SQL warehouse.

  provision     bronze/silver/quarantine/expectations/parse_runs tables
  expectations  load the declared expectations into ow_tp.ops.parse_expectations_<ns>
  land          upload a feed (seed = clean CUSTBILL drops, history = 2019-2024)
  parse         bronze load + expectation-driven silver/quarantine/parse_runs
  gate          run the trailer-reconciliation gate (fails on mismatch, PRS-04)
  grade-seed    compare silver against the golden legacy .psv output (PRS-03)
  grade-history set-compare the quarantine against the history manifest (PRS-06)
  recon         run every acceptance check and write the schema-valid recon report
  job           create/refresh the (unscheduled) Databricks job ow_tp_parse_<ns>
  run-job       trigger the job and report the outcome
  status        summarise the namespace state
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import parse_sql as P
from client import Databricks, DbxError, require_ident, require_ns

REPO = Path(__file__).resolve().parents[2]
NOTEBOOK_DIR = "/Shared/ow_tp"
UNIT = "parse_custbill_fixedwidth"


def names(args) -> P.ParseNames:
    return P.ParseNames(catalog=require_ident(args.catalog, "catalog"), ns=require_ns(args.ns))


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_expectations(dbx: Databricks, n: P.ParseNames) -> tuple[list[dict], dict]:
    """The parse SQL is generated from the expectations table, not from the
    constant that seeded it: the table is the declaration of record."""
    rows = dbx.sql_ok(
        f"SELECT expectation_id, scope, field, reason_class, violation_predicate, priority "
        f"FROM {n.expectations} ORDER BY priority"
    ).dicts()
    if not rows:
        raise SystemExit(f"{n.expectations} is empty; run `expectations` first")
    record = [r for r in rows if r["scope"] == "record"]
    file_scope = [r for r in rows if r["scope"] == "file"]
    if len(file_scope) != 1:
        raise SystemExit(f"expected exactly one file-scope expectation, found {len(file_scope)}")
    return record, file_scope[0]


def manifest_path(args) -> Path:
    return Path(args.legacy_root) / "sftp-drop/history/expected" / f"{args.source_ns}-history-expected.json"


def load_manifest(args) -> dict:
    path = manifest_path(args)
    if not path.exists():
        raise SystemExit(f"history manifest not found: {path}\n"
                         f"  generate it first: make legacy-etl-gen-history NS={args.source_ns}")
    return json.loads(path.read_text())


# --- commands ----------------------------------------------------------------
def cmd_provision(dbx: Databricks, args) -> int:
    n = names(args)
    for statement in P.provision(n):
        dbx.sql_ok(statement)
    print(f"provisioned {UNIT} tables for ns={n.ns}")
    return 0


def cmd_expectations(dbx: Databricks, args) -> int:
    n = names(args)
    dbx.sql_ok(P.load_expectations(n))
    rows = dbx.sql_ok(f"SELECT count(*) FROM {n.expectations}").scalar()
    print(f"declared {rows} expectations in {n.expectations}")
    return 0


def cmd_land(dbx: Databricks, args) -> int:
    n = names(args)
    root = Path(args.legacy_root)
    if args.feed == "seed":
        # scope to this namespace's drops: every namespace stages into the same
        # legacy root, so an unscoped glob would mix in a sibling demo's files
        pattern = f"incoming/CUSTBILL_{args.source_ns.upper()}_*.dat"
        candidates = sorted(root.glob(pattern)) or [
            p.with_suffix("") for p in sorted(root.glob(pattern + ".done"))
        ]
        files = []
        for path in candidates:
            done = Path(str(path) + ".done")
            files.append(done if not path.exists() and done.exists() else path)
        files = [p for p in files if p.exists()]
        targets = [f"{n.feed_dir}/seed/{p.name.removesuffix('.done')}" for p in files]
    else:
        files = sorted(p for p in (root / "sftp-drop/history").rglob(f"CUSTBILL_{args.source_ns.upper()}_*.dat") if p.is_file())
        targets = [f"{n.feed_dir}/history/{p.parent.name}/{p.name}" for p in files]
    if not files:
        raise SystemExit(f"no CUSTBILL files found for feed={args.feed} under {root}")
    entries = []
    for path, target in zip(files, targets):
        payload = path.read_bytes()
        dbx.put_file(target, payload)
        name = target.rsplit("/", 1)[-1]
        period_match = re.search(r"CUSTBILL_[A-Z0-9_-]+_([0-9]{6})\.dat$", name)
        period = period_match.group(1) if period_match else None
        entries.append((name, period, int(period[:4]) if period else None, len(payload)))
    for statement in P.register_files(n, args.feed, entries):
        dbx.sql_ok(statement)
    print(f"landed and registered {len(files)} file(s) under {n.feed_dir}/{args.feed}")
    return 0


def _run_parse(dbx: Databricks, n: P.ParseNames, feeds: list[str], reload_bronze: bool) -> None:
    record, file_exp = read_expectations(dbx, n)
    if reload_bronze:
        for feed in feeds:
            path = f"{n.feed_dir}/{feed}"
            for statement in P.load_bronze(n, feed, path, replace_feed=True):
                dbx.sql_ok(statement)
    broken = dbx.sql_ok(P.line_number_invariant(n)).dicts()
    if broken:
        first = broken[0]
        raise SystemExit(
            f"PARSE FAILED: bronze line numbering invariant violated for file "
            f"{first['source_file']} (hdr_line={first['hdr_line']}, trl_line={first['trl_line']}, "
            f"last_line={first['last_line']}); refusing to parse on unverified offsets"
        )
    dbx.sql_ok(P.build_silver(n, record))
    dbx.sql_ok(P.build_quarantine(n, record, file_exp))
    dbx.sql_ok(P.build_parse_runs(n, file_exp))


def cmd_parse(dbx: Databricks, args) -> int:
    n = names(args)
    feeds = args.feeds.split(",")
    _run_parse(dbx, n, feeds, reload_bronze=not args.no_reload)
    summary = dbx.sql_ok(
        f"SELECT (SELECT count(*) FROM {n.bronze}) AS bronze_lines, "
        f"(SELECT count(DISTINCT source_file) FROM {n.bronze}) AS files, "
        f"(SELECT count(*) FROM {n.silver}) AS silver_rows, "
        f"(SELECT count(*) FROM {n.quarantine}) AS quarantined, "
        f"(SELECT count_if(status = 'failed') FROM {n.parse_runs}) AS failed_files"
    )
    print(json.dumps(summary.dicts()[0], indent=2))
    return 0


def cmd_gate(dbx: Databricks, args) -> int:
    n = names(args)
    result = dbx.sql(P.parse_gate(n))
    if result.ok:
        print(result.scalar())
        return 0
    print(f"gate failed (as designed on trailer mismatch): {result.error[:600]}")
    return 1


def _psv_rows_from_silver(dbx: Databricks, n: P.ParseNames) -> dict[str, list[str]]:
    rows = dbx.sql_ok(
        f"SELECT source_file, record_offset, concat_ws('|', cust_id, cust_name, "
        f"date_format(bill_date, 'yyyy-MM-dd'), CAST(amount AS STRING), currency, record_type) AS line "
        f"FROM {n.silver} WHERE source_feed = 'seed' ORDER BY source_file, record_offset"
    ).dicts()
    out: dict[str, list[str]] = {}
    for row in rows:
        out.setdefault(row["source_file"], []).append(row["line"])
    return out


def grade_seed(dbx: Databricks, args, n: P.ParseNames) -> dict:
    golden_dir = Path(args.legacy_root) / "parsed"
    golden = {p.name.replace(".psv", ".dat"): p.read_text().splitlines()
              for p in sorted(golden_dir.glob(f"CUSTBILL_{args.source_ns.upper()}_*.psv"))}
    if not golden:
        raise SystemExit(f"no golden .psv files under {golden_dir}; run the legacy chain first")
    actual = _psv_rows_from_silver(dbx, n)
    total = matched = extra_rows = 0
    mismatches: list[str] = []
    for fname, lines in golden.items():
        got = actual.pop(fname, [])
        total += len(lines)
        if lines == got:
            matched += len(lines)
            continue
        for i, (g, a) in enumerate(zip(lines, got + [""] * len(lines))):
            if g == a:
                matched += 1
            elif len(mismatches) < 5:
                mismatches.append(f"{fname}:{i + 1} golden={g!r} silver={a!r}")
        if len(got) > len(lines):
            extra_rows += len(got) - len(lines)
            mismatches.append(f"{fname}: {len(got) - len(lines)} silver row(s) beyond the golden output")
    for fname, got in actual.items():  # silver-only files: no golden counterpart at all
        extra_rows += len(got)
        mismatches.append(f"{fname}: {len(got)} silver row(s) with no golden .psv counterpart")
    quarantined = dbx.sql_ok(
        f"SELECT count(*) FROM {n.quarantine} WHERE source_feed = 'seed'").scalar()
    return {"golden_rows": total, "matched_rows": matched, "extra_silver_rows": extra_rows,
            "seed_quarantined": int(quarantined), "mismatches": mismatches}


def cmd_grade_seed(dbx: Databricks, args) -> int:
    result = grade_seed(dbx, args, names(args))
    print(json.dumps(result, indent=2))
    ok = (result["matched_rows"] == result["golden_rows"]
          and result["extra_silver_rows"] == 0 and result["seed_quarantined"] == 0)
    return 0 if ok else 1


def grade_history(dbx: Databricks, args, n: P.ParseNames) -> dict:
    data = load_manifest(args)
    expected = sorted([a["file"], a["kind"], a["cust_id"]] for a in data["planted_anomalies"])
    actual_rows = dbx.sql_ok(
        f"SELECT source_file, reason_class, cust_id, record_offset FROM {n.quarantine} "
        f"WHERE source_feed = 'history' ORDER BY source_file, reason_class, cust_id"
    ).dicts()
    actual = sorted([r["source_file"], r["reason_class"], r["cust_id"]] for r in actual_rows)
    expected_keys = {tuple(e) for e in expected}
    actual_keys = {tuple(a) for a in actual}
    # record offsets: the manifest's row r is body row r, physical line r+1 (HDR is line 1)
    offset_index = {(a["file"], a["cust_id"]): a["row"] + 1
                    for a in data["planted_anomalies"] if a["row"] > 0}
    offset_mismatches = [
        f"{r['source_file']}/{r['cust_id']}: expected line {offset_index[(r['source_file'], r['cust_id'])]}, got {r['record_offset']}"
        for r in actual_rows
        if (r["source_file"], r["cust_id"]) in offset_index
        and int(r["record_offset"]) != offset_index[(r["source_file"], r["cust_id"])]
    ]
    totals = dbx.sql_ok(
        f"SELECT source_year, currency, record_type, count(*) AS record_count, "
        f"sum(amount_cents) AS total_cents FROM {n.silver} WHERE source_feed = 'history' "
        f"GROUP BY source_year, currency, record_type"
    ).dicts()
    actual_totals = {(int(t["source_year"]), t["currency"], t["record_type"]):
                     (int(t["record_count"]), int(t["total_cents"])) for t in totals}
    total_mismatches = []
    for block in data["per_year"]:
        for t in block["totals"]:
            key = (block["year"], t["currency"], t["record_type"])
            want = (t["record_count"], t["total_amount_cents"])
            if actual_totals.get(key) != want:
                total_mismatches.append(f"{key}: manifest={want} silver={actual_totals.get(key)}")
    return {
        "expected_set": expected, "actual_set": actual,
        "missing": sorted(list(k) for k in expected_keys - actual_keys),
        "unexpected": sorted(list(k) for k in actual_keys - expected_keys),
        "offset_mismatches": offset_mismatches,
        "per_year_total_mismatches": total_mismatches,
    }


def cmd_grade_history(dbx: Databricks, args) -> int:
    result = grade_history(dbx, args, names(args))
    print(json.dumps({k: v for k, v in result.items() if k not in ("expected_set", "actual_set")}, indent=2))
    print(f"expected {len(result['expected_set'])} anomalies, quarantined {len(result['actual_set'])}")
    ok = not (result["missing"] or result["unexpected"]
              or result["offset_mismatches"] or result["per_year_total_mismatches"])
    return 0 if ok else 1


def _counts(dbx: Databricks, n: P.ParseNames) -> dict:
    return dbx.sql_ok(
        f"SELECT (SELECT count(*) FROM {n.silver}) AS silver_rows, "
        f"(SELECT sum(amount_cents) FROM {n.silver}) AS silver_cents, "
        f"(SELECT count(*) FROM {n.quarantine}) AS quarantined, "
        f"(SELECT count(*) FROM {n.parse_runs}) AS files, "
        f"(SELECT count_if(status = 'failed') FROM {n.parse_runs}) AS failed_files"
    ).dicts()[0]


def cmd_recon(dbx: Databricks, args) -> int:
    n = names(args)
    data = load_manifest(args)
    checks: list[dict] = []

    def check(check_id: str, expected, actual, source: str) -> None:
        checks.append({"id": check_id, "expected": expected, "actual": actual,
                       "source_of_truth": source,
                       "result": "pass" if expected == actual else "fail"})

    # PRS-01: layout fidelity — every bronze BODY line is exactly one silver or
    # quarantined record; HDR/TRL never reach the record set.
    coverage = dbx.sql_ok(
        f"SELECT (SELECT count(*) FROM {n.bronze} WHERE record_kind = 'BODY') AS body_lines, "
        f"(SELECT count(*) FROM {n.silver}) AS silver_rows, "
        f"(SELECT count(*) FROM {n.quarantine} WHERE record_offset > 0) AS record_quarantined, "
        f"(SELECT count(*) FROM {n.silver} s JOIN {n.bronze} b ON s.source_file = b.source_file "
        f" AND s.record_offset = b.line_no WHERE b.record_kind <> 'BODY') AS hdr_trl_in_silver"
    ).dicts()[0]
    body = int(coverage["body_lines"])
    check("PRS-01",
          {"body_lines": body, "silver_plus_quarantined": body, "hdr_trl_in_silver": 0},
          {"body_lines": body,
           "silver_plus_quarantined": int(coverage["silver_rows"]) + int(coverage["record_quarantined"]),
           "hdr_trl_in_silver": int(coverage["hdr_trl_in_silver"])},
          f"{n.bronze} line inventory vs {n.silver}/{n.quarantine}")

    # PRS-02: typed columns.
    schema = {r["col_name"]: r["data_type"] for r in dbx.sql_ok(
        f"DESCRIBE TABLE {n.silver}").dicts() if r.get("col_name")}
    classes = [r["record_class"] for r in dbx.sql_ok(
        f"SELECT DISTINCT record_class FROM {n.silver} ORDER BY record_class").dicts()]
    check("PRS-02",
          {"amount": "decimal(12,2)", "bill_date": "date", "amount_cents": "bigint",
           "record_classes": ["CREDIT", "INVOICE"]},
          {"amount": schema.get("amount"), "bill_date": schema.get("bill_date"),
           "amount_cents": schema.get("amount_cents"), "record_classes": classes},
          f"DESCRIBE TABLE {n.silver} and distinct record_class values")

    # PRS-03: row parity against the golden .psv for the clean seed.
    seed = grade_seed(dbx, args, n)
    check("PRS-03",
          {"golden_rows": seed["golden_rows"], "matched_rows": seed["golden_rows"],
           "extra_silver_rows": 0, "seed_quarantined": 0},
          {"golden_rows": seed["golden_rows"], "matched_rows": seed["matched_rows"],
           "extra_silver_rows": seed["extra_silver_rows"], "seed_quarantined": seed["seed_quarantined"]},
          "golden .psv from a real legacy run (sha256-pinned in the unit contract)")

    # PRS-04: trailer reconciliation enforced — the manifest's mismatched files
    # are failed and the gate raises.
    expected_failed = sorted(f["file"] for f in data["files"] if not f["trailer_matches"])
    actual_failed = sorted(r["source_file"] for r in dbx.sql_ok(
        f"SELECT source_file FROM {n.parse_runs} WHERE status = 'failed'").dicts())
    gate = dbx.sql(P.parse_gate(n))
    gate_enforced = (not gate.ok) and "trailer_count_mismatch" in gate.error
    check("PRS-04",
          {"failed_files": expected_failed, "gate_fails_run": True},
          {"failed_files": actual_failed, "gate_fails_run": gate_enforced},
          "history manifest trailer_matches flags; parse_gate raise_error on the warehouse")

    # PRS-05: expectations live as data and every quarantined row carries its
    # expectation id and raw source line.
    declared = dbx.sql_ok(
        f"SELECT expectation_id FROM {n.expectations} ORDER BY priority").dicts()
    unattributed = int(dbx.sql_ok(
        f"SELECT count(*) FROM {n.quarantine} WHERE expectation_id IS NULL "
        f"OR raw_line IS NULL OR expectation_id NOT IN "
        f"(SELECT expectation_id FROM {n.expectations})").scalar())
    check("PRS-05",
          {"declared_expectations": [e[0] for e in P.EXPECTATIONS], "unattributed_quarantine_rows": 0},
          {"declared_expectations": [d["expectation_id"] for d in declared],
           "unattributed_quarantine_rows": unattributed},
          f"{n.expectations} contents; quarantine attribution join")

    # PRS-06: malformed-record coverage, exact set equality both directions.
    history = grade_history(dbx, args, n)
    check("PRS-06",
          {"expected_anomalies": len(history["expected_set"]), "missing": [], "unexpected": [],
           "offset_mismatches": [], "per_year_total_mismatches": []},
          {"expected_anomalies": len(history["actual_set"]), "missing": history["missing"],
           "unexpected": history["unexpected"], "offset_mismatches": history["offset_mismatches"],
           "per_year_total_mismatches": history["per_year_total_mismatches"]},
          "history manifest planted_anomalies and per_year totals (sha256-pinned)")

    # PRS-07: idempotency, proven by an actual re-parse with Delta history.
    before = _counts(dbx, n)
    versions_before = int(dbx.sql_ok(
        f"SELECT max(version) FROM (DESCRIBE HISTORY {n.silver})").scalar())
    _run_parse(dbx, n, args.feeds.split(","), reload_bronze=False)
    after = _counts(dbx, n)
    versions_after = int(dbx.sql_ok(
        f"SELECT max(version) FROM (DESCRIBE HISTORY {n.silver})").scalar())
    idempotent = before == after and versions_after > versions_before
    check("PRS-07",
          {"counts_unchanged": True, "new_delta_version_written": True},
          {"counts_unchanged": before == after, "new_delta_version_written": versions_after > versions_before},
          f"counts/totals before vs after re-parse; DESCRIBE HISTORY {n.silver} "
          f"(v{versions_before} -> v{versions_after})")

    # PRS-08: no orphaned temp state, no blanket suppression — failures raise
    # naming the file; the landing volume holds only the landed feeds.
    landing_entries = [e.get("path", "") for e in dbx.list_dir(n.feed_dir)]
    stray = [p for p in landing_entries if not p.rstrip("/").endswith(("seed", "history"))]
    invariant_rows = dbx.sql_ok(P.line_number_invariant(n)).dicts()
    gate_names_file = (not gate.ok) and any(f in gate.error for f in expected_failed)
    check("PRS-08",
          {"stray_landing_paths": [], "line_invariant_violations": 0, "failure_names_file": True},
          {"stray_landing_paths": stray, "line_invariant_violations": len(invariant_rows),
           "failure_names_file": gate_names_file},
          "Files API listing of the feed dir; line-number invariant query; gate error text")

    report = {
        "kind": "recon-report",
        "unit": UNIT,
        "namespace": n.ns,
        "generated_at": now(),
        "run_mode": args.run_mode,
        "checks": checks,
        "values_recomputed_from_target": True,
        "idempotency_rerun": {
            "performed": True,
            "result": "pass" if idempotent else "fail",
            "evidence": (f"silver/quarantine/parse_runs rebuilt from bronze; counts and cent totals "
                         f"identical ({before}); silver Delta history advanced v{versions_before} -> "
                         f"v{versions_after} (INSERT OVERWRITE, replace not append)"),
        },
        "planted_anomaly_detections": {
            "expected_set": history["expected_set"],
            "actual_set": history["actual_set"],
            "missing": history["missing"],
            "unexpected": history["unexpected"],
        },
        "unverified_paths": [
            "undecodable_bytes (EXP-ENC) and unknown_currency/unknown_record_type (EXP-CCY/EXP-RT) "
            "quarantine paths: declared and generated into the parse SQL, but neither graded input "
            "plants such records, so they were not exercised against real defects",
            "hex retention of undecodable raw bytes: bronze stores the line as decoded by "
            "read_files(text); a genuinely undecodable byte sequence was not exercised",
        ],
        "contract_decisions": [
            "PRS-04 'quarantines its records' vs the manifest declaring the trailer-mismatched "
            "files' body records valid (they are counted in per_year totals and absent from "
            "planted_anomalies): resolved in favour of the manifest and PRS-06 exact set "
            "equality - the file fails (parse_runs status=failed, gate raises), a file-scope "
            "quarantine row with reason trailer_count_mismatch and the raw TRL line is written, "
            "and structurally-valid body records of that file remain in silver",
        ],
    }
    out = Path(args.out) if args.out else REPO / f"docs/tech-partnerships/recon/{UNIT}-{n.ns}.recon.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")
    failed = [c for c in checks if c["result"] == "fail"]
    print(f"wrote {out}")
    print(f"checks: {len(checks)}, failed: {len(failed)}")
    for c in failed:
        print(f"  FAIL {c['id']} expected={c['expected']} actual={c['actual']}")
    return 1 if failed or not idempotent else 0


def cmd_job(dbx: Databricks, args) -> int:
    n = names(args)
    record, file_exp = read_expectations(dbx, n)
    build_sql = ";\n\n".join([
        P.line_number_gate(n),  # same refusal the CLI path enforces
        P.build_silver(n, record),
        P.build_quarantine(n, record, file_exp),
        P.build_parse_runs(n, file_exp),
    ]) + ";\n"
    header = ("-- Generated by scripts/tp_dbx/parse_custbill.py `job` from the rows of\n"
              f"-- {n.expectations} (the declaration of record); edit the table, then redeploy.\n")
    dbx.ok("POST", "/api/2.0/workspace/mkdirs", {"path": NOTEBOOK_DIR})
    for name, text in ((f"parse_custbill_build_{n.ns}.sql", header + build_sql),
                       (f"parse_custbill_gate_{n.ns}.sql", header + P.parse_gate(n) + ";\n")):
        dbx.ok("POST", "/api/2.0/workspace/import", {
            "path": f"{NOTEBOOK_DIR}/{name}", "format": "AUTO", "overwrite": True,
            "content": base64.b64encode(text.encode()).decode(),
        })
    settings = {
        "name": f"ow_tp_parse_{n.ns}",
        "tags": {"project": "otterworks-tp", "unit": UNIT, "namespace": n.ns},
        "max_concurrent_runs": 1,
        "tasks": [
            {
                "task_key": "parse_build",
                "sql_task": {
                    "warehouse_id": dbx.warehouse_id,
                    "file": {"path": f"{NOTEBOOK_DIR}/parse_custbill_build_{n.ns}.sql", "source": "WORKSPACE"},
                },
            },
            {
                "task_key": "trailer_gate",
                "depends_on": [{"task_key": "parse_build"}],
                "sql_task": {
                    "warehouse_id": dbx.warehouse_id,
                    "file": {"path": f"{NOTEBOOK_DIR}/parse_custbill_gate_{n.ns}.sql", "source": "WORKSPACE"},
                },
            },
        ],
        # no schedule at all: nothing in this namespace runs unattended
        "queue": {"enabled": True},
    }
    job_id = dbx.upsert_job(settings)
    print(f"job {job_id} (no schedule): {dbx.host}/jobs/{job_id}")
    return 0


def cmd_run_job(dbx: Databricks, args) -> int:
    n = names(args)
    job = dbx.find_job(f"ow_tp_parse_{n.ns}")
    if not job:
        raise SystemExit(f"job ow_tp_parse_{n.ns} not found; run `job` first")
    run_id = dbx.run_job(int(job["job_id"]))
    print(f"triggered run: {dbx.run_url(run_id)}")
    run = dbx.wait_run(run_id)
    state = run.get("state", {})
    print(f"result: {state.get('result_state')} — {str(state.get('state_message'))[:400]}")
    for task in run.get("tasks", []):
        print(f"  task {task['task_key']}: {task.get('state', {}).get('result_state')}")
    return 0 if state.get("result_state") == "SUCCESS" else 1


def cmd_status(dbx: Databricks, args) -> int:
    n = names(args)
    result = dbx.sql(
        f"SELECT (SELECT count(*) FROM {n.bronze}) AS bronze_lines, "
        f"(SELECT count(DISTINCT source_file) FROM {n.bronze}) AS files, "
        f"(SELECT count(*) FROM {n.silver}) AS silver_rows, "
        f"(SELECT count(*) FROM {n.quarantine}) AS quarantined, "
        f"(SELECT count(*) FROM {n.expectations}) AS expectations, "
        f"(SELECT count_if(status = 'failed') FROM {n.parse_runs}) AS failed_files"
    )
    print(json.dumps(result.dicts()[0] if result.ok else {"state": result.state, "error": result.error}, indent=2))
    job = dbx.find_job(f"ow_tp_parse_{n.ns}")
    print(f"job: {dbx.host}/jobs/{job['job_id']}" if job else "job: absent")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=[
        "provision", "expectations", "land", "parse", "gate", "grade-seed",
        "grade-history", "recon", "job", "run-job", "status"])
    parser.add_argument("--ns", default="w2parse")
    parser.add_argument("--catalog", default="ow_tp")
    parser.add_argument("--warehouse-id", default="")
    parser.add_argument("--legacy-root",
                        default=os.environ.get("OTTERWORKS_LEGACY_ROOT", "/tmp/otterworks-legacy"))
    parser.add_argument("--source-ns", default="demo",
                        help="namespace the legacy generator produced the drops under")
    parser.add_argument("--feed", choices=["seed", "history"], default="seed")
    parser.add_argument("--feeds", default="seed,history",
                        help="comma-separated feeds parse/recon operate over")
    parser.add_argument("--no-reload", action="store_true",
                        help="parse without reloading bronze from the landing volume")
    parser.add_argument("--run-mode", choices=["live", "fixture"], default="live")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    dbx = Databricks(warehouse_id=args.warehouse_id or None)
    commands = {
        "provision": cmd_provision, "expectations": cmd_expectations, "land": cmd_land,
        "parse": cmd_parse, "gate": cmd_gate, "grade-seed": cmd_grade_seed,
        "grade-history": cmd_grade_history, "recon": cmd_recon, "job": cmd_job,
        "run-job": cmd_run_job, "status": cmd_status,
    }
    try:
        return commands[args.command](dbx, args)
    except DbxError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
