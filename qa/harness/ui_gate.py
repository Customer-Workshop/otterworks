#!/usr/bin/env python3
"""Grade user-facing defects against the running client app.

The registry (qa/registry.yaml) names each defect a browser pass found, the
routes it appears on, and the Playwright spec that reproduces it. This harness
drives the loop around those specs:

    list     what is registered, which specs exist, which are still open
    repro    the spec must FAIL against the current app (the defect is real)
    verify   the spec must PASS and the finding must no longer be suppressed
    gate     every remediated finding's spec passes, and no unregistered
             console/network error appears on any swept route

Reports are written to qa/reports/ on success *and* failure paths; that
directory is git-ignored, so collect it as a CI artifact and paste the summary
into the PR.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY = REPO_ROOT / "qa" / "registry.yaml"
REPORTS = REPO_ROOT / "qa" / "reports"

# Closed set: a status outside it is an error, so a typo cannot skip a gate.
STATUSES = ("open", "remediated")


@dataclass
class Finding:
    id: str
    title: str
    severity: str
    status: str
    routes: list[str]
    spec: str
    symptom: str
    expected: str
    accepted_console_errors: list[dict[str, Any]] = field(default_factory=list)

    @property
    def remediated(self) -> bool:
        return self.status == "remediated"


@dataclass
class Registry:
    app_dir: Path
    base_url: str
    authenticated_routes: list[str]
    findings: list[Finding]

    def get(self, finding_id: str) -> Finding:
        for f in self.findings:
            if f.id == finding_id:
                return f
        known = ", ".join(f.id for f in self.findings)
        raise SystemExit(f"unknown finding {finding_id!r}; registered: {known}")


def load_registry() -> Registry:
    raw = yaml.safe_load(REGISTRY.read_text())
    app = raw["app"]
    findings: list[Finding] = []
    for entry in raw["findings"]:
        status = entry["status"]
        if status not in STATUSES:
            raise SystemExit(
                f"{entry['id']}: status {status!r} is not one of {STATUSES}"
            )
        finding = Finding(
            id=entry["id"],
            title=entry["title"],
            severity=entry["severity"],
            status=status,
            routes=entry.get("routes", []),
            spec=entry["spec"],
            symptom=entry.get("symptom", "").strip(),
            expected=entry.get("expected", "").strip(),
            accepted_console_errors=entry.get("accepted_console_errors", []) or [],
        )
        if finding.remediated and finding.accepted_console_errors:
            raise SystemExit(
                f"{finding.id}: remediated findings may not keep "
                "accepted_console_errors — the gate must enforce them"
            )
        findings.append(finding)
    return Registry(
        app_dir=REPO_ROOT / app["dir"],
        base_url=os.environ.get("BASE_URL", app["base_url"]),
        authenticated_routes=app["authenticated_routes"],
        findings=findings,
    )


def spec_path(reg: Registry, finding: Finding) -> Path:
    return reg.app_dir / finding.spec


def write_accepted(reg: Registry) -> Path:
    """Publish the suppressions the console gate is allowed to ignore.

    Only findings still `open` contribute. The spec defaults to suppressing
    nothing when the file is absent, so it fails closed when run on its own.
    """
    REPORTS.mkdir(parents=True, exist_ok=True)
    accepted = [
        {"finding": f.id, **rule}
        for f in reg.findings
        if not f.remediated
        for rule in f.accepted_console_errors
    ]
    path = REPORTS / "accepted-console.json"
    path.write_text(
        json.dumps(
            {"routes": reg.authenticated_routes, "accepted": accepted}, indent=2
        )
        + "\n"
    )
    return path


def run_playwright(reg: Registry, specs: list[str], accepted: Path | None) -> tuple[int, str]:
    npx = shutil.which("npx")
    if npx is None:
        raise SystemExit("npx not found: install Node.js and run npm install in " + str(reg.app_dir))
    env = dict(os.environ, BASE_URL=reg.base_url)
    if accepted is not None:
        env["UI_ACCEPTED_CONSOLE"] = str(accepted)
    cmd = [npx, "playwright", "test", "--reporter=line", *specs]
    print(f"$ (cd {reg.app_dir.relative_to(REPO_ROOT)} && {' '.join(cmd)})", flush=True)
    proc = subprocess.run(
        cmd, cwd=reg.app_dir, env=env, capture_output=True, text=True
    )
    output = proc.stdout + proc.stderr
    print(output, end="", flush=True)
    return proc.returncode, output


def write_report(name: str, payload: dict[str, Any], lines: list[str]) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / f"{name}.json").write_text(json.dumps(payload, indent=2) + "\n")
    (REPORTS / f"{name}.md").write_text("\n".join(lines) + "\n")
    print(f"\nreport: qa/reports/{name}.md (and .json)")


def cmd_list(reg: Registry, _args: argparse.Namespace) -> int:
    rows = []
    for f in reg.findings:
        exists = spec_path(reg, f).exists()
        rows.append(
            {
                "id": f.id,
                "severity": f.severity,
                "status": f.status,
                "spec": f.spec,
                "spec_present": exists,
                "routes": f.routes,
                "title": f.title,
            }
        )
    width = max(len(r["id"]) for r in rows)
    print(f"{'FINDING'.ljust(width)}  SEV      STATUS      SPEC     TITLE")
    for r in rows:
        spec = "present" if r["spec_present"] else "MISSING"
        print(
            f"{r['id'].ljust(width)}  {r['severity']:<7}  {r['status']:<10}  "
            f"{spec:<7}  {r['title']}"
        )
    pending = [r["id"] for r in rows if not r["spec_present"]]
    if pending:
        print(f"\nno reproduction spec yet: {', '.join(pending)}")
    return 0


def cmd_repro(reg: Registry, args: argparse.Namespace) -> int:
    finding = reg.get(args.finding)
    path = spec_path(reg, finding)
    if not path.exists():
        print(
            f"{finding.id}: no reproduction spec at {finding.spec}.\n"
            "Write the spec first: it must assert the *expected* behavior, so it\n"
            "fails while the defect is present and passes once it is fixed.",
            file=sys.stderr,
        )
        return 2
    code, output = run_playwright(reg, [finding.spec], write_accepted(reg))
    reproduced = code != 0
    lines = [
        f"# Reproduction — {finding.id}",
        "",
        f"- Target: {reg.base_url}",
        f"- Spec: `{finding.spec}`",
        f"- Result: **{'reproduced (spec failed, as it must)' if reproduced else 'NOT reproduced (spec passed)'}**",
        "",
        f"Symptom: {finding.symptom}",
        "",
        f"Expected: {finding.expected}",
    ]
    write_report(f"repro-{finding.id.lower()}", {
        "finding": finding.id, "stage": "repro", "reproduced": reproduced,
        "exit_code": code, "target": reg.base_url, "output_tail": output[-4000:],
    }, lines)
    if not reproduced:
        print(
            f"\n{finding.id}: the spec passed, so it does not reproduce the defect.\n"
            "Either the spec asserts something the app already does, or you are\n"
            "pointed at a target that does not exhibit it. Fix that before fixing code.",
            file=sys.stderr,
        )
        return 1
    print(f"\n{finding.id}: reproduced against {reg.base_url}.")
    return 0


def cmd_verify(reg: Registry, args: argparse.Namespace) -> int:
    finding = reg.get(args.finding)
    path = spec_path(reg, finding)
    if not path.exists():
        print(f"{finding.id}: no spec at {finding.spec}", file=sys.stderr)
        return 2
    problems: list[str] = []
    if not finding.remediated:
        problems.append(
            f"{finding.id} is still `status: open` in qa/registry.yaml. Set it to "
            "`remediated` and drop its accepted_console_errors so the console gate "
            "starts enforcing it."
        )
    code, output = run_playwright(reg, [finding.spec], write_accepted(reg))
    if code != 0:
        problems.append(f"{finding.id}: spec {finding.spec} still fails")
    lines = [
        f"# Verification — {finding.id}",
        "",
        f"- Target: {reg.base_url}",
        f"- Spec: `{finding.spec}` — {'pass' if code == 0 else 'FAIL'}",
        f"- Registry status: `{finding.status}`",
        "",
        f"Expected behavior under contract: {finding.expected}",
    ]
    if problems:
        lines += ["", "## Blocking", ""] + [f"- {p}" for p in problems]
    write_report(f"verify-{finding.id.lower()}", {
        "finding": finding.id, "stage": "verify", "spec_passed": code == 0,
        "status": finding.status, "problems": problems,
        "target": reg.base_url, "output_tail": output[-4000:],
    }, lines)
    if problems:
        print("\n" + "\n".join(problems), file=sys.stderr)
        return 1
    print(f"\n{finding.id}: verified against {reg.base_url}.")
    return 0


def cmd_gate(reg: Registry, _args: argparse.Namespace) -> int:
    accepted = write_accepted(reg)
    specs = ["e2e/ui-console-gate.spec.ts"]
    graded = [f for f in reg.findings if f.remediated]
    missing = [f.id for f in graded if not spec_path(reg, f).exists()]
    specs += [f.spec for f in graded if spec_path(reg, f).exists()]
    code, output = run_playwright(reg, specs, accepted)
    problems: list[str] = []
    if missing:
        problems.append(
            "remediated findings without a spec: " + ", ".join(missing)
        )
    if code != 0:
        problems.append("the graded suite failed (see the output above)")
    lines = [
        "# UI gate",
        "",
        f"- Target: {reg.base_url}",
        f"- Routes swept: {', '.join(reg.authenticated_routes)}",
        f"- Graded findings: {', '.join(f.id for f in graded) or 'none'}",
        f"- Suppressed (still open): "
        f"{', '.join(f.id for f in reg.findings if not f.remediated) or 'none'}",
        f"- Result: **{'PASS' if not problems else 'FAIL'}**",
    ]
    if problems:
        lines += ["", "## Blocking", ""] + [f"- {p}" for p in problems]
    write_report("ui-gate", {
        "stage": "gate", "target": reg.base_url, "passed": not problems,
        "graded": [f.id for f in graded], "problems": problems,
        "generated_at": int(time.time()), "output_tail": output[-8000:],
    }, lines)
    if problems:
        print("\n" + "\n".join(problems), file=sys.stderr)
        return 1
    print("\nUI gate passed.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list registered findings and their specs")
    for name, help_text in (
        ("repro", "require the finding's spec to fail (defect is real)"),
        ("verify", "require the finding's spec to pass and its suppression to be gone"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--finding", required=True)
    sub.add_parser("gate", help="run the console gate plus every remediated finding's spec")
    args = parser.parse_args(argv)
    reg = load_registry()
    handlers = {
        "list": cmd_list, "repro": cmd_repro, "verify": cmd_verify, "gate": cmd_gate,
    }
    return handlers[args.command](reg, args)


if __name__ == "__main__":
    sys.exit(main())
