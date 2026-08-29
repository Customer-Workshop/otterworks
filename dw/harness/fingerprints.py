"""Fingerprints that decide whether two manifests may be compared at all.

A recorded manifest is only evidence about the inputs that produced it. If the
legacy asset's SQL, the DDL behind its inputs, or the seed changes, the recorded
manifest describes an estate that no longer exists -- and a gate that compares
against it is asserting something it cannot know. So every manifest carries a
fingerprint over *all* of those inputs, and the comparison refuses to run when
the two sides disagree.

The fingerprint deliberately covers three things, not one:
  * the asset source   -- the legacy ELT/DDL text being converted;
  * the schema         -- the DDL of every table the asset reads;
  * the seed           -- the data generator, because recorded row digests are a
                          function of the data, not just of the code.
It also covers the executable compatibility and manifest runtime, because
changing either changes the recorded values or what those values mean.
Covering only the source is the classic hole: a seed edit then silently
re-defines "correct" while every fingerprint still matches.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

# Bump when the normalisation or digest definition changes: old manifests then
# stop comparing as equal instead of comparing as accidentally-equal.
NORMALISATION_SPEC = "dw-harness-normalisation-v4"


def file_digest(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fingerprint(
    asset_sources: Iterable[Path],
    schema_sources: Iterable[Path],
    seed_sources: Iterable[Path],
    runtime_sources: Iterable[Path] = (),
) -> str:
    """Deterministic fingerprint over every input that can change behaviour."""
    payload = {
        "normalisation": NORMALISATION_SPEC,
        "asset": sorted(
            f"{Path(p).name}:{file_digest(p)}" for p in asset_sources
        ),
        "schema": sorted(
            f"{Path(p).name}:{file_digest(p)}" for p in schema_sources
        ),
        "seed": sorted(
            f"{Path(p).name}:{file_digest(p)}" for p in seed_sources
        ),
        "runtime": sorted(
            f"{Path(p).name}:{file_digest(p)}" for p in runtime_sources
        ),
    }
    for key in ("asset", "schema", "seed"):
        if not payload[key]:
            raise ValueError(
                f"fingerprint requires at least one {key} source -- an empty "
                "input set would make the fingerprint claim more than it knows"
            )
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
