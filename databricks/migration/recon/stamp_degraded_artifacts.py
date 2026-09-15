#!/usr/bin/env python3
"""Re-stamp DEGRADED evidence written before the stamp covered the Markdown artifacts.

`run_degraded_recon` now carries the grade into the harness's own `recon.summary.md` and
`report.md`; evidence produced earlier has the banner only in `result.json`/`DEGRADED.md`.
This walks the recon evidence tree and brings those runs up to the same shape. It is
idempotent and touches nothing that has no `DEGRADED.md` beside it.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_degraded_recon import stamp_markdown  # noqa: E402

EVIDENCE_ROOT = Path(".migration/recon")


def main() -> int:
    for unit_dir in sorted(p for p in EVIDENCE_ROOT.iterdir() if p.is_dir()):
        if (unit_dir / "DEGRADED.md").exists():
            stamp_markdown(unit_dir)
            print(f"stamped {unit_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
