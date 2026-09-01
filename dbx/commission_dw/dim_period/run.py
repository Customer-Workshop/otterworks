#!/usr/bin/env python3
"""Run the dim_period baseline load and insert-only merge."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "tp_dbx"))
from client import Databricks, require_ns

PERIOD_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def statements(path: Path) -> list[str]:
    text = "\n".join(
        line for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("--")
    )
    return [statement.strip() for statement in re.split(r";(?=[ \t]*(?:\n|$))", text) if statement.strip()]


def merge_metrics(result) -> str | None:
    if not result.rows:
        return None
    values = result.dicts()[0]
    metrics = [
        f"{name}={values[name]}"
        for name in ("num_affected_rows", "num_inserted_rows")
        if name in values
    ]
    return " ".join(metrics) if metrics else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ns", default="cdw")
    parser.add_argument("--period-month")
    parser.add_argument("--warehouse", default="565cd2fd713738c4")
    parser.add_argument(
        "--manifest",
        default="etl/legacy-extra/commission_dw/cdw/manifest.json",
    )
    args = parser.parse_args()

    ns = require_ns(args.ns)
    if ns != "cdw":
        raise SystemExit("this unit writes only ow_tp.silver.dim_period_cdw")
    if args.period_month is not None and not PERIOD_MONTH_RE.fullmatch(args.period_month):
        raise SystemExit("--period-month must match YYYY-MM")

    try:
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        declared_rows = manifest["files"]["COMMISSION_LEDGER.csv"]["rows"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise SystemExit(f"failed to read declared feed rows from {args.manifest}: {exc}") from exc

    unit_dir = Path(__file__).resolve().parent
    period_month = "NULL" if args.period_month is None else f"'{args.period_month}'"
    substitutions = {
        "{{declared_feed_rows}}": str(declared_rows),
        "{{p_period_month}}": period_month,
    }
    dbx = Databricks(warehouse_id=args.warehouse)
    all_statements = statements(unit_dir / "ddl.sql") + statements(unit_dir / "load.sql")
    for statement in all_statements:
        for placeholder, value in substitutions.items():
            statement = statement.replace(placeholder, value)
        result = dbx.sql_ok(statement)
        print(f"ok {' '.join(statement.split())[:60]}")
        if statement.lstrip().upper().startswith("MERGE INTO"):
            metrics = merge_metrics(result)
            if metrics:
                print(metrics)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
