"""Emit the single-unit slice of the mapping spec that the recon harness grades.

The harness grades every collection in the spec it is handed, and a unit only owns some
of them, so each run is given the slice for its unit. The slice keeps the spec's version,
so the citation in the recon report still points at mapping spec v<version>.

    python migrations/mongodb/common/unit_spec.py U1-reference .migration/recon/U1-reference/mapping.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SPEC = Path(".migration/03_mapping_spec.json")


def slice_spec(unit: str, spec_path: Path = SPEC) -> dict:
    spec = json.loads(spec_path.read_text())
    collections = [c for c in spec["collections"] if c.get("unit") == unit]
    if not collections:
        raise SystemExit(f"no collections carry unit {unit!r} in {spec_path}")
    return {"version": spec["version"], "source_family": spec["source_family"],
            "unit": unit, "collections": collections}


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        raise SystemExit(__doc__)
    unit, out = argv[0], Path(argv[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(slice_spec(unit), indent=2) + "\n")
    print(f"{out}: {len(json.loads(out.read_text())['collections'])} collections for {unit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
