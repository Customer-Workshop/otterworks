#!/usr/bin/env python3
"""Reconciliation harness for the P-B CUSTBILL units (parent-owned, wave 0).

Compares what the converted Databricks jobs wrote for one namespace against
the deterministic legacy outputs regenerated under OTTERWORKS_LEGACY_ROOT
(see each unit's contract, `golden_baseline_location`). Every value on the
target side is recomputed from ow_tp tables / volume files at run time; every
value on the legacy side is read from the legacy files, never from a document.

Idempotency requires a first-pass snapshot followed by a no-input job rerun and a second invocation with `--previous <snapshot>` that compares fingerprints and proves a newer successful run.

Usage:
  recon_custbill.py --unit sftp_ingest_poll --ns demo --legacy-root ~/otterworks-legacy-demo --run-mode live
  recon_custbill.py --unit parse_custbill_fixedwidth --ns parse-w2 --legacy-root ... \
      --anomaly-ns parse-w2-anom --anomaly-root ~/otterworks-legacy-anom --run-mode live
  ... second run ...  --previous docs/tech-partnerships/recon/<unit>.recon.first-pass.json
"""
from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import io
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from client import Databricks, DbxError, require_custbill_ns  # noqa: E402

CATALOG = "ow_tp"
UNITS = ("sftp_ingest_poll", "parse_custbill_fixedwidth", "finance_excel_report", "custbill_workflow")
REPORT_DIR = Path(__file__).resolve().parents[2] / "docs/tech-partnerships/recon"
JOB_NAME = "ow_tp_custbill"
RUN_LOOKBACK_MS = 30 * 24 * 3600 * 1000
REQUIRED = {
    "sftp_ingest_poll": {"U6-a", "U6-b", "U6-c", "U6-e"},
    "parse_custbill_fixedwidth": {"U7-a", "U7-b", "U7-c", "U7-d", "U7-e"},
    "finance_excel_report": {"U8-a", "U8-b", "U8-c", "U8-e", "U8-f"},
    "custbill_workflow": {
        "U9-a", "U9-c",
        "U9-b/U6-a", "U9-b/U6-b", "U9-b/U7-a", "U9-b/U7-b",
        "U9-b/U7-c", "U9-b/U8-a", "U9-b/U8-b",
    },
}


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def content_fingerprint(rows: list[str]) -> str:
    return sha256("\n".join(rows).encode())


def idempotency_result(
    same: bool,
    wrote_rows: bool,
    prev_run: dict | None,
    cur_run: dict | None,
    snapshot_time_ms: int,
) -> tuple[str, str]:
    if not same:
        return "fail", "fingerprints differ"
    if not wrote_rows:
        return "fail", "first pass did not write rows"
    if cur_run is None:
        return "fail", "no newer successful ow_tp_custbill run since first pass"
    if cur_run.get("result_state") != "SUCCESS":
        return "fail", "latest matching ow_tp_custbill run did not succeed"
    if cur_run.get("end_time", 0) <= snapshot_time_ms:
        return "fail", "latest successful run ended before the first-pass snapshot"
    if prev_run is not None and cur_run.get("end_time", 0) <= prev_run.get("end_time", 0):
        return "fail", "no newer successful ow_tp_custbill run since first pass"
    return "pass", "newer successful ow_tp_custbill run confirmed"


def verdict(unit: str, checks: list[dict], idem_result: str | None, waived: set[str]) -> list[str]:
    required = REQUIRED[unit]
    by_id = {check["id"]: check for check in checks}
    failures = [check["id"] for check in checks if check["result"] == "fail"]
    for check_id in sorted(required):
        if check_id in waived:
            continue
        check = by_id.get(check_id)
        if check is None:
            failures.append(f"{check_id} (missing)")
        elif check["result"] == "skipped":
            failures.append(f"{check_id} (skipped, not waived)")
    if idem_result == "fail":
        failures.append("idempotency")
    return failures


def q(s: str) -> str:
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def landing(ns: str) -> str:
    return f"/Volumes/{CATALOG}/bronze/landing/{ns}"


