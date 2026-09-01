"""CLI: recon run --unit <id> --mapping ... --tolerances ... --canonicalization ...

Secrets are passed by environment-variable NAME (--source-dsn-secret, --target-uri-secret);
the harness reads the value from the environment and never accepts literals.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import load_canon_rules, load_mapping_spec, load_tolerances
from .engine import MODES, run_recon

SOURCE_FAMILIES = ("oracle", "sqlserver", "mongodb-atlas")


def _build_source(family: str, dsn_secret: str, source_db: str | None):
    if family == "oracle":
        from .adapters import OracleSourceAdapter
        return OracleSourceAdapter(dsn_secret)
    if family == "sqlserver":
        from .adapters import SqlServerSourceAdapter
        return SqlServerSourceAdapter(dsn_secret)
    from .adapters import MongoSourceAdapter
    if not source_db:
        raise SystemExit("--source-db is required for the mongodb-atlas family")
    return MongoSourceAdapter(dsn_secret, source_db)


def selftest() -> int:
    """Blueprint post-setup check: exercises every canonicalization rule on sample values
    and verifies the engine and report modules import. No database connections."""
    import datetime as dt
    import decimal
    import uuid as uuid_mod

    from . import canon, engine, report  # noqa: F401
    from .config import CanonRule

    samples = {
        "decimal_round": decimal.Decimal("1.23456789012"),
        "datetime_utc_truncate_ms": dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc),
        "datetime_grid_333": dt.datetime(2000, 1, 1, 0, 0, 0, 3000),
        "rstrip_spaces": "x  ",
        "empty_string_is_null": "",
        "null_missing_equiv": canon.MISSING,
        "collation_casefold": "ABC",
        "uuid_normalize": uuid_mod.uuid4(),
        "identity": 1,
    }
    c = canon.Canonicalizer([CanonRule(rule=name, applies_to="*", params={})
                             for name in samples])
    for name, value in samples.items():
        c.apply(value, [name])
    print(f"recon selftest PASS: {len(samples)} canonicalization rules exercised")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="recon")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("selftest", help="verify the harness install (no connections needed)")
    r = sub.add_parser("run", help="run the recon gate for one unit")
    r.add_argument("--unit", required=True)
    r.add_argument("--family", required=True, choices=SOURCE_FAMILIES)
    r.add_argument("--mapping", required=True, type=Path)
    r.add_argument("--tolerances", required=True, type=Path)
    r.add_argument("--canonicalization", required=True, type=Path,
                   help="the source profile's recon_canonicalization rules, as JSON")
    r.add_argument("--mode", required=True, choices=MODES)
    r.add_argument("--source-dsn-secret", required=True,
                   help="ENV VAR NAME holding the source DSN (read-only principal)")
    r.add_argument("--target-uri-secret", required=True,
                   help="ENV VAR NAME holding the migration-cluster URI")
    r.add_argument("--target-db", required=True)
    r.add_argument("--source-db", help="source database name (mongodb-atlas family only)")
    r.add_argument("--ops", type=Path, help="recorded representative operations for Tier 4")
    r.add_argument("--source-concurrency", type=int, default=1,
                   help="STOP A source-load cap (informational; harness runs serially)")
    r.add_argument("--seed", type=int, default=0, help="sampling seed (determinism)")
    r.add_argument("--out", required=True, type=Path)
    args = p.parse_args(argv)

    if args.cmd == "selftest":
        return selftest()

    spec = load_mapping_spec(args.mapping)
    tol = load_tolerances(args.tolerances)
    rules = load_canon_rules(args.canonicalization)

    from .adapters import MongoTargetAdapter
    source = _build_source(args.family, args.source_dsn_secret, args.source_db)
    target = MongoTargetAdapter(args.target_uri_secret, args.target_db)

    ops = json.loads(args.ops.read_text()) if args.ops else None
    result = run_recon(args.unit, args.mode, spec, tol, rules, source, target,
                       ops=ops, out_dir=args.out, seed=args.seed)
    print(f"recon {result['verdict']}: unit={args.unit} mode={args.mode} "
          f"mapping={spec.version} tolerances={tol.version} -> {args.out}/result.json")
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
