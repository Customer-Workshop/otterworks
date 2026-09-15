"""Run a pipeline-1 recon gate over the Oracle JDBC route and stamp the result DEGRADED.

Why this exists: D10-01 was denied, so there is no Lakehouse Federation, and `dbx-recon` will
not run `--family oracle` (untested adapter, refused at the CLI by design). The owner directed
the JDBC-from-Devin route at STOP C and accepted the consequence: **every pipeline-1 unit is
graded DEGRADED and no artifact, PR body or wave brief may call it an official harness
verdict.**

What is still the harness's: the mapping parser, the canonicalisation rules, the frozen
tolerances, every tier, the cost model and the result writer. Money stays exact, row counts
exact, 1e-9 relative on other floats, dates ISO-canonicalised, anomaly sets compared as sets.
What is not: the Oracle connector (`oracle_jdbc_adapter.py`).

The target side is always read back from the target platform, never from the CDC output the
unit itself produced.

Usage mirrors `dbx-recon run`; the result lands in `<out>/result.json` with a `degraded` block
and a sibling `DEGRADED.md` the PR body quotes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from oracle_jdbc_adapter import OracleJdbcSourceAdapter  # noqa: E402
from recon.adapters import (  # noqa: E402
    DatabricksTargetAdapter,
    LakebaseTargetAdapter,
    TargetIdentityError,
)
from recon.cli import _load_allowed_targets, _single_identifier, parse_params  # noqa: E402
from recon.config import load_canon_rules, load_mapping_spec, load_tolerances  # noqa: E402
from recon.engine import run_recon  # noqa: E402

REASON = "d10_01_denied"
ADAPTER_NOTE = (
    "Oracle read over JDBC from the Devin CIDRs with a repo-local source adapter "
    "(databricks/migration/recon/oracle_jdbc_adapter.py). The harness supplies every tier, "
    "canonicalisation rule and tolerance; the connector is outside its tested matrix, so "
    "`dbx-recon --family oracle` refuses it and this result is NOT an official harness verdict."
)

DEGRADED_MD = """# DEGRADED recon result — not an official harness verdict

- Unit: `{unit}`
- Mode: `{mode}`, depth: `{depth}`
- Harness verdict on the compared data: `{verdict}`
- Grade: **DEGRADED** (reason: `{reason}`)

D10-01 (opening 1521 to the Databricks serverless NAT range) was denied, so there is no
Lakehouse Federation and no official Oracle verdict is obtainable on this run. The owner
directed this JDBC route and accepted that consequence at STOP C.

{note}

Unverified on this path: source-side constraint, index and identity parity (tiers 5-7), which
need catalog metadata this adapter does not read.
"""


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--unit", required=True)
    p.add_argument("--mapping", type=Path, required=True)
    p.add_argument("--tolerances", type=Path, required=True)
    p.add_argument("--canonicalization", type=Path, required=True)
    p.add_argument("--mode", required=True, choices=["fixture", "live", "snapshot"])
    p.add_argument("--source-dsn-secret", required=True,
                   help="ENV VAR NAME holding the read-only Oracle secret JSON")
    p.add_argument("--target-kind", default="lakebase", choices=["lakebase", "databricks"])
    p.add_argument("--target-secret", required=True, help="ENV VAR NAME, never a value")
    p.add_argument("--target-catalog", required=True)
    p.add_argument("--target-schema", required=True)
    p.add_argument("--allowed-targets-file", type=Path,
                   default=Path(".migration/allowed_targets.json"))
    p.add_argument("--ops", type=Path)
    p.add_argument("--depth", default="threshold", choices=["threshold", "sampled", "full"])
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--param", action="append", default=[], metavar="NAME=VALUE")
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args(argv)

    allowed = _load_allowed_targets(args.allowed_targets_file)
    target_catalog = _single_identifier(args.target_catalog, "target-catalog")
    target_schema = _single_identifier(args.target_schema, "target-schema")
    if target_catalog not in allowed:
        raise SystemExit(f"--target-catalog {target_catalog!r} is not in {args.allowed_targets_file}")

    params = parse_params(args.param)
    spec = load_mapping_spec(args.mapping, params)
    tol = load_tolerances(args.tolerances)
    rules = load_canon_rules(args.canonicalization)
    ops = json.loads(args.ops.read_text()) if args.ops else None

    source = OracleJdbcSourceAdapter(args.source_dsn_secret)
    if args.target_kind == "lakebase":
        try:
            target = LakebaseTargetAdapter(args.target_secret, target_catalog, target_schema)
        except TargetIdentityError as exc:
            raise SystemExit(str(exc)) from None
    else:
        target = DatabricksTargetAdapter(args.target_secret, target_catalog, target_schema)

    run_source = (lambda op: source.run_query(op["source_sql"])) if ops else None
    run_target = (lambda op: target.run_query(op["target_sql"])) if ops else None
    result = run_recon(args.unit, args.mode, spec, tol, rules, source, target,
                       ops=ops, run_source=run_source, run_target=run_target,
                       out_dir=args.out, seed=args.seed, params=params,
                       source_family="oracle-jdbc-degraded", depth=args.depth)

    result["degraded"] = {"grade": "DEGRADED", "official_verdict": False, "reason": REASON,
                          "source_adapter": ADAPTER_NOTE}
    result_path = args.out / "result.json"
    result_path.write_text(json.dumps(result, indent=2, default=str))
    (args.out / "DEGRADED.md").write_text(DEGRADED_MD.format(
        unit=args.unit, mode=args.mode, depth=result["depth"], verdict=result["verdict"],
        reason=REASON, note=ADAPTER_NOTE))

    print(f"DEGRADED (not an official harness verdict) {result['verdict']}: unit={args.unit} "
          f"mode={args.mode} depth={result['depth']} mapping={spec.version} "
          f"tolerances={tol.version} -> {args.out}/result.json")
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
