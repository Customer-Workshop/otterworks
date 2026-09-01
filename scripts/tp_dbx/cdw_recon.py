#!/usr/bin/env python3
"""Reconciliation harness for the COMMISSION_DW -> Databricks migration (DEGRADED mode).

Compares a migrated `ow_tp.<layer>.<unit>_<ns>` table against the legacy baseline
snapshot (`etl/legacy-extra/commission_dw/<ns>/<OBJECT>.csv`, hash-pinned by
manifest.json) and writes `<unit>.recon.json` (schema
docs/tech-partnerships/contracts/schema/recon-report.schema.json) plus a short
`recon.summary.md`.

  python3 scripts/tp_dbx/cdw_recon.py --unit dim_agent --ns cdw --run-mode fixture \
      --rerun "python3 dbx/commission_dw/dim_agent/load.py --ns cdw" --out dbx/commission_dw/dim_agent

Checks (tolerances v1, 03_recon_tolerances.md):
  rowcount            exact
  row_diff            full ordered row-level diff on the declared key; 0 missing, 0 unexpected,
                      0 changed (numeric columns compared as exact Decimals, i.e. exact cents)
  key_preservation    every baseline surrogate key present with the same natural key
  money_sum_cents     exact integer-cents sum for money columns (fact, summary)
  fact_covers_ledger  (fact only) fact rows == ledger feed rows -> dropped_join_rows = 0
  dropped_join_rows   (fact only) ledger feed rows - target fact rows, clamped at 0; expected 0
  idempotency         the --rerun program (one argv, no shell syntax; wrap shell logic in a
                      script) is executed and the target re-read; row set must be
                      identical (loaded_at excluded). Without --rerun the report is invalid
                      (idempotency_rerun.performed must be true) and the harness exits 2.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from client import Databricks, require_ns

CATALOG = "ow_tp"

# unit -> (baseline object, layer, key columns, natural-key columns, money columns)
UNITS: dict[str, dict] = {
    "dim_agent": {"obj": "DIM_AGENT", "layer": "silver", "key": ["agent_key"], "natural": ["agent_id"], "money": []},
    "dim_product": {"obj": "DIM_PRODUCT", "layer": "silver", "key": ["product_key"], "natural": ["product_code"], "money": []},
    "dim_period": {"obj": "DIM_PERIOD", "layer": "silver", "key": ["period_key"], "natural": ["period_month"], "money": []},
    "fact_commission": {"obj": "FACT_COMMISSION", "layer": "silver", "key": ["fact_id"],
                        "natural": ["policy_id", "agent_key", "period_key"], "money": ["base_premium", "commission_amt"]},
    "mv_agent_commission_summary": {"obj": "MV_AGENT_COMMISSION_SUMMARY", "layer": "gold",
                                    "key": ["agent_code", "full_name", "period_month", "line_of_business"], "natural": [],
                                    "money": ["total_commission"]},
}
EXCLUDED_COLUMNS = {"loaded_at"}
NULL = "\x00NULL"
NUMERIC_COLUMNS = {
    "agent_key", "agent_id", "product_key", "period_key", "year_num", "month_num",
    "quarter_num", "fact_id", "policy_id", "split_pct", "base_premium",
    "commission_amt", "policy_rows", "total_commission",
}


def target_table(unit: str, ns: str) -> str:
    return f"{CATALOG}.{UNITS[unit]['layer']}.{unit}_{ns}"


def read_baseline(baseline_dir: Path, obj: str) -> tuple[list[str], list[list[str]]]:
    manifest = json.loads((baseline_dir / "manifest.json").read_text())
    name = f"{obj}.csv"
    payload = (baseline_dir / name).read_bytes()
    if hashlib.sha256(payload).hexdigest() != manifest["files"][name]["sha256"]:
        raise SystemExit(f"baseline {name} does not match manifest sha256; refusing to reconcile")
    rows = list(csv.reader(payload.decode("utf-8").splitlines()))
    return rows[0], rows[1:]


def read_target(dbx: Databricks, unit: str, ns: str, columns: list[str]) -> list[list[str]]:
    spec = UNITS[unit]
    order = ", ".join(spec["key"])
    cols = ", ".join(columns)
    result = dbx.sql_ok(f"SELECT {cols} FROM {target_table(unit, ns)} ORDER BY {order}")
    return [[NULL if v is None else str(v) for v in row] for row in result.rows]


def norm(col: str, value: str) -> object:
    if value == NULL:
        return NULL
    if col not in NUMERIC_COLUMNS:
        return value
    try:
        return Decimal(value)
    except InvalidOperation:
        raise SystemExit(f"invalid numeric value for {col}: {value!r}") from None


def keyed(header: list[str], rows: list[list[str]], key: list[str]) -> tuple[dict[tuple, dict], list[tuple]]:
    idx = [header.index(k) for k in key]
    out = {}
    duplicates = []
    for row in rows:
        row_key = tuple(row[i] for i in idx)
        if row_key in out:
            duplicates.append(row_key)
            continue
        out[row_key] = {h: norm(h, v) for h, v in zip(header, row) if h not in EXCLUDED_COLUMNS}
    return out, duplicates


def cents(rows: dict[tuple, dict], col: str) -> int:
    total = Decimal(0)
    for r in rows.values():
        v = r.get(col, "")
        total += v if isinstance(v, Decimal) else Decimal(0)
    return int((total * 100).to_integral_value())


def check(cid: str, expected, actual, sot: str) -> dict:
    return {"id": cid, "expected": expected, "actual": actual, "source_of_truth": sot,
            "result": "pass" if expected == actual else "fail"}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--unit", required=True, choices=sorted(UNITS))
    p.add_argument("--ns", default="cdw")
    p.add_argument("--run-mode", default="fixture", choices=["fixture", "live"])
    p.add_argument("--baseline-dir", "--baseline", dest="baseline_dir", default=None)
    p.add_argument("--rerun", default=None, help="program + args (single argv string, no shell operators) that re-runs the unit's load (idempotency proof)")
    p.add_argument("--out", required=True)
    p.add_argument("--warehouse", default="565cd2fd713738c4")
    args = p.parse_args()

    ns = require_ns(args.ns)
    spec = UNITS[args.unit]
    baseline_dir = Path(args.baseline_dir or f"etl/legacy-extra/commission_dw/{ns}")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    dbx = Databricks(warehouse_id=args.warehouse)

    header, brows = read_baseline(baseline_dir, spec["obj"])
    columns = [c for c in header if c not in EXCLUDED_COLUMNS]
    trows = read_target(dbx, args.unit, ns, columns)
    base, base_dups = keyed(header, brows, spec["key"])
    if base_dups:
        raise SystemExit(f"baseline {spec['obj']} has duplicate keys: {base_dups}")
    tgt, target_dups = keyed(columns, trows, spec["key"])

    missing = sorted(k for k in base if k not in tgt)
    unexpected = sorted(k for k in tgt if k not in base)
    changed = sorted(k for k in base if k in tgt and base[k] != tgt[k])
    sot = f"legacy baseline {spec['obj']}.csv (manifest-pinned) vs {target_table(args.unit, ns)}"

    checks = [
        check("rowcount", len(brows), len(trows), sot),
        check("duplicate_keys", 0, len(target_dups), sot),
        check("null_count", 0, sum(value == NULL for row in trows for value in row), sot),
        check("row_diff", {"missing": 0, "unexpected": 0, "changed": 0},
              {"missing": len(missing), "unexpected": len(unexpected), "changed": len(changed)}, sot),
    ]
    if spec["natural"]:
        nat_base = {k: tuple(base[k][c] for c in spec["natural"]) for k in base}
        nat_tgt = {k: tuple(tgt[k][c] for c in spec["natural"]) for k in tgt if k in base}
        preserved = sum(1 for k in nat_base if nat_tgt.get(k) == nat_base[k])
        checks.append(check("key_preservation", len(nat_base), preserved, sot))
    for col in spec["money"]:
        checks.append(check(f"money_sum_cents:{col}", cents(base, col), cents(tgt, col), sot))
    if args.unit == "fact_commission":
        _, lrows = read_baseline(baseline_dir, "COMMISSION_LEDGER")
        checks.append(check("fact_covers_ledger", len(lrows), len(tgt),
                            "COMMISSION_LEDGER.csv feed rows vs fact rows (dropped_join_rows must be 0)"))
        checks.append(check("dropped_join_rows", 0, max(0, len(lrows) - len(tgt)),
                            "COMMISSION_LEDGER.csv feed vs target fact rows"))

    idem = {"performed": False, "result": "fail", "evidence": "no --rerun command supplied"}
    if args.rerun:
        proc = subprocess.run(shlex.split(args.rerun), shell=False, capture_output=True, text=True, check=False)
        after = read_target(dbx, args.unit, ns, columns)
        same = proc.returncode == 0 and sorted(after) == sorted(trows)
        idem = {"performed": True, "result": "pass" if same else "fail",
                "evidence": f"rerun rc={proc.returncode}; rows before={len(trows)} after={len(after)}; "
                            f"row set identical={same} (loaded_at excluded)"}

    report = {
        "kind": "recon-report",
        "unit": args.unit,
        "namespace": ns,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "run_mode": args.run_mode,
        "tolerances_version": "v1 (03_recon_tolerances.md)",
        "recon_mode": "DEGRADED (snapshot; federation unavailable)",
        "checks": checks,
        "values_recomputed_from_target": True,
        "idempotency_rerun": idem,
        "planted_anomaly_detections": {"expected_set": [], "actual_set": [], "missing": [], "unexpected": []},
        "unverified_paths": ["live-legacy-comparison (DEGRADED mode)"] +
            ([] if args.run_mode == "live" else
             ["live-mode pass is owned by the parent's independent recon window"]),
        "row_diff_samples": {"missing": [list(k) for k in missing[:5]],
                             "unexpected": [list(k) for k in unexpected[:5]],
                             "changed": [list(k) for k in changed[:5]]},
    }
    (out / f"{args.unit}.recon.json").write_text(json.dumps(report, indent=2, default=str) + "\n")

    verdict = "PASS" if all(c["result"] == "pass" for c in checks) and idem["result"] == "pass" else "FAIL"
    lines = [(f"# Recon summary — `{args.unit}` (ns `{ns}`, run_mode {args.run_mode}, "
              "DEGRADED snapshot (federation unavailable), tolerances v1)"),
             "", f"**Verdict: {verdict}**", "", "| check | expected | actual | result |", "|---|---|---|---|"]
    for c in checks:
        lines.append(f"| {c['id']} | `{c['expected']}` | `{c['actual']}` | {c['result']} |")
    lines += ["", f"Idempotency rerun: {idem['result']} — {idem['evidence']}",
              f"Source of truth: {sot}"]
    (out / "recon.summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    if not idem["performed"]:
        return 2
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
