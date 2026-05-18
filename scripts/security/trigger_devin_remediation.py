#!/usr/bin/env python3
"""Trigger a Devin session to remediate security vulnerabilities.

Reads the parsed remediation report (from parse_scan_report.py) and calls
the Devin v3 API to create a session that will fix the identified issues
and raise a PR against the source branch.

Usage:
    export DEVIN_API_TOKEN="..."
    python trigger_devin_remediation.py \
        --report-file remediation-report.json \
        --repo "Cognition-Partner-Workshops/otterworks" \
        --branch "feature/my-feature" \
        --playbook-id "playbook-abc123"

Environment variables:
    DEVIN_API_TOKEN   — Required. Devin API bearer token.

For Azure DevOps integration, replace the GitHub-specific references with
ADO pipeline variables. The core logic (parse report → build prompt →
call API) is the same.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests

DEVIN_API_BASE = "https://api.devin.ai/v1"


def build_remediation_prompt(
    report: dict, repo: str, branch: str
) -> str:
    """Build a natural-language prompt for Devin from the remediation report."""
    summary = report["summary"]
    services = report["findings_by_service"]

    lines: list[str] = []
    lines.append("## Security Vulnerability Remediation")
    lines.append("")
    lines.append(
        f"A SAST scan ({summary['scan_tool']}) found "
        f"**{summary['total_findings']}** actionable vulnerabilities "
        f"({summary['critical']} Critical, {summary['high']} High, "
        f"{summary['medium']} Medium) across "
        f"{len(summary['services_affected'])} service(s)."
    )
    lines.append("")
    lines.append(f"**Repository:** `{repo}`")
    lines.append(f"**Source branch:** `{branch}`")
    lines.append("")
    lines.append("Please remediate these vulnerabilities following the security "
                 "remediation playbook. For each finding:")
    lines.append("1. Read the affected code and understand the context")
    lines.append("2. Apply the fix (dependency upgrade or code change)")
    lines.append("3. If a finding is a false positive, document why")
    lines.append("4. Run the service's unit tests to verify no regressions")
    lines.append(f"5. Create a PR against `{branch}` with all fixes")
    lines.append("")
    lines.append("---")
    lines.append("")

    for service_name, service_data in services.items():
        lang = service_data["language"]
        findings = service_data["findings"]
        lines.append(f"### {service_name} ({lang}) — {len(findings)} finding(s)")
        lines.append("")

        for i, finding in enumerate(findings, 1):
            lines.append(
                f"**{i}. [{finding['severity']}] `{finding['rule_id']}`**"
            )
            lines.append(f"- File: `{finding['file']}` (line {finding['line']})")
            lines.append(f"- Message: {finding['message']}")
            if finding.get("snippet"):
                lines.append(f"- Code: `{finding['snippet'][:200]}`")
            lines.append("")

    return "\n".join(lines)


def create_devin_session(
    api_token: str,
    prompt: str,
    repo: str,
    playbook_id: str | None = None,
) -> dict:
    """Create a Devin session via the v1 API."""
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }

    payload: dict = {
        "prompt": prompt,
        "repo": repo,
    }

    if playbook_id:
        payload["playbook_id"] = playbook_id

    response = requests.post(
        f"{DEVIN_API_BASE}/sessions",
        headers=headers,
        json=payload,
        timeout=30,
    )

    if response.status_code not in (200, 201):
        print(
            f"Error creating Devin session: {response.status_code} {response.text}",
            file=sys.stderr,
        )
        sys.exit(1)

    return response.json()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Trigger a Devin remediation session from a scan report."
    )
    parser.add_argument(
        "--report-file",
        required=True,
        help="Path to the remediation report JSON (from parse_scan_report.py).",
    )
    parser.add_argument(
        "--repo",
        required=True,
        help="Repository in owner/repo format.",
    )
    parser.add_argument(
        "--branch",
        required=True,
        help="Source branch to create the remediation PR against.",
    )
    parser.add_argument(
        "--playbook-id",
        default=None,
        help="Optional Devin playbook ID for remediation instructions.",
    )
    args = parser.parse_args()

    api_token = os.environ.get("DEVIN_API_TOKEN")
    if not api_token:
        print("Error: DEVIN_API_TOKEN environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    report_path = Path(args.report_file)
    if not report_path.exists():
        print(f"Error: Report file not found: {report_path}", file=sys.stderr)
        sys.exit(1)

    with open(report_path) as f:
        report = json.load(f)

    total = report["summary"]["total_findings"]
    if total == 0:
        print("No actionable findings — skipping Devin session creation.")
        return

    print(f"Building remediation prompt for {total} finding(s)...")
    prompt = build_remediation_prompt(report, args.repo, args.branch)

    print("Creating Devin session...")
    result = create_devin_session(
        api_token=api_token,
        prompt=prompt,
        repo=args.repo,
        playbook_id=args.playbook_id,
    )

    session_id = result.get("session_id", "unknown")
    session_url = result.get("url", f"https://app.devin.ai/sessions/{session_id}")
    print(f"Devin session created: {session_url}")
    print(f"Session ID: {session_id}")


if __name__ == "__main__":
    main()
