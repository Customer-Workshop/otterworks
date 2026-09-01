#!/usr/bin/env python3
"""Run the dim_agent unit end-to-end: ddl.sql (drop + recreate) then load.sql.

  python3 dbx/commission_dw/dim_agent/run.py --ns cdw

Every statement goes through scripts/tp_dbx/client.py on the serverless SQL warehouse;
the run is idempotent because ddl.sql starts by dropping the unit's own target table.
The only object written is `ow_tp.silver.dim_agent_<ns>`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "scripts" / "tp_dbx"))
from client import Databricks, require_ns

NS_BOUND = {
    "ow_tp.silver.dim_agent_cdw": "ow_tp.silver.dim_agent_{ns}",
    "ow_tp.bronze.agents_cdw": "ow_tp.bronze.agents_{ns}",
    "/Volumes/ow_tp/bronze/landing/cdw/": "/Volumes/ow_tp/bronze/landing/{ns}/",
}


def statements(path: Path, ns: str) -> list[str]:
    text = "\n".join(line for line in path.read_text().splitlines() if not line.lstrip().startswith("--"))
    for literal, template in NS_BOUND.items():
        text = text.replace(literal, template.format(ns=ns))
    return [chunk.strip() for chunk in text.split(";") if chunk.strip()]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ns", default="cdw")
    p.add_argument("--warehouse", default="565cd2fd713738c4")
    args = p.parse_args()
    ns = require_ns(args.ns)
    dbx = Databricks(warehouse_id=args.warehouse)
    target = NS_BOUND["ow_tp.silver.dim_agent_cdw"].format(ns=ns)
    for name in ("ddl.sql", "load.sql"):
        for stmt in statements(HERE / name, ns):
            result = dbx.sql_ok(stmt)
            head = " ".join(stmt.split()[:2])
            metrics = f" {dict(zip(result.columns, result.rows[0]))}" if head.startswith("MERGE") and result.rows else ""
            print(f"{name}: {head} -> {result.state}{metrics}")
    print(f"rows in {target}: {dbx.sql_ok(f'SELECT count(*) FROM {target}').scalar()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
