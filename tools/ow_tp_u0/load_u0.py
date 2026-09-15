from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import uuid
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.dbx_recon_oracle.adapter import connect_oracle
from tools.dbx_recon_oracle.adapter import parse_dsn
from tools.ow_tp_u0.oracle_read import read_pinned
from tools.ow_tp_u0.target_write import ensure_delta_tables
from tools.ow_tp_u0.target_write import load_lakebase


DECLARED_COUNTS = {
    "CODES": 32,
    "PLANS": 3,
    "TENANTS": 69,
    "BILLING_AUDIT_LOG": 0,
}


def _hash_rows(rows: list[tuple]) -> str:
    payload = json.dumps(rows, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--oracle-dsn-env", required=True)
    parser.add_argument("--lakebase-dsn-env", required=True)
    parser.add_argument("--evidence-out", required=True, type=Path)
    parser.add_argument("--skip-delta", action="store_true")
    args = parser.parse_args()
    oracle_dsn = os.environ.get(args.oracle_dsn_env)
    lakebase_dsn = os.environ.get(args.lakebase_dsn_env)
    if not oracle_dsn or not lakebase_dsn:
        raise SystemExit("requested DSN environment variable is unset")

    started = dt.datetime.now(dt.timezone.utc)
    oracle_user, oracle_password, oracle_connect_dsn = parse_dsn(oracle_dsn)
    with connect_oracle(
        user=oracle_user,
        password=oracle_password,
        dsn=oracle_connect_dsn,
    ) as oracle:
        scn, rows = read_pinned(oracle)
    actual_counts = {name: len(values) for name, values in rows.items()}
    target_counts = load_lakebase(lakebase_dsn, rows)
    if not args.skip_delta:
        ensure_delta_tables()
    finished = dt.datetime.now(dt.timezone.utc)
    evidence = {
        "run_id": str(uuid.uuid4()),
        "unit": "U0_shared_core",
        "scn": scn,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "declared_source_counts": DECLARED_COUNTS,
        "actual_source_counts": actual_counts,
        "target_counts_after_load": target_counts,
        "count_mismatches": {
            name: {"declared": DECLARED_COUNTS[name], "actual": actual_counts[name]}
            for name in DECLARED_COUNTS
            if DECLARED_COUNTS[name] != actual_counts[name]
        },
        "hashes": {name: _hash_rows(values) for name, values in rows.items()},
        "delta_tables_ensured": not args.skip_delta,
    }
    args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
    args.evidence_out.write_text(json.dumps(evidence, indent=2, default=str) + "\n")
    print(f"Loaded U0_shared_core at SCN {scn}; evidence: {args.evidence_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
