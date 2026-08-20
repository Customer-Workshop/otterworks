#!/usr/bin/env python3
"""Shared parity harness for the legacy-portal decomposition.

FROZEN in Wave 0. Replays one scenario file against the monolith and against an extracted
service and asserts the two are identical after the normalisations documented in
docs/migration/contracts/README.md. A Wave 1 child adds request cases to its own scenario
file; it must not fork this harness or add a second one. If a child believes a normalisation
here is wrong it stops and reports to the parent session.

Both targets must be freshly started with empty databases: the harness derives its own
identifier mapping per side, but it cannot undo pre-existing rows.

Usage:
    tests/parity/portal/replay.py --context announcements \
        --legacy http://localhost:8095 --candidate http://localhost:8101
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import urllib.error
import urllib.request

SCENARIO_DIR = pathlib.Path(__file__).parent / "scenarios"

# Server-assigned instants differ by construction; the contracts compare presence and shape,
# not value. Sub-second precision also differs (H2/Instant vs PostgreSQL timestamp).
TIMESTAMP_FIELDS = {"createdAt", "timestamp"}
# Identifiers are compared by allocation order, not absolute value.
ID_FIELDS = {"id"}
ISO_INSTANT = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}")


class Normalizer:
    """Rewrites a side's responses into a comparable form."""

    def __init__(self) -> None:
        self._ids: dict[int, int] = {}

    def _seq(self, value: int) -> str:
        if value not in self._ids:
            self._ids[value] = len(self._ids) + 1
        return f"<id:{self._ids[value]}>"

    def apply(self, node, field: str | None = None):
        if isinstance(node, dict):
            return {k: self.apply(v, k) for k, v in node.items()}
        if isinstance(node, list):
            return [self.apply(v, field) for v in node]
        if field in TIMESTAMP_FIELDS and isinstance(node, str):
            if not ISO_INSTANT.match(node):
                return f"<not-an-instant:{node}>"
            return "<instant>"
        if field in ID_FIELDS and isinstance(node, int):
            return self._seq(node)
        return node


def request(base: str, case: dict) -> dict:
    url = base.rstrip("/") + case["path"]
    body = case.get("body")
    data = None
    headers = {}
    if body is not None:
        data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=case["method"])
    try:
        with urllib.request.urlopen(req) as resp:
            status, raw = resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        status, raw = exc.code, exc.read()
    try:
        parsed = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        parsed = {"<unparsed>": raw.decode(errors="replace")}
    return {"status": status, "body": parsed}


def replay(base: str, cases: list[dict]) -> list[dict]:
    normalizer = Normalizer()
    out = []
    for case in cases:
        result = request(base, case)
        out.append({"status": result["status"], "body": normalizer.apply(result["body"])})
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--context", required=True, choices=["announcements", "user-preferences", "feedback"])
    parser.add_argument("--legacy", default="http://localhost:8095")
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--json", help="write the full comparison to this path")
    args = parser.parse_args()

    scenario = SCENARIO_DIR / f"{args.context}.json"
    cases = json.loads(scenario.read_text())

    legacy = replay(args.legacy, cases)
    candidate = replay(args.candidate, cases)

    failures = []
    report = []
    for case, want, got in zip(cases, legacy, candidate):
        ok = want == got
        report.append({"case": case, "legacy": want, "candidate": got, "match": ok})
        label = f"{case['method']} {case['path']}"
        if ok:
            print(f"  ok   {label} -> {want['status']}")
        else:
            failures.append(label)
            print(f"  FAIL {label}")
            print(f"       legacy    {want['status']} {json.dumps(want['body'])}")
            print(f"       candidate {got['status']} {json.dumps(got['body'])}")

    if args.json:
        pathlib.Path(args.json).write_text(json.dumps(report, indent=2) + "\n")

    print(f"\n{len(cases) - len(failures)}/{len(cases)} identical for {args.context}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