class Recon:
    def __init__(self, dbx: Databricks, ns: str, legacy_root: Path):
        self.dbx = dbx
        self.ns = ns
        self.root = legacy_root
        self.checks: list[dict] = []
        self.fingerprint: dict = {}
        self.anomaly = {"expected_set": [], "actual_set": [], "missing": [], "unexpected": []}
        self.unverified: list[str] = []

    # -- helpers --------------------------------------------------------------
    def rows(self, sql: str) -> list[list]:
        r = self.dbx.sql(sql)
        if not r.ok:
            raise DbxError(f"SQL failed: {r.message}\n{sql}")
        return r.rows

    def check(self, cid: str, expected, actual, truth: str, ok: bool | None = None) -> bool:
        passed = (expected == actual) if ok is None else ok
        self.checks.append({
            "id": cid, "expected": expected, "actual": actual,
            "source_of_truth": truth, "result": "pass" if passed else "fail",
        })
        return passed

    def skipped(self, cid: str, why: str, truth: str) -> None:
        self.checks.append({"id": cid, "expected": "n/a", "actual": why,
                            "source_of_truth": truth, "result": "skipped"})
        self.unverified.append(f"{cid}: {why}")

    def latest_run_for_ns(self, start_time_from_ms: int | None) -> dict | None:
        job = self.dbx.find_job(JOB_NAME)
        if not job:
            return None
        matching: list[dict] = []
        for summary in self.dbx.list_runs(int(job["job_id"]), start_time_from_ms):
            run_id = summary.get("run_id")
            if run_id is None:
                continue
            run = self.dbx.get_run(int(run_id))
            params = run.get("job_parameters")
            run_ns = None
            if isinstance(params, list):
                run_ns = next(
                    (item.get("value") for item in params
                     if isinstance(item, dict) and item.get("name") == "ns"),
                    None,
                )
            if run_ns is None:
                job_params = run.get("overriding_parameters", {}).get("job_parameters", {})
                if isinstance(job_params, dict):
                    run_ns = job_params.get("ns")
            if run_ns != self.ns:
                continue
            state = run.get("state", {})
            if state.get("result_state") != "SUCCESS":
                continue
            matching.append({
                "run_id": int(run["run_id"]),
                "end_time": int(run.get("end_time", 0)),
                "result_state": state["result_state"],
            })
        return max(matching, key=lambda item: item["end_time"]) if matching else None

    def legacy_dats(self) -> list[Path]:
        files = sorted(Path(p) for p in glob.glob(str(self.root / "incoming" / "CUSTBILL*.dat*")))
        # legacy parse renames incoming/X.dat -> X.dat.done; either is the same bytes
        seen: dict[str, Path] = {}
        for f in files:
            base = f.name[: f.name.index(".dat") + 4]
            seen.setdefault(base, f)
        if not seen:
            for f in sorted(Path(p) for p in glob.glob(str(self.root / "sftp-drop/upload/CUSTBILL*.dat"))):
                seen.setdefault(f.name, f)
        return [seen[k] for k in sorted(seen)]

    # -- U6 -------------------------------------------------------------------
    def unit_ingest(self) -> None:
        dats = self.legacy_dats()
        if not dats:
            raise SystemExit(f"no legacy CUSTBILL*.dat under {self.root}/incoming or sftp-drop/upload")
        archive = {e["name"]: e for e in self.dbx.list_dir(f"{landing(self.ns)}/archive")}
        incoming = {e["name"] for e in self.dbx.list_dir(f"{landing(self.ns)}/incoming")}
        a_exp, a_act, b_exp, b_act, c_exp, c_act = [], [], [], [], [], []
        for path in dats:
            base = path.name[: path.name.index(".dat") + 4]
            raw = path.read_bytes()
            digest = sha256(raw)
            a_exp.append({"file": base, "bytes": len(raw), "sha256": digest})
            arch_name = f"{base}.{digest[:12]}"
            if arch_name in archive:
                blob = self.dbx.get_file(f"{landing(self.ns)}/archive/{arch_name}")
                a_act.append({"file": base, "bytes": len(blob), "sha256": sha256(blob)})
            else:
                a_act.append({"file": base, "bytes": None, "sha256": f"archive {arch_name} missing"})
            lines = raw.split(b"\n")
            if lines and lines[-1] == b"":
                lines.pop()
            kinds = {"HDR": 0, "TRL": 0, "BODY": 0}
            for ln in lines:
                kinds["HDR" if ln.startswith(b"HDR") else "TRL" if ln.startswith(b"TRL") else "BODY"] += 1
            b_exp.append({"file": base, "lines": len(lines), **kinds})
            got = self.rows(
                f"SELECT record_kind, count(*) FROM {CATALOG}.bronze.custbill_raw "
                f"WHERE ns={q(self.ns)} AND source_file={q(base)} GROUP BY record_kind")
            k = {"HDR": 0, "TRL": 0, "BODY": 0}
            for kind, n in got:
                k[kind] = int(n)
            b_act.append({"file": base, "lines": sum(k.values()), **k})
            c_exp.append({"file": base, "sha256": digest})
            recon = self.rows(
                f"SELECT raw_line FROM {CATALOG}.bronze.custbill_raw WHERE ns={q(self.ns)} "
                f"AND source_file={q(base)} ORDER BY line_no")
            rebuilt = b"".join((r[0] or "").encode("latin-1") + b"\n" for r in recon)
            c_act.append({"file": base, "sha256": sha256(rebuilt) if recon else "no rows"})
        self.check("U6-a", a_exp, a_act, "legacy incoming/*.dat bytes vs volume archive/<file>.<sha12> bytes")
        self.check("U6-b", b_exp, b_act, "wc -l / prefix classification of legacy file vs bronze record_kind counts")
        self.check("U6-c", c_exp, c_act, "sha256(legacy file) vs sha256(concat bronze raw_line ORDER BY line_no)")
        leftovers = sorted(n for n in incoming if any(n.startswith(d["file"]) for d in a_exp))
        self.check("U6-e", [], leftovers, "volume incoming/ listing after run: processed files must be gone")
        self.fingerprint["bronze_rows"] = b_act
        self.fingerprint["bronze_content"] = c_act
        self.fingerprint["archive"] = a_act

    # -- U7 -------------------------------------------------------------------
    def legacy_psv_rows(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for p in sorted(glob.glob(str(self.root / "parsed" / "CUSTBILL*.psv"))):
            base = Path(p).name[:-4] + ".dat"
            out[base] = [ln for ln in Path(p).read_text(encoding="latin-1").split("\n") if ln != ""]
        return out

    def unit_parse(self, anomaly_ns: str | None, anomaly_root: Path | None) -> None:
        legacy = self.legacy_psv_rows()
        if not legacy:
            raise SystemExit(f"no legacy parsed/CUSTBILL*.psv under {self.root}")
        exp_counts = {f: len(v) for f, v in legacy.items()}
        got = self.rows(f"SELECT source_file, count(*) FROM {CATALOG}.silver.custbill_records "
                        f"WHERE ns={q(self.ns)} GROUP BY source_file")
        act_counts = {f: int(n) for f, n in got}
        silver_content: list[str] = []
        self.check("U7-a", {"total": sum(exp_counts.values()), "per_file": exp_counts},
                   {"total": sum(act_counts.values()), "per_file": act_counts},
                   "wc -l parsed/*.psv vs count(*) silver per source_file")
        mismatches: list[dict] = []
        compared = 0
        for base, lines in legacy.items():
            rows = self.rows(
                f"SELECT cust_id, cust_name, date_format(bill_date,'yyyy-MM-dd'), "
                f"format_number(bill_amt, '0.00'), currency, rec_type "
                f"FROM {CATALOG}.silver.custbill_records WHERE ns={q(self.ns)} AND source_file={q(base)} "
                f"ORDER BY line_no")
            target = ["|".join("" if c is None else str(c) for c in r) for r in rows]
            silver_content.extend(target)
            for i in range(max(len(lines), len(target))):
                compared += 1
                le = lines[i] if i < len(lines) else "<missing>"
                ta = target[i] if i < len(target) else "<missing>"
                if le != ta and len(mismatches) < 25:
                    mismatches.append({"file": base, "row": i + 1, "legacy": le, "target": ta})
                elif le != ta:
                    mismatches.append({"file": base, "row": i + 1, "legacy": "...", "target": "..."})
                    break
        self.check("U7-b", {"rows_compared": compared, "mismatches": []},
                   {"rows_compared": compared, "mismatches": mismatches},
                   "full row diff: legacy .psv line i vs silver row i (ORDER BY line_no), 6 fields", ok=not mismatches)
        quarantine_rows = self.rows(
            f"SELECT source_file, line_no, reason FROM {CATALOG}.silver.custbill_quarantine "
            f"WHERE ns={q(self.ns)} ORDER BY source_file, line_no, reason")
        qn = len(quarantine_rows)
        self.check("U7-c", 0, qn, "count(*) quarantine on clean seed (T7)")
        trailer = self.rows(
            f"SELECT source_file, "
            f"max(CASE WHEN record_kind='TRL' THEN cast(substr(raw_line,4,10) AS INT) END), "
            f"sum(CASE WHEN record_kind='BODY' THEN 1 ELSE 0 END) "
            f"FROM {CATALOG}.bronze.custbill_raw WHERE ns={q(self.ns)} GROUP BY source_file ORDER BY source_file")
        t_act = [{"file": f, "trailer": None if t is None else int(t), "body": int(b)} for f, t, b in trailer]
        t_exp = [{"file": d["file"], "trailer": d["body"], "body": d["body"]} for d in t_act]
        if not t_act:
            self.skipped("U7-d", "no bronze rows for ns (parse-only fixture without bronze seed)", "bronze TRL count vs BODY count")
        else:
            self.check("U7-d", t_exp, t_act, "bronze TRL cols 4-13 vs BODY row count per file")
        self.fingerprint["silver_counts"] = act_counts
        self.fingerprint["quarantine"] = qn
        self.fingerprint["silver_content"] = content_fingerprint(silver_content)
        self.fingerprint["quarantine_content"] = content_fingerprint(
            ["|".join("" if c is None else str(c) for c in row) for row in quarantine_rows])
        if anomaly_ns and anomaly_root:
            self.anomaly_leg(anomaly_ns, anomaly_root)
        else:
            self.skipped("U7-e", "anomaly leg not run (pass --anomaly-ns/--anomaly-root)", "history manifest planted_anomalies vs quarantine")

    def anomaly_leg(self, ans: str, aroot: Path) -> None:
        manifests = glob.glob(str(aroot / "sftp-drop/history/expected/*-history-expected.json"))
        if len(manifests) != 1:
            raise SystemExit(f"expected exactly one history manifest under {aroot}, found {manifests}")
        manifest = json.loads(Path(manifests[0]).read_text())
        expected = sorted({(a["file"], int(a["row"]), a["kind"]) for a in manifest["planted_anomalies"]})
        got = self.rows(f"SELECT source_file, line_no, reason FROM {CATALOG}.silver.custbill_quarantine WHERE ns={q(ans)}")
        actual = sorted({(f, 0 if r == "trailer_count_mismatch" else int(ln) - 1, r) for f, ln, r in got})
        es, as_ = set(expected), set(actual)
        self.anomaly = {
            "expected_set": [list(t) for t in expected], "actual_set": [list(t) for t in actual],
            "missing": [list(t) for t in sorted(es - as_)], "unexpected": [list(t) for t in sorted(as_ - es)],
        }
        excluded = int(self.rows(
            f"SELECT count(*) FROM {CATALOG}.silver.custbill_records WHERE ns={q(ans)}")[0][0])
        row_level = [a for a in expected if a[1] != 0]
        total_rows = int(manifest["record_count"])
        expected_silver_rows = total_rows - len(row_level)
        self.check("U7-e", {"missing": [], "unexpected": [], "silver_rows": expected_silver_rows},
                   {"missing": self.anomaly["missing"], "unexpected": self.anomaly["unexpected"], "silver_rows": excluded},
                   f"manifest {Path(manifests[0]).name} planted_anomalies (file,row,kind) vs quarantine (source_file,line_no-1,reason) on ns={ans}",
                   ok=not self.anomaly["missing"] and not self.anomaly["unexpected"]
                   and excluded == expected_silver_rows)

    # -- U8 -------------------------------------------------------------------
    def unit_finance(self, anomaly_ns: str | None, anomaly_root: Path | None) -> None:
        csvs = sorted(glob.glob(str(self.root / "reports" / "finance_billing_*.csv")))
        if len(csvs) != 1:
            raise SystemExit(f"expected exactly one legacy finance_billing_*.csv under {self.root}/reports, found {csvs}")
        legacy_csv = Path(csvs[0])
        stamp = legacy_csv.name[len("finance_billing_"):-4]
        legacy_bytes = legacy_csv.read_bytes()
        legacy_rows = list(csv.reader(io.StringIO(legacy_bytes.decode("ascii"))))[1:]
        exp = [[r[0], r[1], int(r[2]), r[3]] for r in legacy_rows]
        got = self.rows(
            f"SELECT currency, record_type, record_count, format_number(total_amount,'0.00') "
            f"FROM {CATALOG}.gold.finance_billing WHERE ns={q(self.ns)} "
            f"ORDER BY currency, CASE record_type WHEN 'INVOICE' THEN '01' WHEN 'CREDIT' THEN '02' "
            f"ELSE regexp_extract(record_type, 'UNKNOWN\\\\((.*)\\\\)', 1) END")
        act = [[r[0], r[1], int(r[2]), r[3]] for r in got]
        self.check("U8-a", exp, act, f"legacy {legacy_csv.name} rows vs gold (currency, record_type, record_count, total_amount) ordered like the Perl sort")
        target_csv_path = f"{landing(self.ns)}/reports/finance_billing_{stamp}.csv"
        try:
            target_bytes = self.dbx.get_file(target_csv_path)
            t_sha = sha256(target_bytes)
        except DbxError as exc:
            target_bytes, t_sha = b"", str(exc)
        xls = legacy_csv.with_suffix(".xls")
        xls_same = xls.exists() and xls.read_bytes() == legacy_bytes
        self.check("U8-b", {"csv_sha256": sha256(legacy_bytes), "legacy_xls_equals_csv": True},
                   {"csv_sha256": t_sha, "legacy_xls_equals_csv": xls_same},
                   f"sha256 legacy csv vs {target_csv_path}; legacy .xls bytes vs .csv bytes")
        # independent recompute from the legacy PSVs with exact Decimal
        agg: dict[tuple[str, str], list] = {}
        for lines in self.legacy_psv_rows().values():
            for ln in lines:
                f = ln.split("|")
                if len(f) < 6 or f[0] == "":
                    continue
                k = (f[4], f[5])
                agg.setdefault(k, [0, Decimal("0")])
                agg[k][0] += 1
                agg[k][1] += Decimal(f[3])
        def rtname(rt: str) -> str:
            return "INVOICE" if rt == "01" else "CREDIT" if rt == "02" else f"UNKNOWN({rt})"
        recomputed = [[k[0], rtname(k[1]), v[0], f"{v[1]:.2f}"] for k, v in sorted(agg.items())]
        sums = self.rows(
            f"SELECT (SELECT format_number(sum(total_amount),'0.00') FROM {CATALOG}.gold.finance_billing WHERE ns={q(self.ns)}), "
            f"(SELECT format_number(sum(bill_amt),'0.00') FROM {CATALOG}.silver.custbill_records WHERE ns={q(self.ns)})")[0]
        self.check("U8-c", {"awk_equivalent": recomputed, "gold_sum_equals_silver_sum": True},
                   {"awk_equivalent": act, "gold_sum_equals_silver_sum": sums[0] == sums[1], "gold_sum": sums[0], "silver_sum": sums[1]},
                   "Decimal recompute over legacy parsed/*.psv (awk one-liner equivalent) vs gold; sum(gold)==sum(silver)",
                   ok=recomputed == act and sums[0] == sums[1])
        xlsx_path = f"{landing(self.ns)}/reports/finance_billing_{stamp}.xlsx"
        try:
            xlsx_bytes = self.dbx.get_file(xlsx_path)
        except DbxError as exc:
            xlsx_bytes = None
            self.check("U8-e", "xlsx present", str(exc), xlsx_path)
        if xlsx_bytes is not None:
            try:
                import openpyxl  # type: ignore
                wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), read_only=True, data_only=True)
                ws = wb["finance_billing"]
                cells = [list(r) for r in ws.iter_rows(values_only=True)]
                body = [[r[0], r[1], int(r[2]), f"{Decimal(str(r[3])):.2f}"] for r in cells[1:] if r and r[0] is not None]
                self.check("U8-e", {"header": ["Currency", "RecordType", "RecordCount", "TotalAmount"], "rows": exp},
                           {"header": list(cells[0]) if cells else [], "rows": body}, f"{xlsx_path} opened with openpyxl")
            except ImportError:
                self.skipped("U8-e", "openpyxl not installed locally; xlsx exists but cell values not verified", xlsx_path)
        self.fingerprint["gold"] = act
        self.fingerprint["csv_sha256"] = t_sha
        if anomaly_ns and anomaly_root:
            self.finance_anomaly_leg(anomaly_ns, anomaly_root)
        else:
            self.skipped("U8-f", "quarantined-totals leg not run (pass --anomaly-ns/--anomaly-root)",
                         "history manifest totals vs gold; bronze BODY cents - gold cents == quarantined cents")

    def finance_anomaly_leg(self, ans: str, aroot: Path) -> None:
        manifests = glob.glob(str(aroot / "sftp-drop/history/expected/*-history-expected.json"))
        if len(manifests) != 1:
            raise SystemExit(f"expected exactly one history manifest under {aroot}, found {manifests}")
        manifest = json.loads(Path(manifests[0]).read_text())

        def rtname(rt: str) -> str:
            return "INVOICE" if rt == "01" else "CREDIT" if rt == "02" else f"UNKNOWN({rt})"

        exp_totals = sorted(
            [t["currency"], rtname(t["record_type"]), int(t["record_count"]), int(t["total_amount_cents"])]
            for y in manifest["per_year"] for t in y["totals"])
        gold = self.rows(
            f"SELECT currency, record_type, record_count, cast(total_amount * 100 AS BIGINT) "
            f"FROM {CATALOG}.gold.finance_billing WHERE ns={q(ans)}")
        act_totals = sorted([c, rt, int(n), int(cents)] for c, rt, n, cents in gold)
        total_records = int(manifest["record_count"])
        exp_rows_delta = total_records - sum(t[2] for t in exp_totals)
        amt = "CASE WHEN substr(raw_line, 49, 12) RLIKE '^[0-9]{12}$' THEN cast(substr(raw_line, 49, 12) AS BIGINT) END"
        body_cents, body_rows = self.rows(
            f"SELECT coalesce(sum({amt}), 0), count(*) FROM {CATALOG}.bronze.custbill_raw "
            f"WHERE ns={q(ans)} AND record_kind='BODY'")[0]
        quar_rows, quar_cents = self.rows(
            f"SELECT count(*), coalesce(sum({amt}), 0) FROM {CATALOG}.silver.custbill_quarantine qr "
            f"JOIN {CATALOG}.bronze.custbill_raw br "
            f"ON br.ns=qr.ns AND br.source_file=qr.source_file AND br.line_no=qr.line_no AND br.record_kind='BODY' "
            f"WHERE qr.ns={q(ans)}")[0]
        gold_rows = sum(t[2] for t in act_totals)
        gold_cents = sum(t[3] for t in act_totals)
        expected = {"totals": exp_totals, "quarantined_rows": exp_rows_delta,
                   "rows_delta_equals_quarantined": True, "cents_delta_equals_quarantined": True}
        actual = {"totals": act_totals, "quarantined_rows": int(quar_rows),
                  "quarantined_cents": int(quar_cents), "bronze_body_rows": int(body_rows),
                  "bronze_body_cents": int(body_cents), "gold_rows": gold_rows, "gold_cents": gold_cents,
                  "rows_delta_equals_quarantined": int(body_rows) - gold_rows == int(quar_rows),
                  "cents_delta_equals_quarantined": int(body_cents) - gold_cents == int(quar_cents)}
        self.check("U8-f", expected, actual,
                   f"quarantined_rows_change_totals on ns={ans}: manifest {Path(manifests[0]).name} totals vs gold; "
                   f"bronze BODY rows/cents minus gold rows/cents must equal quarantine-joined rows/cents",
                   ok=exp_totals == act_totals and int(quar_rows) == exp_rows_delta
                   and actual["rows_delta_equals_quarantined"] and actual["cents_delta_equals_quarantined"])

    # -- U9 -------------------------------------------------------------------
    def unit_workflow(self, evidence: Path | None) -> None:
        job = self.dbx.find_job(JOB_NAME)
        if not job:
            raise SystemExit(f"job {JOB_NAME} not found")
        full = self.dbx.ok("GET", f"/api/2.1/jobs/get?job_id={job['job_id']}")
        s = full.get("settings", {})
        tasks = s.get("tasks", [])
        graph = {t["task_key"]: sorted(d["task_key"] for d in t.get("depends_on", [])) for t in tasks}
        sched = s.get("schedule") or {}
        trig = s.get("trigger") or {}
        act = {
            "tasks": graph,
            "max_concurrent_runs": s.get("max_concurrent_runs"),
            "pause_status": sched.get("pause_status") or trig.get("pause_status"),
            "clusters": [t.get("existing_cluster_id") or t.get("new_cluster") for t in tasks if t.get("existing_cluster_id") or t.get("new_cluster")],
            "on_failure_recipients": (s.get("email_notifications") or {}).get("on_failure", []),
        }
        exp = {"tasks": {"ingest": [], "parse": ["ingest"], "finance": ["parse"]}, "max_concurrent_runs": 1,
               "pause_status": "PAUSED", "clusters": [], "on_failure_recipients": act["on_failure_recipients"]}
        self.check("U9-a", exp, act, f"Jobs API 2.1 get job_id={job['job_id']}", ok=exp == act and bool(act["on_failure_recipients"]))
        self.unit_ingest()
        self.unit_parse(None, None)
        self.unit_finance()
        for c in self.checks:
            if c["id"] in ("U6-a", "U6-b", "U7-a", "U7-b", "U7-c", "U8-a", "U8-b"):
                c["id"] = "U9-b/" + c["id"]
        if evidence and evidence.exists():
            ev = json.loads(evidence.read_text())
            partial = ev.get("partial_upstream_run", {})
            overlap = ev.get("overlap_runs", [])
            ok = (partial.get("run_state") == "FAILED" and partial.get("finance_task_state") == "SKIPPED"
                  and len(overlap) >= 2 and all(r.get("overlapped") is False for r in overlap))
            self.check("U9-c", {"partial_upstream_run": {"run_state": "FAILED", "finance_task_state": "SKIPPED"}, "overlap_runs": "≥2 runs, none overlapped"},
                       {"partial_upstream_run": partial, "overlap_runs": overlap}, f"child-captured run states in {evidence}", ok=ok)
        else:
            self.skipped("U9-c", "no --evidence-json with captured run states", "Jobs API run states")
        self.fingerprint["job"] = act


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--unit", required=True, choices=UNITS)
    ap.add_argument("--ns", required=True)
    ap.add_argument("--legacy-root", required=True, type=Path)
    ap.add_argument("--run-mode", required=True, choices=["fixture", "live"],
                    help="fixture = child namespace slice; live = parent NS=demo proof window")
    ap.add_argument("--anomaly-ns", help="namespace that holds the parsed 2023 history seed (parse/finance units)")
    ap.add_argument("--anomaly-root", type=Path, help="OTTERWORKS_LEGACY_ROOT of the history seed (parse/finance units)")
    ap.add_argument("--evidence-json", type=Path, help="workflow unit: child-captured run states")
    ap.add_argument("--previous", type=Path, help="first-pass snapshot to compare for idempotency")
    ap.add_argument("--unverified", action="append", default=[], help="declared gap (repeatable)")
    ap.add_argument("--waive", action="append", default=[], help="waive a skipped required check (repeatable)")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    ns = require_custbill_ns(a.ns)
    if ns == "demo" and a.run_mode != "live":
        raise SystemExit("ns=demo is the parent's live window: --run-mode live")
    if ns != "demo" and a.run_mode == "live":
        raise SystemExit("run_mode live is reserved for ns=demo; children report fixture on their own slice")
    dbx = Databricks()
    r = Recon(dbx, ns, a.legacy_root)
    if a.unit == "sftp_ingest_poll":
        r.unit_ingest()
    elif a.unit == "parse_custbill_fixedwidth":
        r.unit_parse(a.anomaly_ns, a.anomaly_root)
    elif a.unit == "finance_excel_report":
        r.unit_finance(a.anomaly_ns, a.anomaly_root)
    else:
        r.unit_workflow(a.evidence_json)
    waived = set(a.waive)
    r.unverified.extend(a.unverified)
    for check in r.checks:
        if check["result"] == "skipped" and check["id"] in waived:
            prefix = f"{check['id']}:"
            r.unverified = [
                f"{entry} (waived)" if entry.startswith(prefix) and not entry.endswith(" (waived)") else entry
                for entry in r.unverified
            ]
    wrote_rows = any(bool(v) and v != 0 for k, v in r.fingerprint.items() if k in ("bronze_rows", "silver_counts", "gold"))
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat(timespec="seconds")
    snapshot_time_ms = int(now_dt.timestamp() * 1000)
    prev = None
    if a.previous is None:
        run_start_time_ms = snapshot_time_ms - RUN_LOOKBACK_MS
    else:
        prev = json.loads(a.previous.read_text())
        if prev.get("kind") != "recon-snapshot" or prev.get("unit") != a.unit or prev.get("namespace") != ns:
            raise SystemExit("--previous must be this unit/namespace's first-pass snapshot")
        run_start_time_ms = prev.get("snapshot_time_ms")
        if not isinstance(run_start_time_ms, int):
            run_start_time_ms = None
    latest_run = r.latest_run_for_ns(run_start_time_ms)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    if a.previous is None:
        snap = a.out or REPORT_DIR / f"{a.unit}.recon.first-pass.json"
        snap.write_text(json.dumps({"kind": "recon-snapshot", "unit": a.unit, "namespace": ns, "generated_at": now,
                                    "run_mode": a.run_mode, "checks": r.checks, "fingerprint": r.fingerprint,
                                    "planted_anomaly_detections": r.anomaly, "wrote_rows": wrote_rows,
                                    "latest_run": latest_run,
                                    "snapshot_time_ms": snapshot_time_ms}, indent=2) + "\n")
        fails = verdict(a.unit, r.checks, None, waived)
        print(f"first pass: {len(r.checks)} checks, {len(fails)} failed {fails}; snapshot {snap}")
        print("re-run the job with no new input, then invoke again with --previous", snap)
        return 1 if fails else 0
    same = prev.get("fingerprint") == r.fingerprint
    previous_snapshot_time = prev.get("snapshot_time_ms")
    if isinstance(previous_snapshot_time, int):
        idem_result, idem_reason = idempotency_result(
            same, bool(prev.get("wrote_rows")), prev.get("latest_run"), latest_run,
            previous_snapshot_time,
        )
    else:
        idem_result, idem_reason = (
            "fail",
            "first-pass snapshot lacks snapshot_time_ms; regenerate",
        )
    idem = {
        "performed": True,
        "result": idem_result,
        "reason": idem_reason,
        "previous_latest_run": prev.get("latest_run"),
        "latest_run": latest_run,
        "snapshot_time_ms": previous_snapshot_time,
        "evidence": (
            f"first pass {prev['generated_at']} wrote_rows={prev.get('wrote_rows')}; "
            f"second pass {now} fingerprint {'identical' if same else 'DIFFERS'}; "
            f"{idem_reason}; namespace={ns}; "
            f"fingerprint={json.dumps(r.fingerprint, sort_keys=True)[:600]}"
        ),
    }
    report = {
        "kind": "recon-report", "unit": a.unit, "namespace": ns, "generated_at": now, "run_mode": a.run_mode,
        "checks": r.checks, "values_recomputed_from_target": True, "idempotency_rerun": idem,
        "planted_anomaly_detections": r.anomaly, "unverified_paths": sorted(set(r.unverified)),
        "baseline_provenance": f"legacy outputs regenerated under {a.legacy_root} via scripts/tp-run-deterministic.sh",
    }
    out = a.out or REPORT_DIR / f"{a.unit}.recon.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    fails = verdict(a.unit, r.checks, idem["result"], waived)
    print(f"{'GREEN' if not fails else 'RED'}: {len(r.checks)} checks, failed {fails}; report {out}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
