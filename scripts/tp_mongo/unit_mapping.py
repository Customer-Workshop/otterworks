#!/usr/bin/env python3
"""Create a verbatim unit subset because the approved spec is one flat 16-collection document and the harness reconciles every collection in the file it is given (--unit is only a label)."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", default=".migration/03_mapping_spec.json", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--collection", action="append", required=True)
    args = parser.parse_args()

    source = json.loads(args.spec.read_text())
    source_entries = source.get("collections", [])
    by_name = {entry["collection"]: entry for entry in source_entries}
    missing = [name for name in args.collection if name not in by_name]
    if missing:
        raise SystemExit(
            f"requested collection(s) absent from {args.spec}: {', '.join(missing)}"
        )
    requested = set(args.collection)
    selected = [
        copy.deepcopy(entry)
        for entry in source_entries
        if entry["collection"] in requested
    ]
    expected = [
        copy.deepcopy(by_name[name])
        for name in args.collection
    ]
    if set(args.collection) != {entry["collection"] for entry in selected}:
        raise AssertionError("unit mapping selection is incomplete")
    if any(
        next(entry for entry in selected if entry["collection"] == expected_entry["collection"])
        != expected_entry
        for expected_entry in expected
    ):
        raise AssertionError("unit mapping entry differs from approved source entry")

    payload = {"version": source["version"], "collections": selected}
    encoded = json.dumps(payload, indent=2) + "\n"
    if json.loads(encoded)["collections"] != selected:
        raise AssertionError("serialized unit mapping changed an approved entry")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(encoded)
    return 0


if __name__ == "__main__":
    main()
