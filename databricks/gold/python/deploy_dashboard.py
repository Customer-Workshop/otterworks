#!/usr/bin/env python3
"""Create or update the ow_tp finance AI/BI dashboard from the checked-in definition.

    python3 databricks/gold/python/deploy_dashboard.py [--publish]

The definition in databricks/gold/dashboards/ is the source of truth; the workspace copy is
built from it, never the other way round. Dataset queries use bare view names and the
catalog/schema are supplied here, so the same file can be deployed to another workspace.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.dashboards import Dashboard

WAREHOUSE = "565cd2fd713738c4"
CATALOG, SCHEMA = "ow_tp", "gold"
DISPLAY_NAME = "ow_tp Finance Gold"
PARENT_PATH = "/Workspace/Shared/ow_tp"
DEFINITION = Path(__file__).resolve().parents[1] / "dashboards" / "ow_tp_finance_gold.lvdash.json"


def serialized() -> str:
    spec = json.loads(DEFINITION.read_text())
    for dataset in spec["datasets"]:
        dataset.setdefault("catalog", CATALOG)
        dataset.setdefault("schema", SCHEMA)
    return json.dumps(spec)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--publish", action="store_true")
    args = ap.parse_args(argv)

    w = WorkspaceClient()
    w.workspace.mkdirs(PARENT_PATH)

    existing = next((d for d in w.lakeview.list()
                     if d.display_name == DISPLAY_NAME and not d.lifecycle_state
                     or (d.display_name == DISPLAY_NAME
                         and str(d.lifecycle_state) != "LifecycleState.TRASHED")), None)
    body = Dashboard(display_name=DISPLAY_NAME, warehouse_id=WAREHOUSE,
                     serialized_dashboard=serialized())
    if existing and existing.dashboard_id:
        dash = w.lakeview.update(dashboard_id=existing.dashboard_id, dashboard=body)
    else:
        body.parent_path = PARENT_PATH
        dash = w.lakeview.create(dashboard=body)

    if args.publish:
        w.lakeview.publish(dashboard_id=dash.dashboard_id, warehouse_id=WAREHOUSE)
    print(json.dumps({"dashboard_id": dash.dashboard_id, "path": dash.path,
                      "published": args.publish}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
