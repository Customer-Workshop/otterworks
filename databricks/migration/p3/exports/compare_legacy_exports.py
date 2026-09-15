#!/usr/bin/env python3
"""Byte-compare a unit's exported report objects against the legacy's own bytes.

    python3 databricks/migration/p3/exports/compare_legacy_exports.py \
        --unit p3-analytics-daily --run-date 2026-09-15

This is the acceptance gate the plan declared for the file interface, and it is a
comparison of bytes, not of rows: row parity over the Delta tables says the numbers agree,
which is a different statement from "a consumer reading the file sees what it saw before".
Key order, indentation, gzip framing and line endings are all in scope here and in none of
the table checks.

The legacy side is the frozen manifest under `exports/legacy_objects/<unit>.json`, whose
digests were verified against the captured recon baseline when it was written. The target
side is read back from the export volume, so what is compared is what was actually
written, not what the exporter believed it wrote. The manifest names its own export root,
so a unit is compared as soon as its frozen objects exist and no shared registry has to be
edited to admit it.

A unit whose legacy behaviour differs by record shape (the audit archive: one shape writes
an archive and a report, one writes an archive and then dies, one writes nothing at all)
carries its objects under `shapes`, and the shape is a path segment under the export root.
A shape the legacy left empty is checked as empty: the gate fails if the target wrote a
file where the legacy wrote none, which no table comparison would notice.

One normalization, and only one: an object the manifest marks with a `wallclock_field`
(`generated_at`) embeds `datetime.now()`, so the target's value for that single field is
replaced by the legacy's and both sides are re-serialized identically. Everything else --
every number, every key, every byte of ordering -- still has to match exactly. The
normalization is reported in the output, so it can never be a silent weakening.

A run date the manifest does not cover is reported as `compared: false` and does not pass
as green: there is no legacy artifact for that day and the gate says so rather than
inventing one.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path

# A Databricks python task runs this through IPython, which defines no __file__, and it
# runs with the script's own directory as the working directory -- so the fallback is the
# bare name, not a path relative to the bundle root.
LEGACY_OBJECTS = (Path(globals().get("__file__", "compare_legacy_exports.py"))
                 .resolve().parent / "legacy_objects")


def units() -> list[str]:
    return sorted(p.stem for p in LEGACY_OBJECTS.glob("*.json"))


def flatten(manifest: dict) -> tuple[dict, dict]:
    """(objects keyed by path under the export root, prefixes that must hold nothing).

    A flat manifest is one run; a sharded one is a run per record shape, each under its
    own prefix. A shape with no objects is not skipped -- its prefix is returned as one
    that has to be empty on the target too.
    """
    if "shapes" not in manifest:
        return dict(manifest["objects"]), {}
    objects, empty = {}, {}
    for shape, body in sorted(manifest["shapes"].items()):
        for key, entry in sorted(body["objects"].items()):
            objects[f"{shape}/{key}"] = entry
        if not body["objects"]:
            empty[shape] = body.get(
                "reason", "the legacy wrote no object for this shape")
    return objects, empty


def normalized(body: bytes, field: str, value: str) -> bytes:
    """Swap one field's value in place, leaving every other byte as written.

    Re-serializing the parsed object would hide exactly what this gate exists to catch --
    different indentation or key order deserialized to the same dict -- so the substitution
    is textual and has to hit the field once.
    """
    obj = json.loads(body.decode("utf-8"))
    if field not in obj:
        raise SystemExit(f"the object carries no {field} to normalize")
    needle = json.dumps({field: obj[field]})[1:-1].encode("utf-8")
    if body.count(needle) != 1:
        raise SystemExit(f"{field} appears {body.count(needle)} times in the exported "
                         "object; the normalization is only safe on a single occurrence")
    return body.replace(needle, json.dumps({field: value})[1:-1].encode("utf-8"))


def download(w, path: str) -> bytes | None:
    from databricks.sdk.errors import NotFound

    try:
        return w.files.download(path).contents.read()
    except NotFound:
        return None


def listing(w, path: str) -> list[str]:
    from databricks.sdk.errors import NotFound

    try:
        return [entry.path for entry in w.files.list_directory_contents(path)]
    except NotFound:
        return []


def compare(w, unit: str, run_date: str, export_root: str | None = None) -> dict:
    manifest = json.loads((LEGACY_OBJECTS / f"{unit}.json").read_text())
    export_root = (export_root or manifest["export_root"]).rstrip("/")
    if manifest["run_date"] != run_date:
        reason = (f"the frozen legacy objects cover {manifest['run_date']}, not {run_date}; "
                  "there is nothing to compare these bytes against")
        return {"unit": unit, "run_date": run_date, "compared": False,
                "problems": [reason], "reason": reason, "verdict": "FAIL"}

    objects, empty = flatten(manifest)
    results, problems = {}, []
    for prefix, reason in sorted(empty.items()):
        found = listing(w, f"{export_root}/{prefix}")
        results[f"{prefix}/"] = {"compared": True, "matches": not found,
                                 "expected": "no objects", "reason": reason,
                                 "found": sorted(found)}
        if found:
            problems.append(f"{prefix}/: the legacy wrote nothing here and the target "
                            f"wrote {sorted(found)}")
    for key, entry in sorted(objects.items()):
        legacy = base64.b64decode(entry["raw_b64"])
        target = download(w, f"{export_root}/{key}")
        if target is None:
            results[key] = {"compared": True, "matches": False,
                            "reason": "not written to the export volume"}
            problems.append(f"{key}: missing from {export_root}")
            continue
        field = entry.get("wallclock_field")
        if field:
            left, right = normalized(target, field, entry["wallclock_value"]), legacy
        else:
            left, right = target, legacy
        results[key] = {
            "compared": True,
            "matches": left == right,
            "normalized_field": field,
            "legacy_bytes": len(legacy),
            "target_bytes": len(target),
            "legacy_sha256": hashlib.sha256(right).hexdigest(),
            "target_sha256": hashlib.sha256(left).hexdigest(),
        }
        if left != right:
            problems.append(
                f"{key}: target sha256 {results[key]['target_sha256']} != legacy "
                f"{results[key]['legacy_sha256']}")
    return {"unit": unit, "run_date": run_date, "export_root": export_root,
            "compared": True, "objects": results, "problems": problems,
            "verdict": "PASS" if not problems else "FAIL"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit", required=True, choices=units())
    ap.add_argument("--run-date", required=True)
    ap.add_argument("--export-root", default=None)
    args = ap.parse_args(argv)

    from databricks.sdk import WorkspaceClient

    result = compare(WorkspaceClient(), args.unit, args.run_date, args.export_root)
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    print()
    return 1 if result.get("problems") else 0


if __name__ == "__main__":
    if (code := main()):
        raise SystemExit(code)
