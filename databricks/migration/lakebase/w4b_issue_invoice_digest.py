#!/usr/bin/env python3
"""Digest the target state a run of the converted sp_issue_invoice produces.

Unit p1-pkg-invoicing (U-23) delivers routines, not a load, so the rerun proof the recon
report carries (`emit_recon_report.py --idempotency-digest`) cannot come from a loader. It
comes from here: one run issues the wave's scenario invoices against Lakebase, digests every
declared write target, and ROLLS BACK. Two such runs from the same delivered state must
produce byte-identical digests.

What that does and does not prove is stated in the unit's summary.md: re-running the routine
over the same input state is idempotent. Calling it twice in a row is a *different* input
state the second time (the first call burns credit notes down), and Oracle behaves the same
way; that path is compared against Oracle in pkg_invoicing_behaviour_check.py instead.

usage: python3 w4b_issue_invoice_digest.py --out <digest.json>
       run under with_lakebase_dsn.py, which sets OW_TP_LAKEBASE_DSN.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import uuid
from pathlib import Path

import psycopg

UNIT = "p1-pkg-invoicing"
CATALOG = "ow_tp"

# The scenarios the Oracle fixture expectation covers, and the period it uses.
TENANTS = ["00000000-0000-0000-0000-000000000001", "00000000-0000-0000-0000-000000000003",
           "00000000-0000-0000-0000-000000000004", "00000000-0000-0000-0000-000000000009"]
PERIOD_START = "2026-02-01 00:00:00"
PERIOD_END = "2026-02-28 00:00:00"

# Every declared write target of this batch, digested whether or not this run touches it.
# Two columns cannot be in a content hash that compares two runs, because the source writes
# them from the clock and a sequence and Oracle does the same: billing_audit_log's serial
# log_id and its logged_at, and rating_state's updated_at (`localtimestamp`). They are
# hashed out by name, and the exclusion is recorded in the digest so a reviewer sees which
# columns the rerun proof does not cover.
TARGETS = {"billing.credit_notes": [], "billing.billing_audit_log": ["log_id", "logged_at"],
           "billing.rating_periods": [], "billing.rating_results": [],
           "billing.rating_state": ["updated_at"], "billing.invoices": [],
           "billing.invoice_lines": []}


def digest(target: str, excluded: list[str], cur) -> dict:
    """Row count plus an order-independent content hash, read back off the target."""
    row = "t"
    if excluded:
        cols = [c for (c,) in cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = split_part(%s, '.', 1) "
            "AND table_name = split_part(%s, '.', 2) "
            "AND column_name <> ALL(%s) ORDER BY ordinal_position",
            (target, target, excluded)).fetchall()]
        row = "ROW(" + ", ".join(f"t.{c}" for c in cols) + ")"
    rows, content = cur.execute(
        "SELECT count(*), md5(string_agg(h, '' ORDER BY h)) FROM "
        f"(SELECT md5({row}::text) AS h FROM {target} t) s").fetchone()
    out = {"table": f"{CATALOG}.{target}", "rows": rows, "content_hash": content}
    if excluded:
        out["excluded_columns"] = excluded
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    dsn = os.environ.get("OW_TP_LAKEBASE_DSN")
    if not dsn:
        raise SystemExit("OW_TP_LAKEBASE_DSN is not set; run under with_lakebase_dsn.py")

    with psycopg.connect(dsn, autocommit=False) as conn:
        (database,) = conn.execute("SELECT current_database()").fetchone()
        if database != CATALOG:
            raise SystemExit(f"target DSN connects to {database!r}, not {CATALOG!r}")
        cur = conn.cursor()
        for tenant in TENANTS:
            cur.execute("CALL billing.sp_issue_invoice(%s, %s, %s)",
                        (tenant, PERIOD_START, PERIOD_END))
        digests = [digest(t, cols, cur) for t, cols in TARGETS.items()]
        conn.rollback()     # the branch keeps exactly the state earlier waves put there

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(
        {"kind": "target-state-digest", "unit": UNIT,
         # The run id, not the clock, tells two runs apart.
         "run_id": uuid.uuid4().hex,
         "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds"),
         "tables": digests}, indent=2) + "\n")
    print(f"digested {len(digests)} declared targets -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
