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
from pathlib import Path, PurePosixPath, PureWindowsPath

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


DECLARED_AT = re.compile(r"p\d+ wave \d+$")
PLACEHOLDER = re.compile(r"^(todo|tbd|tba|n/?a|none|fixme|xxx|\.+)$", re.IGNORECASE)
MIN_REASON = 80


def check_no_data_movement(path: Path, unit: str, where: str) -> None:
    """A unit with no mapping spec must say, in a checkable file, why it needs none.

    The exemption this file grants is the thing that removes a unit from reconciliation,
    so it is checked rather than taken on trust: the unit has to match, the reason has to
    be prose rather than a placeholder, every evidence entry has to be a repo path that
    exists, and the wave has to be named in the form the manifests use.
    """
    if not path.exists():
        raise SystemExit(f"{where}: unit {unit} has neither a mapping spec nor a "
                         "no_data_movement.json declaring why it needs none")
    try:
        declaration = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{where}: {path.name} for {unit} is not valid JSON: {exc}") from exc
    if not isinstance(declaration, dict):
        raise SystemExit(f"{where}: {path.name} for {unit} must be a JSON object")
    if declaration.get("unit") != unit:
        raise SystemExit(f"{where}: {path.name} declares unit "
                         f"{declaration.get('unit')!r}, not {unit!r}")

    reason = declaration.get("reason")
    if not isinstance(reason, str) or PLACEHOLDER.match(reason.strip()) \
            or len(reason.strip()) < MIN_REASON:
        raise SystemExit(f"{where}: {path.name} for {unit} needs a reason of at least "
                         f"{MIN_REASON} characters saying what the unit does instead of "
                         "moving data")

    evidence = declaration.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise SystemExit(f"{where}: {path.name} for {unit} needs an evidence list of "
                         "repo paths a reviewer can open")
    for entry in evidence:
        if not isinstance(entry, str) or not entry.strip():
            raise SystemExit(f"{where}: {path.name} for {unit} has a non-path evidence "
                            f"entry {entry!r}")
        # Evidence is a link a reviewer follows in the PR, so it is repo-relative by
        # definition: an absolute path describes one machine's checkout, and a ../ escape
        # or a symlink out of the tree resolves to a file that exists but is not in the
        # repository at all.
        if PurePosixPath(entry).is_absolute() or PureWindowsPath(entry).is_absolute():
            raise SystemExit(f"{where}: {path.name} for {unit} cites evidence by absolute "
                             f"path; use a path relative to the repository root: {entry}")
        resolved = (ROOT / entry).resolve()
        if not resolved.is_relative_to(ROOT.resolve()):
            raise SystemExit(f"{where}: {path.name} for {unit} cites evidence outside "
                             f"the repository: {entry}")
        if not resolved.exists():
            raise SystemExit(f"{where}: {path.name} for {unit} cites evidence that does "
                             f"not exist in the repo: {entry}")

    declared_at = declaration.get("declared_at")
    if not isinstance(declared_at, str) or not DECLARED_AT.match(declared_at.strip()):
        raise SystemExit(f"{where}: {path.name} for {unit} needs declared_at in the form "
                         f"'p<pipeline> wave <n>', not {declared_at!r}")


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
    target_wave: dict[tuple[str, str], int] = {}
    runtime: list[tuple[str, str, int, str]] = []  # (pipeline, target, wave, where)
    # the fan-out workflow writes wave-<N>.result.json beside the manifests; only the
    # manifests are validated here. A manifest is either wave-<N>.json (pipeline 1, which
    # predates the prefix) or <pipeline>-wave-<N>.json.
    for path in sorted(p for p in WAVES.glob("*wave-*.json")
                       if re.fullmatch(r"(?:[a-z0-9]+-)?wave-\d+\.json", p.name)):
        manifest = json.loads(path.read_text())
        pipeline = manifest.get("pipeline", "p1")
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
                # A unit either maps source fields to target fields, or declares in
                # writing that it moves no data (a docs/contract unit). Silence is the
                # failure case: an unmapped unit with no declaration is one nobody can
                # reconcile.
                unit_dir = UNITS / unit
                if not (unit_dir / "mapping_spec.json").exists():
                    check_no_data_movement(unit_dir / "no_data_movement.json", unit, where)
            for target in batch["write_targets"]:
                if target in targets:
                    raise SystemExit(f"write-target collision on {target}: "
                                     f"{targets[target]} and {where}")
                targets[target] = where
                target_wave[(pipeline, target)] = manifest["wave"]
            for target in batch.get("runtime_writes", []):
                runtime.append((pipeline, target, manifest["wave"], where))
        print(f"{path.name}: ok - width {manifest['width']}, "
              f"{len(manifest['batches'])} batches, "
              f"{sum(len(b['units']) for b in manifest['batches'])} units")
    # A runtime write is DML into a table another unit owns. It is safe only when that owner
    # merged in a STRICTLY earlier wave: same-wave batches run concurrently on one Lakebase
    # branch, so two writers there race with nothing to separate them.
    # Wave numbers restart per pipeline, so the ordering is only meaningful within one.
    for pipeline, target, wave, where in runtime:
        if (pipeline, target) not in target_wave:
            raise SystemExit(f"{where}: runtime write to {target}, which no batch owns")
        if target_wave[(pipeline, target)] >= wave:
            raise SystemExit(
                f"{where}: runtime write to {target} owned by {targets[target]} in wave "
                f"{target_wave[(pipeline, target)]}; the owner must merge in an earlier wave or the two "
                "batches race on the shared branch")

    mapped = {d.name for d in UNITS.iterdir() if d.is_dir()}
    if mapped - set(placed):
        raise SystemExit(f"units with a mapping but no batch: {sorted(mapped - set(placed))}")
    print(f"{len(placed)} units placed, {len(targets)} write targets, "
          f"{len(runtime)} runtime writes, no collisions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
