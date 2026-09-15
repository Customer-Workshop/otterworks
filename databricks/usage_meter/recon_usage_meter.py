"""Correctness comparison for the usage meter.

Three comparisons, all recomputed from the target platform at run time:

1. `meter_vs_direct_aggregate` - the gold meter against a direct aggregate of the
   normalised events, with the rating window rebuilt from `occurred_at` the way
   `pkg_rating` does it (inclusive `YYYYMMDD` between period start and end).
2. `meter_vs_migrated_snapshot` - the same aggregate over the Pipeline 1 snapshot
   `ow_tp.silver.usage_events`, which this pipeline does not read at run time. It
   shows the bronze -> silver path neither dropped nor invented events.
3. `lakebase_vs_meter` - the slice published to Lakebase against gold.

Tolerances: integer counts and unit totals must be exactly equal; floating point
columns must agree to 1e-9 relative. The meter carries no money column, so the
money rule has nothing to compare - stated here rather than silently skipped.

    python3 recon_usage_meter.py [--branch mig-p1-w0] [--period 2026-02-01]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from executor import Executor, get_executor
from lakebase_sync import TABLE as LAKEBASE_TABLE, dsn
from pipeline import ingest, meter as meter_stage, normalise
from meter_sql import (
    PRODUCTION,
    Namespace,
    current_period,
    direct_aggregate,
    meter_rows_for_period,
    source_snapshot_aggregate,
)

FLOAT_RTOL = 1e-9
EXACT_COLUMNS = ("event_count", "units_total")
FLOAT_COLUMNS = ("avg_units_per_event",)
MONEY_COLUMNS: tuple[str, ...] = ()
EVIDENCE = Path(__file__).resolve().parent / "evidence"


def _key(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row["tenant_id"]), str(row["metric"]))


def compare(left: list[dict[str, Any]], right: list[dict[str, Any]],
            left_name: str, right_name: str) -> dict[str, Any]:
    li = {_key(r): r for r in left}
    ri = {_key(r): r for r in right}
    mismatches: list[dict[str, Any]] = []
    for key in sorted(set(li) | set(ri)):
        if key not in li or key not in ri:
            mismatches.append({"key": list(key),
                               "reason": f"missing in {right_name if key not in ri else left_name}"})
            continue
        a, b = li[key], ri[key]
        for column in EXACT_COLUMNS + MONEY_COLUMNS:
            if int(a[column]) != int(b[column]):
                mismatches.append({"key": list(key), "column": column,
                                   left_name: int(a[column]), right_name: int(b[column])})
        for column in FLOAT_COLUMNS:
            x, y = float(a[column]), float(b[column])
            if abs(x - y) > FLOAT_RTOL * max(abs(x), abs(y), 1.0):
                mismatches.append({"key": list(key), "column": column,
                                   left_name: x, right_name: y, "rtol": FLOAT_RTOL})
    return {
        "left": left_name,
        "right": right_name,
        "rows_left": len(li),
        "rows_right": len(ri),
        "exact_columns": list(EXACT_COLUMNS),
        "money_columns": list(MONEY_COLUMNS),
        "float_columns": list(FLOAT_COLUMNS),
        "float_relative_tolerance": FLOAT_RTOL,
        "mismatches": mismatches,
        "verdict": "pass" if not mismatches else "fail",
    }


def gold_digest(ex: Executor, ns: Namespace) -> str:
    return str(ex.scalar(
        f"SELECT MD5(CONCAT_WS('|', SORT_ARRAY(COLLECT_LIST(CONCAT_WS(':', tenant_id, metric, "
        f"CAST(period_start AS STRING), CAST(event_count AS STRING), "
        f"CAST(units_total AS STRING)))))) FROM {ns.meter}"))


def idempotency_rerun(ex: Executor, ns: Namespace) -> dict[str, Any]:
    """Run the pipeline again over the same landing volume and diff gold."""
    before = gold_digest(ex, ns)
    ingest(ex, ns)
    normalise(ex, ns)
    stats = meter_stage(ex, ns)
    after = gold_digest(ex, ns)
    passed = before == after
    return {
        "performed": True,
        "result": "pass" if passed else "fail",
        "evidence": (f"gold digest {before} unchanged after a full rerun, "
                     f"{stats['rows_in']} new silver rows on the second pass") if passed
        else f"gold digest changed {before} -> {after}",
    }


ANOMALIES = ("duplicate-event-id", "late-arriving-event", "missing tenant attribution",
             "units must be > 0", "unknown usage kind")


def planted_anomalies(ex: Executor) -> dict[str, Any]:
    """What test_usage_meter.py planted, read back out of the `_selftest` tables."""
    actual: list[str] = []
    try:
        if ex.scalar("SELECT COUNT(*) FROM ow_tp.silver.usage_meter_events_selftest"
                     " WHERE seen_count > 1"):
            actual.append("duplicate-event-id")
        if ex.scalar("SELECT COUNT(*) FROM ow_tp.silver.usage_meter_events_selftest"
                     " WHERE is_late"):
            actual.append("late-arriving-event")
        actual += sorted(r["reject_reason"] for r in ex.sql(
            "SELECT DISTINCT reject_reason FROM ow_tp.silver.usage_meter_rejects_selftest"))
    except Exception as exc:  # the tables only exist once the test suite has run
        actual = [f"unavailable: {exc}"]
    return {"expected_set": list(ANOMALIES), "actual_set": actual,
            "missing": [a for a in ANOMALIES if a not in actual],
            "unexpected": [a for a in actual if a not in ANOMALIES]}


def lakebase_rows(branch: str, period_start: str) -> list[dict[str, Any]]:
    import psycopg

    with psycopg.connect(dsn(branch)) as conn, conn.cursor() as cur:
        cur.execute(f"SELECT tenant_id, metric, event_count, units_total, avg_units_per_event "
                    f"FROM {LAKEBASE_TABLE} WHERE period_start = %s", (period_start,))
        names = [c.name for c in cur.description]
        return [dict(zip(names, row)) for row in cur.fetchall()]


def run(branch: str = "mig-p1-w0", period: str | None = None,
        ns: Namespace = PRODUCTION) -> dict[str, Any]:
    ex = get_executor()
    period_start = period or str(ex.scalar(current_period(ns)))
    period_end = str(ex.scalar(
        f"SELECT MAX(period_end) FROM {ns.meter} WHERE period_start = DATE'{period_start}'"))

    meter = ex.sql(meter_rows_for_period(ns, period_start))
    direct = ex.sql(direct_aggregate(ns, period_start, period_end))
    snapshot = ex.sql(source_snapshot_aggregate(period_start, period_end))
    published = lakebase_rows(branch, period_start)

    comparisons = [
        compare(meter, direct, "meter", "direct_aggregate"),
        compare(meter, snapshot, "meter", "migrated_snapshot"),
        compare(published, meter, "lakebase", "meter"),
    ]
    rerun = idempotency_rerun(ex, ns)
    anomalies = planted_anomalies(ex)
    totals = {
        "meter_events": sum(int(r["event_count"]) for r in meter),
        "meter_units": sum(int(r["units_total"]) for r in meter),
        "direct_events": sum(int(r["event_count"]) for r in direct),
        "direct_units": sum(int(r["units_total"]) for r in direct),
        "lakebase_events": sum(int(r["event_count"]) for r in published),
        "lakebase_units": sum(int(r["units_total"]) for r in published),
    }
    checks = [{"id": f"{c['left']}_vs_{c['right']}",
               "expected": {"mismatches": 0, "rows": c["rows_right"]},
               "actual": {"mismatches": len(c["mismatches"]), "rows": c["rows_left"]},
               "source_of_truth": c["right"], "result": c["verdict"]} for c in comparisons]
    checks.append({
        "id": "period_totals", "source_of_truth": "direct_aggregate",
        "expected": {"events": totals["direct_events"], "units": totals["direct_units"]},
        "actual": {"events": totals["meter_events"], "units": totals["meter_units"]},
        "result": "pass" if (totals["direct_events"], totals["direct_units"])
        == (totals["meter_events"], totals["meter_units"]) else "fail"})

    return {
        "kind": "recon-report",
        "unit": "ow-tp-usage-meter",
        "namespace": "ow_tp",
        "run_mode": "live",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "checks": checks,
        "values_recomputed_from_target": True,
        "idempotency_rerun": rerun,
        "planted_anomaly_detections": anomalies,
        "period": {"start": period_start, "end": period_end},
        "target": {"catalog": "ow_tp", "meter_table": ns.meter,
                   "lakebase_project": "ow-tp-billing", "lakebase_branch": branch,
                   "lakebase_table": LAKEBASE_TABLE},
        "rating_window_rule": "TO_CHAR(occurred_at,'YYYYMMDD') between period start and end, inclusive",
        "totals": totals,
        "comparisons": comparisons,
        "verdict": "pass" if all(c["verdict"] == "pass" for c in comparisons)
        and rerun["result"] == "pass" and not anomalies["missing"] else "fail",
        "unverified_paths": [
            "No money column exists in the meter, so the exact-on-money rule has nothing to compare; rating's tier, quota, rollover and proration arithmetic is untouched by this work.",
            "Nothing was read from Oracle. Agreement is with the migrated Delta snapshot, not with a live legacy query.",
            "The legacy rating package was not executed against these events; the comparison reproduces its window rule, it does not run it.",
            "Lakebase branch mig-p1-w0 only; no production branch was contacted.",
            "The schedule is paused, so no unattended run has been observed.",
        ],
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--branch", default="mig-p1-w0")
    parser.add_argument("--period", default=None)
    parser.add_argument("--out", default=str(EVIDENCE / "usage_meter.recon.json"))
    args = parser.parse_args(argv)

    report = run(args.branch, args.period)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(json.dumps({"verdict": report["verdict"], "totals": report["totals"], "report": str(out)},
                     indent=2))
    return 0 if report["verdict"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
