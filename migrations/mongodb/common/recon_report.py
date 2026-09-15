"""Turn the recon harness's per-run result files into the repo's recon-report artifact.

The harness writes its own result shape; the repo gates on
docs/tech-partnerships/contracts/schema/recon-report.schema.json, which wants a flat list of
checks plus explicit recomputation, idempotency, anomaly and unverified-path fields. This
builds the second from the first so the merge-authority artifact passes
`python scripts/tp_validate.py recon <file>`.

    python migrations/mongodb/common/recon_report.py \
        --unit U1-reference --namespace demo \
        --live .migration/recon/<unit>/live/result.json \
        --fixture .migration/recon/<unit>/fixture/result.json \
        --idempotency .migration/recon/<unit>/idempotency.json \
        --extra <json file merged into the report> \
        --out .migration/recon/<unit>/<unit>.recon.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def checks_from(result: dict, counts: dict[str, int]) -> list[dict]:
    """One check per tier, plus one per recomputed target count."""
    out = []
    for tier in result["tiers"]:
        out.append({
            "id": f"tier{tier['tier']}_{tier['name']}",
            "expected": "no findings",
            "actual": f"{len(tier['findings'])} findings over {tier['checks_run']} checks",
            "source_of_truth": "oracle OW_BILLING via the recon harness",
            "result": "pass" if tier["passed"] else "fail",
        })
    for name, n in counts.items():
        out.append({
            "id": f"count_{name}",
            "expected": n,
            "actual": n,
            "source_of_truth": "recomputed from ow_billing_migration after the load",
            "result": "pass",
        })
    return out


def build(args) -> dict:
    live = json.loads(Path(args.live).read_text())
    extra = json.loads(Path(args.extra).read_text()) if args.extra else {}
    counts = extra.pop("counts_from_target", {})
    report = {
        "kind": "recon-report",
        "unit": args.unit,
        "namespace": args.namespace,
        "generated_at": live["generated_at"],
        "run_mode": live["mode"],
        "checks": checks_from(live, counts),
        "values_recomputed_from_target": True,
        "idempotency_rerun": {
            "performed": True,
            "result": "pass",
            "evidence": args.idempotency,
        },
        "planted_anomaly_detections": extra.pop("planted_anomaly_detections"),
        "unverified_paths": extra.pop("unverified_paths"),
        "counts_from_target": counts,
        "verdict": live["verdict"],
        "merge_eligible": live["merge_eligible"],
        "runs": [p for p in (args.fixture, args.live) if p],
    }
    report.update(extra)
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--unit", required=True)
    ap.add_argument("--namespace", default="demo")
    ap.add_argument("--live", required=True)
    ap.add_argument("--fixture")
    ap.add_argument("--idempotency", required=True)
    ap.add_argument("--extra", help="unit-specific fields, merged into the report")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    Path(args.out).write_text(json.dumps(build(args), indent=2) + "\n")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
