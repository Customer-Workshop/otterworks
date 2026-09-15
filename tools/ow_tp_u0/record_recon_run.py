from __future__ import annotations

import argparse
import json
import os
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _sql_literal(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return "'" + str(value).replace("'", "''") + "'"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--scn", required=True, type=int)
    parser.add_argument("--lakebase-branch", required=True)
    args = parser.parse_args()
    result = json.loads(args.result.read_text())
    now = datetime.now(timezone.utc).isoformat()
    sql = f"""
    INSERT INTO ow_tp.ops.p1_recon_runs
      (run_id, unit, mode, verdict, merge_eligible, scn_pin, lakebase_branch,
       started_at, finished_at, cost, result_path, recorded_at)
    VALUES (
      {_sql_literal(str(uuid.uuid4()))},
      {_sql_literal(result.get("unit"))},
      {_sql_literal(result.get("mode"))},
      {_sql_literal(result.get("verdict"))},
      {_sql_literal(result.get("merge_eligible"))},
      {args.scn},
      {_sql_literal(args.lakebase_branch)},
      {_sql_literal(result.get("started_at"))},
      {_sql_literal(result.get("finished_at"))},
      {_sql_literal(json.dumps(result.get("cost", {}), separators=(",", ":")))},
      {_sql_literal(str(args.result.resolve()))},
      {_sql_literal(now)}
    )
    """
    env = os.environ.copy()
    env.pop("DATABRICKS_TOKEN", None)
    env.pop("DATABRICKS_DEMO_TOKEN", None)
    env["DATABRICKS_HOST"] = os.environ["DATABRICKS_DEMO_HOST"]
    subprocess.run(
        ["databricks", "experimental", "aitools", "tools", "query", sql],
        check=True,
        env=env,
        stdout=subprocess.DEVNULL,
    )
    print("Recorded reconciliation run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
