#!/usr/bin/env python3
"""Validate .migration/waves/*.json with the fan-out workflow's own validator, without launching.

Extracts `validate_manifest` from the installed migration-fanout workflow the way that
skill's tests do (the module runs a wave at import time, so it cannot be imported), then
checks the capability contract against the doctor report, unit coverage, and write-target
disjointness across every wave.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WAVES = ROOT / ".migration/waves"
UNITS = ROOT / ".migration/units"
CAPS = ROOT / ".migration/09_capabilities.json"
ALLOWED = ROOT / ".migration/allowed_targets.json"
WORKFLOW_REL = "skills/migration-fanout/workflow.py"
PLUGIN_GLOB = "*dbx-migration-plugin*/*"
PLUGIN_CACHE = Path("/opt/.devin/plugins/cache")
WANTED = {"VERIFY_DEPTHS", "GUARD_MODES", "STOP_MODES", "UNIT_ID", "WORD", "ENV_NAME",
          "PARAM_VALUE"}


def find_workflow(explicit: str | None) -> Path:
    """Locate the installed migration-fanout workflow: --workflow, then $DBX_MIGRATION_PLUGIN,
    then the newest matching plugin in the cache. The path is version-dependent, so a miss is
    a configuration error with the fix in it, not a FileNotFoundError traceback."""
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    if os.environ.get("DBX_MIGRATION_PLUGIN"):
        candidates.append(Path(os.environ["DBX_MIGRATION_PLUGIN"]) / WORKFLOW_REL)
    candidates += sorted((p / WORKFLOW_REL for p in PLUGIN_CACHE.glob(PLUGIN_GLOB)), reverse=True)
    for path in candidates:
        if path.is_file():
            return path
    raise SystemExit(
        "cannot find the migration-fanout workflow. Pass --workflow <path to "
        f"{WORKFLOW_REL}>, or set DBX_MIGRATION_PLUGIN to the installed plugin version "
        f"directory (searched {PLUGIN_CACHE}/{PLUGIN_GLOB}).")


def validator(workflow: Path):
    tree = ast.parse(workflow.read_text())
    selected = [n for n in tree.body
                if (isinstance(n, ast.FunctionDef) and n.name == "validate_manifest")
                or (isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id in WANTED for t in n.targets))]
    if not any(isinstance(n, ast.FunctionDef) for n in selected):
        raise SystemExit(f"{workflow} has no validate_manifest; the installed migration-fanout "
                         "skill changed shape and this checker needs updating.")
    ns: dict = {"Counter": Counter, "re": re}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(workflow), "exec"), ns)
    return ns["validate_manifest"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workflow", help="path to the migration-fanout workflow.py")
    args = ap.parse_args()
    workflow = find_workflow(args.workflow)
    print(f"validator: {workflow}")
    validate = validator(workflow)
    doctor = json.loads(CAPS.read_text())
    allowed_branches = set(json.loads(ALLOWED.read_text())["lakebase_branches"])
    placed: dict[str, str] = {}
    targets: dict[str, str] = {}
    for path in sorted(WAVES.glob("wave-*.json")):
        manifest = json.loads(path.read_text())
        validate(manifest)
        validate(manifest, doctor)
        branch = manifest["controls"].get("lakebase_branch")
        if branch and branch not in allowed_branches:
            raise SystemExit(f"{path.name}: Lakebase branch {branch} is not in "
                             "allowed_targets.json; the guard would block the wave")
        for batch in manifest["batches"]:
            where = f"{path.name}:{batch['id']}"
            for unit in batch["units"]:
                if unit in placed:
                    raise SystemExit(f"unit {unit} in two batches: {placed[unit]} and {where}")
                placed[unit] = where
                if not (UNITS / unit / "mapping_spec.json").exists():
                    raise SystemExit(f"{where}: unit {unit} has no mapping spec")
            for target in batch["write_targets"]:
                if target in targets:
                    raise SystemExit(f"write-target collision on {target}: "
                                     f"{targets[target]} and {where}")
                targets[target] = where
        print(f"{path.name}: ok - width {manifest['width']}, "
              f"{len(manifest['batches'])} batches, "
              f"{sum(len(b['units']) for b in manifest['batches'])} units")
    mapped = {d.name for d in UNITS.iterdir() if d.is_dir()}
    if mapped - set(placed):
        raise SystemExit(f"units with a mapping but no batch: {sorted(mapped - set(placed))}")
    print(f"{len(placed)} units placed, {len(targets)} write targets, no collisions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
