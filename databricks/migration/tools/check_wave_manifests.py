#!/usr/bin/env python3
"""Validate .migration/waves/*.json with the fan-out workflow's own validator, without launching.

Extracts `validate_manifest` from the installed migration-fanout workflow the way that
skill's tests do (the module runs a wave at import time, so it cannot be imported), then
checks the capability contract against the doctor report, unit coverage, and write-target
disjointness across every wave.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WAVES = ROOT / ".migration/waves"
UNITS = ROOT / ".migration/units"
CAPS = ROOT / ".migration/09_capabilities.json"
PLUGIN = Path("/opt/.devin/plugins/cache/"
              "github.com_Cognition-Partner-Workshops_dbx-migration-plugin-5890f19a/0.2.1")
WORKFLOW = PLUGIN / "skills/migration-fanout/workflow.py"
WANTED = {"VERIFY_DEPTHS", "GUARD_MODES", "STOP_MODES", "UNIT_ID", "WORD", "ENV_NAME",
          "PARAM_VALUE"}


def validator():
    tree = ast.parse(WORKFLOW.read_text())
    selected = [n for n in tree.body
                if (isinstance(n, ast.FunctionDef) and n.name == "validate_manifest")
                or (isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id in WANTED for t in n.targets))]
    ns: dict = {"Counter": Counter, "re": re}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(WORKFLOW), "exec"), ns)
    return ns["validate_manifest"]


def main() -> int:
    validate = validator()
    doctor = json.loads(CAPS.read_text())
    placed: dict[str, str] = {}
    targets: dict[str, str] = {}
    for path in sorted(WAVES.glob("wave-*.json")):
        manifest = json.loads(path.read_text())
        validate(manifest)
        validate(manifest, doctor)
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
