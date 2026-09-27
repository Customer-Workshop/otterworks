#!/usr/bin/env python3
"""Dry-run-by-default reset of the Databricks-side demo state left by an
OtterWorks OW_BILLING migration run, so the estate can be rerun from clean.

This is an operator action run by the workspace admin (the PAT identity behind
DATABRICKS_DEMO_HOST / DATABRICKS_DEMO_TOKEN — though any identity that owns or
administers the objects works, including a service principal), not a factory action: it deletes
whole schemas with DROP SCHEMA CASCADE and is deliberately outside the
.migration allowlist machinery. It exists because `tables delete` misses
pipeline materialization tables (`__materialization_mat_*`), leaving schemas
non-empty, and because Lakebase read-write endpoints cannot be deleted while
their branches can.

Only run-scoped schemas (`<catalog>.<schema-prefix>*`, e.g. `mig_20260926_bronze`)
are dropped — the shared `ow_tp.bronze/silver/gold` hold the persistent showcase
namespace and are never touched.

Plan -> act -> negative verification, modelled on showcase.py cmd_teardown.
Stdlib only; uses client.py Databricks for REST + SQL.

  python3 scripts/tp_dbx/demo_reset.py            # print plan, do nothing
  python3 scripts/tp_dbx/demo_reset.py --apply    # execute, then verify
  ... [--catalog ow_tp] [--schema-prefix mig_] [--job-prefix ow_tp_] [--lakebase-project ow-tp-billing]
      [--branch-prefix mig-] [--start-oracle i-0123...]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.parse
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from client import Databricks, DbxError, require_ident  # noqa: E402
import showcase  # noqa: E402

# the showcase teardown owns these; a demo reset must never touch them. The
# constants come from showcase.py so the exclusions cannot drift from the names
# showcase actually creates.
SHOWCASE_JOB_PREFIX = showcase.RECON_JOB_PREFIX
SHOWCASE_PIPELINE_PREFIX = showcase.PIPELINE_PREFIX
SHOWCASE_DASHBOARD_PREFIXES = (showcase.HISTORY_PREFIX, showcase.DASHBOARD_PREFIX)

KINDS = ("job", "pipeline", "dashboard", "schema", "lakebase_branch", "oracle")

BRANCH_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
# shared schemas a run prefix must never be able to swallow, and the Lakebase
# production branch — a prefix of any of these is a plan error, not a delete
PROTECTED_SCHEMA_NAMES = ("bronze", "silver", "gold", "ops", "default", "information_schema")
PROTECTED_BRANCH_NAMES = ("production",)


@dataclass
class Opts:
    catalog: str = "ow_tp"
    schema_prefix: str = "mig_"
    job_prefix: str = "ow_tp_"
    lakebase_project: str = "ow-tp-billing"
    branch_prefix: str = "mig-"
    start_oracle: str = ""


@dataclass
class Item:
    kind: str
    name: str
    action: str
    resource_id: str = ""


@dataclass
class Plan:
    items: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    def add(self, kind: str, name: str, action: str, resource_id: str = "") -> None:
        self.items.append(Item(kind, name, action, resource_id))


def _run_schemas(rows: list, opts: Opts) -> list[str]:
    """Full schema names under opts.catalog carrying the run prefix. Shared
    schemas (bronze/silver/gold, airbyte_demo, ...) lack the prefix and are
    never returned; information_schema and default are excluded outright."""
    out = []
    for row in rows:
        name = row[0] if isinstance(row, (list, tuple)) else row
        short = str(name).split(".")[-1]
        if short in {"information_schema", "default"} or not short.startswith(opts.schema_prefix):
            continue
        full = str(name) if "." in str(name) else f"{opts.catalog}.{name}"
        catalog_part = full.split(".", 1)[0]
        if catalog_part != opts.catalog:
            continue
        require_ident(short, "schema")
        out.append(full)
    return out


def _strip_dev_prefix(name: str) -> str:
    """`[dev <x>] ow_tp_foo` -> `ow_tp_foo`; dev deployments prefix the name."""
    if name.startswith("[dev ") and "] " in name:
        return name.split("] ", 1)[1]
    return name


def _order_branches_children_first(branches: list[dict]) -> list[dict]:
    """Children before parents: a branch whose source_branch is another
    candidate sorts after it. Falls back to reverse create_time when the
    source_branch field is absent from the payload."""
    names = {b.get("branch_id") for b in branches}

    def source_id(branch: dict) -> str:
        src = branch.get("source_branch") or branch.get("status", {}).get("source_branch") or ""
        return src.rsplit("/", 1)[-1] if src else ""

    if not any(source_id(b) for b in branches):
        return sorted(branches, key=lambda b: b.get("create_time", ""), reverse=True)

    children: dict[str, list] = {}
    roots: list[dict] = []
    for branch in branches:
        parent_id = source_id(branch)
        if parent_id in names:
            children.setdefault(parent_id, []).append(branch)
        else:
            roots.append(branch)
    # newest first among siblings and roots, so branches with unknown parents are
    # visited before older ones that might secretly depend on them
    by_newest = lambda b: b.get("create_time", "")  # noqa: E731
    roots.sort(key=by_newest, reverse=True)
    for siblings in children.values():
        siblings.sort(key=by_newest, reverse=True)

    ordered: list[dict] = []

    def visit(branch: dict) -> None:  # post-order: descendants before their source
        for child in children.get(branch.get("branch_id"), []):
            visit(child)
        ordered.append(branch)

    for root in roots:
        visit(root)
    return ordered


def _prefix_guards(p: Plan, inventory: dict, opts: Opts) -> None:
    """Refuse prefixes broad enough to reach protected objects — the name match is
    `startswith`, so any prefix *of* a protected name is itself dangerous. Runs in
    plan() so a bad flag is an exit-2 plan error in dry-run too."""
    for label, value in (("--schema-prefix", opts.schema_prefix),
                         ("--job-prefix", opts.job_prefix),
                         ("--branch-prefix", opts.branch_prefix)):
        if len(value) < 3:
            p.errors.append(f"{label} {value!r} is too short (min 3 chars)")
    for name in PROTECTED_SCHEMA_NAMES:
        if name.startswith(opts.schema_prefix):
            p.errors.append(
                f"--schema-prefix {opts.schema_prefix!r} is a prefix of protected schema {name!r}")
            break
    for name in PROTECTED_BRANCH_NAMES:
        if name.startswith(opts.branch_prefix):
            p.errors.append(
                f"--branch-prefix {opts.branch_prefix!r} is a prefix of protected branch {name!r}")
            break
    for branch in inventory.get("lakebase_branches", []):
        bid, status = branch.get("branch_id", ""), branch.get("status", {})
        if bid.startswith(opts.branch_prefix) and (status.get("default") or status.get("is_protected")):
            p.errors.append(
                f"--branch-prefix {opts.branch_prefix!r} matches protected/default branch {bid!r}")
            break
    for name in (SHOWCASE_JOB_PREFIX, SHOWCASE_PIPELINE_PREFIX, *SHOWCASE_DASHBOARD_PREFIXES):
        # a job prefix too short to reach the ow_tp_ boundary can't tell run objects
        # from showcase objects; prefixes at/inside ow_tp_ only ever select run names
        # or the already-excluded showcase ones
        if name.startswith(opts.job_prefix) and not opts.job_prefix.startswith("ow_tp_"):
            p.errors.append(
                f"--job-prefix {opts.job_prefix!r} is a prefix of showcase name {name!r}")
            break


def plan(inventory: dict, opts: Opts) -> Plan:
    """Pure: inventory -> Plan. inventory carries schemas (existing full names),
    jobs, pipelines, dashboards, lakebase_branches, oracle_instance."""
    p = Plan()
    _prefix_guards(p, inventory, opts)

    for job in inventory.get("jobs", []):
        name = job.get("settings", {}).get("name", "")
        if name.startswith(opts.job_prefix) and not name.startswith(SHOWCASE_JOB_PREFIX):
            p.add("job", name, f"POST /api/2.2/jobs/delete job_id={job['job_id']}",
                  str(job["job_id"]))

    for pipe in inventory.get("pipelines", []):
        name = _strip_dev_prefix(pipe.get("name", ""))
        if name.startswith(opts.job_prefix) and not name.startswith(SHOWCASE_PIPELINE_PREFIX):
            p.add("pipeline", pipe.get("name", ""), f"DELETE /api/2.0/pipelines/{pipe['pipeline_id']}",
                  pipe["pipeline_id"])

    for dash in inventory.get("dashboards", []):
        name = dash.get("display_name", "")
        if name.startswith("ow_tp") and not name.startswith(SHOWCASE_DASHBOARD_PREFIXES):
            p.add("dashboard", name, f"DELETE /api/2.0/lakeview/dashboards/{dash['dashboard_id']}",
                  dash["dashboard_id"])

    for full in _run_schemas(inventory.get("schemas", []), opts):
        p.add("schema", full, f"DROP SCHEMA {full} CASCADE")

    branches = []
    for branch in inventory.get("lakebase_branches", []):
        bid = branch.get("branch_id", "")
        status = branch.get("status", {})
        if not bid.startswith(opts.branch_prefix):
            continue
        if not BRANCH_ID_RE.fullmatch(bid):
            p.errors.append(f"lakebase branch id {bid!r} is not a safe URL segment; refusing")
            continue
        if bid == "production" or status.get("default") or status.get("is_protected"):
            p.errors.append(
                f"lakebase branch {bid} matches --branch-prefix but is "
                f"{'default' if status.get('default') or bid == 'production' else 'protected'}; refusing")
            continue
        branches.append(branch)
    for branch in _order_branches_children_first(branches):
        bid = branch["branch_id"]
        p.add("lakebase_branch", bid,
              f"DELETE /api/2.0/postgres/projects/{opts.lakebase_project}/branches/{bid}")

    if opts.start_oracle:
        instance = inventory.get("oracle_instance")
        if instance is None:
            p.errors.append(f"--start-oracle: instance {opts.start_oracle} not found in describe-instances")
        else:
            p.add("oracle", opts.start_oracle, "aws ec2 start-instances + wait + TCP poll :1521")

    return p


def print_plan(p: Plan) -> None:
    print(f"{'kind':<16} {'name':<50} action")
    print("-" * 100)
    for item in p.items:
        print(f"{item.kind:<16} {item.name:<50} {item.action}")
    if not p.items:
        print("(empty plan — nothing to reset)")
    for err in p.errors:
        print(f"PLAN ERROR: {err}")


def inventory(dbx: Databricks, opts: Opts) -> dict:
    inv: dict = {}
    inv["jobs"] = dbx.list_all("/api/2.2/jobs/list", "jobs")
    inv["pipelines"] = dbx.list_all("/api/2.0/pipelines", "statuses", "pipelines")
    inv["dashboards"] = dbx.list_all("/api/2.0/lakeview/dashboards", "dashboards")
    inv["schemas"] = dbx.sql_ok(f"SHOW SCHEMAS IN {opts.catalog}").rows
    if opts.lakebase_project:
        payload = dbx.ok("GET", f"{_project_url(opts)}/branches")
        inv["lakebase_branches"] = payload.get("branches", payload.get("_list", []))
    if opts.start_oracle:
        inv["oracle_instance"] = _describe_instance(opts.start_oracle)
    return inv


def _project_url(opts: Opts) -> str:
    return f"/api/2.0/postgres/projects/{urllib.parse.quote(opts.lakebase_project, safe='')}"


def _describe_instance(instance_id: str) -> dict | None:
    out = subprocess.run(
        ["aws", "ec2", "describe-instances", "--instance-ids", instance_id,
         "--region", os.environ.get("AWS_REGION", "us-east-1"), "--output", "json"],
        capture_output=True, text=True)
    if out.returncode != 0:
        return None
    for res in json.loads(out.stdout).get("Reservations", []):
        for inst in res.get("Instances", []):
            return inst
    return None


def _start_oracle(instance_id: str) -> str:
    region = os.environ.get("AWS_REGION", "us-east-1")
    subprocess.run(["aws", "ec2", "start-instances", "--instance-ids", instance_id,
                    "--region", region], check=True, capture_output=True, text=True)
    subprocess.run(["aws", "ec2", "wait", "instance-running", "--instance-ids", instance_id,
                    "--region", region], check=True, capture_output=True, text=True)
    instance = _describe_instance(instance_id) or {}
    ip = instance.get("PublicIpAddress")
    if not ip:
        raise DbxError(f"{instance_id} started but has no public IP to poll")
    deadline = time.time() + 300
    while time.time() < deadline:
        try:
            with socket.create_connection((ip, 1521), timeout=5):
                return f"{instance_id} running, {ip}:1521 reachable"
        except OSError:
            time.sleep(10)
    raise DbxError(f"{instance_id} running but {ip}:1521 not reachable within 5 min")


def apply_plan(dbx: Databricks, p: Plan, opts: Opts) -> list[str]:
    failures = []
    branch_failed: list[Item] = []
    order = {"job": 0, "pipeline": 1, "dashboard": 2, "schema": 3, "lakebase_branch": 4, "oracle": 5}
    for item in sorted(p.items, key=lambda i: order[i.kind]):
        try:
            if item.kind == "job":
                dbx.ok("POST", "/api/2.2/jobs/delete", {"job_id": int(item.resource_id)})
            elif item.kind == "pipeline":
                dbx.ok("DELETE", f"/api/2.0/pipelines/{urllib.parse.quote(item.resource_id, safe='')}")
            elif item.kind == "dashboard":
                dbx.ok("DELETE",
                       f"/api/2.0/lakeview/dashboards/{urllib.parse.quote(item.resource_id, safe='')}")
            elif item.kind == "schema":
                result = dbx.sql(item.action)
                if not result.ok:
                    raise DbxError(f"{item.action} -> {result.state}: {result.error[:300]}")
            elif item.kind == "lakebase_branch":
                dbx.ok("DELETE",
                       f"{_project_url(opts)}/branches/{urllib.parse.quote(item.name, safe='')}")
            elif item.kind == "oracle":
                detail = _start_oracle(item.name)
                print(f"  {item.kind} {item.name}: {detail}")
                continue
            print(f"  {item.kind} {item.name}: OK")
        except Exception as exc:  # noqa: BLE001 - collect and continue
            if item.kind == "lakebase_branch":
                branch_failed.append(item)  # retried once after the rest run below
            failures.append(f"{item.kind} {item.name}: {exc}")
            print(f"  {item.kind} {item.name}: FAIL {exc}")
    for item in branch_failed:
        # one retry after every other branch delete ran — a child that failed for
        # ordering reasons now has its descendants gone
        try:
            dbx.ok("DELETE",
                   f"{_project_url(opts)}/branches/{urllib.parse.quote(item.name, safe='')}")
            failures.remove(next(f for f in failures if f.startswith(f"lakebase_branch {item.name}:")))
            print(f"  {item.kind} {item.name}: OK on retry")
        except Exception as exc:  # noqa: BLE001
            print(f"  {item.kind} {item.name}: retry FAIL {exc}")
    return failures


def verify(dbx: Databricks, opts: Opts) -> dict:
    survivors = {}
    jobs = [j.get("settings", {}).get("name") for j in dbx.list_all("/api/2.2/jobs/list", "jobs")
            if j.get("settings", {}).get("name", "").startswith(opts.job_prefix)
            and not j.get("settings", {}).get("name", "").startswith(SHOWCASE_JOB_PREFIX)]
    if jobs:
        survivors["jobs"] = jobs
    pipes = [p.get("name") for p in dbx.list_all("/api/2.0/pipelines", "statuses", "pipelines")
             if _strip_dev_prefix(p.get("name", "")).startswith(opts.job_prefix)
             and not _strip_dev_prefix(p.get("name", "")).startswith(SHOWCASE_PIPELINE_PREFIX)]
    if pipes:
        survivors["pipelines"] = pipes
    dashes = [d.get("display_name") for d in dbx.list_all("/api/2.0/lakeview/dashboards", "dashboards")
              if d.get("display_name", "").startswith("ow_tp")
              and not d.get("display_name", "").startswith(SHOWCASE_DASHBOARD_PREFIXES)]
    if dashes:
        survivors["dashboards"] = dashes
    result = dbx.sql(f"SHOW SCHEMAS IN {opts.catalog}")
    if result.ok:
        remaining = _run_schemas(result.rows, opts)
        if remaining:
            survivors["schemas"] = remaining
    else:
        survivors["schemas"] = [f"verify query failed: {result.state} {result.error[:200]}"]
    if opts.lakebase_project:
        status, payload = dbx.call("GET", f"{_project_url(opts)}/branches")
        if 200 <= status < 300:
            bids = [b.get("branch_id") for b in payload.get("branches", payload.get("_list", []))
                    if b.get("branch_id", "").startswith(opts.branch_prefix)]
            if bids:
                survivors["lakebase_branches"] = bids
        else:
            survivors["lakebase_branches"] = [f"verify GET -> HTTP {status}"]
    return survivors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="execute the plan (default: print only)")
    parser.add_argument("--catalog", default="ow_tp")
    parser.add_argument("--schema-prefix", default="mig_",
                        help="drop every schema in --catalog whose name carries this prefix")
    parser.add_argument("--job-prefix", default="ow_tp_")
    parser.add_argument("--lakebase-project", default="ow-tp-billing")
    parser.add_argument("--branch-prefix", default="mig-")
    parser.add_argument("--start-oracle", default="", metavar="INSTANCE_ID")
    args = parser.parse_args()

    require_ident(args.catalog, "catalog")
    opts = Opts(
        catalog=args.catalog,
        schema_prefix=args.schema_prefix,
        job_prefix=args.job_prefix,
        lakebase_project=args.lakebase_project,
        branch_prefix=args.branch_prefix,
        start_oracle=args.start_oracle,
    )
    require_ident(args.schema_prefix, "--schema-prefix")
    if not args.job_prefix:
        raise SystemExit("--job-prefix must be non-empty")
    if not args.branch_prefix:
        raise SystemExit("--branch-prefix must be non-empty")
    if args.start_oracle and not args.start_oracle.startswith("i-"):
        raise SystemExit("--start-oracle expects an EC2 instance id (i-...)")

    dbx = Databricks()
    p = plan(inventory(dbx, opts), opts)
    print_plan(p)
    if p.errors:
        return 2
    if not args.apply:
        print("dry run — pass --apply to execute")
        return 0

    failures = apply_plan(dbx, p, opts)
    survivors = verify(dbx, opts)
    print("negative verification: " + json.dumps(survivors))
    if failures:
        print(f"failures: {len(failures)}")
        for f in failures:
            print(f"  {f}")
    return 1 if failures or survivors else 0


if __name__ == "__main__":
    raise SystemExit(main())
