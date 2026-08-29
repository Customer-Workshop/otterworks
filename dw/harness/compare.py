"""The equivalence gate: compare a converted asset's manifest to the frozen
legacy manifest and decide, programmatically, whether the conversion is correct.

Design rules this file exists to enforce:

* **Status comes from a closed set.** ``Status`` is an enum, and the CLI maps
  exactly one member to exit code 0. A typo cannot invent a status that a CI
  ``if`` treats as "fine", and an asset cannot be quietly reported as anything
  other than pass / fail / blocked.
* **Fingerprints gate the comparison itself.** Mismatched fingerprints are
  ``Status.BLOCKED``, never a pass and never a silent re-record: the recorded
  evidence describes different inputs, so the gate has nothing to say. An
  override requires ``--rerecord-reason`` and is echoed into the report, so a
  re-record is always attributable.
* **Reports are written on the failure path.** The diagnostic JSON is written
  before the non-zero exit, because a gate that only leaves evidence when it
  passes is a gate nobody can debug.
* **Order is compared when order is a business rule.** If the legacy manifest
  carries an ordered digest, the converted side must carry one too, over the
  same key; a missing ordered digest is a failure, not an absence of evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from manifest import Manifest


class Status(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    BLOCKED = "blocked"


PASSING = frozenset({Status.PASS})


@dataclass
class Finding:
    kind: str
    column: str | None
    legacy: object
    converted: object

    def render(self) -> str:
        where = f" [{self.column}]" if self.column else ""
        return f"{self.kind}{where}: legacy={self.legacy!r} converted={self.converted!r}"


@dataclass
class Result:
    asset: str
    status: Status
    findings: list[Finding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "asset": self.asset,
            "status": self.status.value,
            "finding_count": len(self.findings),
            "findings": [
                {
                    "kind": f.kind,
                    "column": f.column,
                    "legacy": f.legacy,
                    "converted": f.converted,
                }
                for f in self.findings
            ],
            "notes": self.notes,
        }

    def render(self) -> str:
        lines = [f"{self.asset}: {self.status.value.upper()}"]
        lines += [f"  {n}" for n in self.notes]
        lines += [f"  {f.render()}" for f in self.findings]
        return "\n".join(lines)


PROFILE_FIELDS = ("digest", "non_null", "distinct", "min", "max", "sum")

_INTEGER_TYPES = {
    "smallint", "int", "int2", "int4", "int8", "integer", "bigint", "long",
}
_DECIMAL_TYPES = {"numeric", "decimal"}
_DOUBLE_TYPES = {"float", "real", "double", "double precision"}
_TIMESTAMP_TYPES = {
    "timestamp",
    "timestamptz",
    "timestamp with time zone",
    "timestamp without time zone",
}
_BOOLEAN_TYPES = {"boolean", "bool"}
_STRING_TYPES = {
    "varchar", "char", "text", "string", "character", "character varying",
}


def _declared_scale(column: dict, base: str) -> int | None:
    scale = column.get("scale")
    if scale is not None:
        return int(scale)
    if base in _DECIMAL_TYPES:
        type_name = str(column.get("type", ""))
        if "(" in type_name and "," in type_name:
            return int(type_name.rsplit(",", 1)[1].rstrip(") "))
    return None


def canonical_type(column: dict) -> tuple[str, bool]:
    """Return a logical type and whether the source type is recognised."""
    raw = str(column.get("type", "")).strip().lower()
    base = " ".join(raw.split("(")[0].split())
    if base in _INTEGER_TYPES:
        return "integer", True
    if base in _DECIMAL_TYPES:
        scale = _declared_scale(column, base)
        return f"decimal({scale if scale is not None else 'none'})", True
    if base in _DOUBLE_TYPES:
        return "double", True
    if base == "date":
        return "date", True
    if base in _TIMESTAMP_TYPES:
        return "timestamp", True
    if base in _BOOLEAN_TYPES:
        return "boolean", True
    if base in _STRING_TYPES:
        return "string", True
    return base, False


def compare(
    legacy: Manifest,
    converted: Manifest,
    rerecord_reason: str | None = None,
) -> Result:
    asset = legacy.table
    result = Result(asset=asset, status=Status.PASS)

    if legacy.table != converted.table:
        result.findings.append(
            Finding("table", None, legacy.table, converted.table)
        )

    if legacy.fingerprint != converted.fingerprint:
        detail = Finding(
            "fingerprint", None, legacy.fingerprint, converted.fingerprint
        )
        if not rerecord_reason:
            result.status = Status.BLOCKED
            result.findings.append(detail)
            result.notes.append(
                "input fingerprints differ, so the recorded manifest "
                "describes a different estate; re-record deliberately or "
                "pass --rerecord-reason to proceed with an audited override"
            )
            return result
        result.notes.append(f"fingerprint override accepted: {rerecord_reason}")
        result.findings.append(detail)

    if legacy.row_count != converted.row_count:
        result.findings.append(
            Finding("row_count", None, legacy.row_count, converted.row_count)
        )
    if legacy.row_digest != converted.row_digest:
        result.findings.append(
            Finding("row_digest", None, legacy.row_digest, converted.row_digest)
        )

    legacy_columns = {c["name"]: c for c in legacy.columns}
    converted_columns = {c["name"]: c for c in converted.columns}
    for name in sorted(set(legacy_columns) - set(converted_columns)):
        result.findings.append(Finding("column_missing", name, "present", None))
    for name in sorted(set(converted_columns) - set(legacy_columns)):
        result.findings.append(Finding("column_added", name, None, "present"))

    for name in [c["name"] for c in legacy.columns if c["name"] in converted_columns]:
        left, right = legacy_columns[name], converted_columns[name]
        left_type, left_known = canonical_type(left)
        right_type, right_known = canonical_type(right)
        if (
            not left_known
            or not right_known
            or left_type != right_type
        ):
            result.findings.append(
                Finding("type", name, left_type, right_type)
            )
        for key in PROFILE_FIELDS:
            if left.get(key) != right.get(key):
                result.findings.append(
                    Finding(f"column_{key}", name, left.get(key), right.get(key))
                )

    if legacy.ordered is not None:
        if converted.ordered is None:
            result.findings.append(
                Finding("ordered_digest_missing", None, legacy.ordered, None)
            )
        else:
            if legacy.ordered.get("key") != converted.ordered.get("key"):
                result.findings.append(
                    Finding(
                        "ordered_key",
                        None,
                        legacy.ordered.get("key"),
                        converted.ordered.get("key"),
                    )
                )
            if legacy.ordered.get("digest") != converted.ordered.get("digest"):
                result.findings.append(
                    Finding(
                        "ordered_digest",
                        None,
                        legacy.ordered.get("digest"),
                        converted.ordered.get("digest"),
                    )
                )

    non_override = [f for f in result.findings if f.kind != "fingerprint"]
    if non_override:
        result.status = Status.FAIL
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy", required=True, type=Path)
    parser.add_argument("--converted", required=True, type=Path)
    parser.add_argument("--report", type=Path, help="where to write result JSON")
    parser.add_argument(
        "--rerecord-reason",
        help="audited justification for comparing across differing fingerprints",
    )
    args = parser.parse_args(argv)

    try:
        result = compare(
            Manifest.load(args.legacy),
            Manifest.load(args.converted),
            rerecord_reason=args.rerecord_reason,
        )
    except Exception as exc:  # a harness failure is BLOCKED, never a pass
        result = Result(
            asset=args.legacy.stem,
            status=Status.BLOCKED,
            notes=[f"harness error: {type(exc).__name__}: {exc}"],
        )

    # Written before the exit so the failure path always leaves evidence.
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result.to_dict(), indent=2) + "\n")
    print(result.render())
    return 0 if result.status in PASSING else 1


if __name__ == "__main__":
    sys.exit(main())
