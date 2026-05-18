#!/usr/bin/env python3
"""Parse SARIF scan results into a structured remediation report for Devin.

Reads a SARIF JSON file (typically from Semgrep or another SAST tool),
filters findings by severity, groups them by OtterWorks service, and
outputs a JSON report suitable for constructing a Devin remediation prompt.

Usage:
    python parse_scan_report.py \
        --sarif-file semgrep-results.sarif \
        --severity CRITICAL,HIGH \
        --output-file remediation-report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Mapping of OtterWorks service directory prefixes to their primary language.
SERVICE_LANGUAGES: dict[str, str] = {
    "services/api-gateway": "Go",
    "services/auth-service": "Java",
    "services/file-service": "Rust",
    "services/document-service": "Python",
    "services/collab-service": "TypeScript",
    "services/notification-service": "Kotlin",
    "services/search-service": "Python",
    "services/analytics-service": "Scala",
    "services/admin-service": "Ruby",
    "services/audit-service": "C#",
    "services/report-service": "Java",
    "frontend/web-app": "TypeScript",
    "frontend/admin-dashboard": "TypeScript",
    "infrastructure/terraform": "HCL",
    "etl": "Python",
    "scripts": "Python",
}

# Semgrep severity levels mapped to a canonical set.
SEVERITY_MAP: dict[str, str] = {
    "ERROR": "HIGH",
    "WARNING": "MEDIUM",
    "INFO": "LOW",
    "NOTE": "LOW",
    "NONE": "LOW",
    # Passthrough for already-canonical values
    "CRITICAL": "CRITICAL",
    "HIGH": "HIGH",
    "MEDIUM": "MEDIUM",
    "LOW": "LOW",
}


@dataclass
class Finding:
    rule_id: str
    severity: str
    file: str
    line: int
    end_line: int
    message: str
    snippet: str = ""
    service: str = ""
    language: str = ""


@dataclass
class ServiceFindings:
    language: str
    findings: list[Finding] = field(default_factory=list)


@dataclass
class ReportSummary:
    total_findings: int = 0
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    services_affected: list[str] = field(default_factory=list)
    scan_tool: str = "semgrep"
    scan_timestamp: str = ""


@dataclass
class RemediationReport:
    summary: ReportSummary
    findings_by_service: dict[str, ServiceFindings] = field(default_factory=dict)


def detect_service(file_path: str) -> tuple[str, str]:
    """Return (service_name, language) for a file path."""
    for prefix, language in SERVICE_LANGUAGES.items():
        if file_path.startswith(prefix):
            # Use the second path component as the service name
            parts = prefix.split("/")
            service_name = parts[-1] if len(parts) > 1 else parts[0]
            return service_name, language
    return "other", "Unknown"


def normalize_severity(raw: str) -> str:
    """Normalize a SARIF/Semgrep severity to CRITICAL/HIGH/MEDIUM/LOW."""
    return SEVERITY_MAP.get(raw.upper(), "LOW")


def parse_sarif(sarif_path: str) -> list[Finding]:
    """Parse a SARIF JSON file into a list of Finding objects."""
    with open(sarif_path) as f:
        data = json.load(f)

    findings: list[Finding] = []

    for run in data.get("runs", []):
        tool_name = (
            run.get("tool", {}).get("driver", {}).get("name", "unknown")
        )

        # Build a rule-id → severity lookup from the tool's rule definitions
        rule_severity: dict[str, str] = {}
        for rule in run.get("tool", {}).get("driver", {}).get("rules", []):
            rule_id = rule.get("id", "")
            level = (
                rule.get("defaultConfiguration", {}).get("level", "WARNING")
            )
            rule_severity[rule_id] = normalize_severity(level)

        for result in run.get("results", []):
            rule_id = result.get("ruleId", "unknown")
            level = result.get("level", "")
            severity = normalize_severity(level) if level else rule_severity.get(rule_id, "MEDIUM")

            message = result.get("message", {}).get("text", "")

            for location in result.get("locations", []):
                phys = location.get("physicalLocation", {})
                artifact = phys.get("artifactLocation", {}).get("uri", "")
                region = phys.get("region", {})
                start_line = region.get("startLine", 0)
                end_line = region.get("endLine", start_line)
                snippet = region.get("snippet", {}).get("text", "")

                service_name, language = detect_service(artifact)

                findings.append(
                    Finding(
                        rule_id=rule_id,
                        severity=severity,
                        file=artifact,
                        line=start_line,
                        end_line=end_line,
                        message=message,
                        snippet=snippet.strip(),
                        service=service_name,
                        language=language,
                    )
                )

    return findings


def filter_by_severity(
    findings: list[Finding], severities: set[str]
) -> list[Finding]:
    """Filter findings to only include the specified severity levels."""
    return [f for f in findings if f.severity in severities]


def group_by_service(
    findings: list[Finding],
) -> dict[str, ServiceFindings]:
    """Group findings by OtterWorks service."""
    groups: dict[str, ServiceFindings] = {}
    for finding in findings:
        key = finding.service
        if key not in groups:
            groups[key] = ServiceFindings(language=finding.language)
        groups[key].findings.append(finding)
    return groups


def generate_report(
    findings: list[Finding], scan_tool: str = "semgrep"
) -> RemediationReport:
    """Generate a structured remediation report from parsed findings."""
    by_service = group_by_service(findings)

    severity_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for f in findings:
        severity_counts[f.severity] = severity_counts.get(f.severity, 0) + 1

    summary = ReportSummary(
        total_findings=len(findings),
        critical=severity_counts["CRITICAL"],
        high=severity_counts["HIGH"],
        medium=severity_counts["MEDIUM"],
        low=severity_counts["LOW"],
        services_affected=sorted(by_service.keys()),
        scan_tool=scan_tool,
        scan_timestamp=datetime.now(timezone.utc).isoformat(),
    )

    return RemediationReport(summary=summary, findings_by_service=by_service)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse SARIF scan results into a Devin remediation report."
    )
    parser.add_argument(
        "--sarif-file",
        required=True,
        help="Path to the SARIF JSON file.",
    )
    parser.add_argument(
        "--severity",
        default="CRITICAL,HIGH",
        help="Comma-separated severity levels to include (default: CRITICAL,HIGH).",
    )
    parser.add_argument(
        "--output-file",
        default="remediation-report.json",
        help="Output path for the remediation report JSON.",
    )
    args = parser.parse_args()

    sarif_path = Path(args.sarif_file)
    if not sarif_path.exists():
        print(f"Error: SARIF file not found: {sarif_path}", file=sys.stderr)
        sys.exit(1)

    severities = {s.strip().upper() for s in args.severity.split(",")}

    print(f"Parsing SARIF file: {sarif_path}")
    all_findings = parse_sarif(str(sarif_path))
    print(f"  Total findings in SARIF: {len(all_findings)}")

    filtered = filter_by_severity(all_findings, severities)
    print(f"  After severity filter ({', '.join(sorted(severities))}): {len(filtered)}")

    report = generate_report(filtered)

    output_path = Path(args.output_file)
    with open(output_path, "w") as f:
        json.dump(asdict(report), f, indent=2)

    print(f"  Report written to: {output_path}")
    print(f"  Services affected: {', '.join(report.summary.services_affected) or 'None'}")


if __name__ == "__main__":
    main()
