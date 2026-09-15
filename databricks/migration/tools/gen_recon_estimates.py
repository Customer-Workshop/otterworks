#!/usr/bin/env python3
"""Run `dbx-recon estimate` for every pipeline-1 data unit and collect the wave cost lines.

Row counts are the live counts in docs/migration/OtterWorks_inventory.md (FACT(live)).
Writes .migration/units/<unit>/cost_estimate.json per unit and prints a per-wave rollup
that the wave manifests carry in their `cost_estimate` block.

    python3 databricks/migration/tools/gen_recon_estimates.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
UNITS = ROOT / ".migration/units"
TOL = ROOT / ".migration/03_recon_tolerances.json"

ROWS = {
    "customer_master": 25000, "customer_master_hist": 0, "invoice_line": 150000,
    "invoice_header": 18750, "entity_attr_value": 8333, "usage_events": 814,
    "codes": 32, "plans": 3, "subscriptions_hist": 0, "tenants": 69,
    "subscriptions": 69, "rating_periods": 3, "rating_results": 3, "invoices": 3,
    "invoice_lines": 2, "credit_notes": 5, "dunning_attempts": 1, "notifications": 1,
    "billing_audit_log": 0,
}

# unit -> (wave, batch, depth). Depth `full` everywhere the money path or an id chain runs;
# `sampled` only where the unit is a transport/orchestration shell with no row contract.
# Must stay in step with PLAN in gen_wave_manifests.py.
PLACEMENT = {
    "p1-pkg-ow-util": (0, "w0-a", "full"),
    # The transport unit proves the CDC leg lands rows and preserves order; the row
    # contract on those three tables belongs to their own units, so threshold depth here.
    "p1-cdc-transport": (0, "w0-b", "threshold"),
    "p1-tenants": (1, "w1-a", "full"),
    "p1-plans": (1, "w1-a", "full"),
    "p1-codes": (1, "w1-a", "full"),
    "p1-usage-events": (1, "w1-b", "full"),
    "p1-invoice-header": (1, "w1-c", "full"),
    "p1-invoice-line": (1, "w1-c", "full"),
    "p1-subscriptions": (2, "w2-a", "full"),
    "p1-pkg-plans": (2, "w2-a", "full"),
    "p1-customer-master": (2, "w2-b", "full"),
    "p1-entity-attr-value": (2, "w2-c", "full"),
    "p1-customer-master-hist": (2, "w2-d", "full"),
    "p1-subscriptions-hist": (2, "w2-d", "full"),
    "p1-billing-audit-log": (2, "w2-e", "full"),
    "p1-job-purge-audit-log": (2, "w2-e", "sampled"),
    "p1-rating-periods": (3, "w3-a", "full"),
    "p1-rating-results": (3, "w3-a", "full"),
    "p1-pkg-rating": (3, "w3-a", "full"),
    "p1-credit-notes": (2, "w2-f", "full"),
    "p1-invoices": (3, "w3-b", "full"),
    "p1-invoice-lines": (3, "w3-b", "full"),
    # Wave 4, not 3: D-009 moved it out of w3-b so its runtime writes to the rating tables
    # land after the wave that owns them.
    "p1-pkg-invoicing": (4, "w4-b", "full"),
    "p1-dunning-attempts": (3, "w3-d", "full"),
    "p1-notifications": (3, "w3-d", "full"),
    "p1-pkg-dunning": (3, "w3-d", "full"),
    "p1-job-nightly-dunning": (4, "w4-a", "sampled"),
}


def main() -> int:
    waves: dict[int, dict] = {}
    for unit, (wave, batch, depth) in PLACEMENT.items():
        spec = json.loads((UNITS / unit / "mapping_spec.json").read_text())
        mode = "transactional" if spec["track"] == "lakebase" else "live"
        counts = {t["source_table"]: ROWS[t["source_table"].split(".")[-1]]
                  for t in spec["tables"]}
        # delete=False so the subprocess can open the path on every platform; the finally
        # below is what removes it, including when dbx-recon exits non-zero.
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(counts, fh)
            counts_path = fh.name
        ops_file = UNITS / unit / "ops.json"
        ops_count = len(json.loads(ops_file.read_text())) if ops_file.exists() else 0
        cmd = ["dbx-recon", "estimate", "--mapping", str(UNITS / unit / "mapping_spec.json"),
               "--tolerances", str(TOL), "--depth", depth, "--mode", mode,
               "--row-counts", counts_path]
        if ops_count:
            cmd += ["--ops-count", str(ops_count)]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True)
        finally:
            Path(counts_path).unlink(missing_ok=True)
        if out.returncode != 0:
            print(out.stdout + out.stderr, file=sys.stderr)
            return out.returncode
        est = json.loads(out.stdout)
        est = est.get("estimate", est)
        record = {"unit": unit, "wave": wave, "batch": batch, "depth": depth,
                  "mode": mode, "rows": sum(counts.values()), "row_counts": counts,
                  "ops": ops_count, "estimate": est}
        (UNITS / unit / "cost_estimate.json").write_text(json.dumps(record, indent=2) + "\n")
        agg = waves.setdefault(wave, {"source_statements": 0, "target_statements": 0,
                                      "source_rows_fetched": 0, "target_rows_fetched": 0})
        agg["source_statements"] += int(est["source_statements"]["total"])
        agg["target_statements"] += int(est["target_statements"]["total"])
        agg["source_rows_fetched"] += int(est.get("source_rows_fetched") or 0)
        agg["target_rows_fetched"] += int(est.get("target_rows_fetched") or 0)
    print(json.dumps(waves, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
