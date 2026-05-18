# Security Auto-Remediation with Devin

## Overview

This document describes the automated security vulnerability remediation pipeline
integrated into OtterWorks. The pipeline connects the existing CI security scanning
infrastructure with Devin's AI-powered remediation capabilities, enabling automated
fixes for SAST and dependency vulnerabilities with human review in the loop.

**Goals:**
- Prevent CRITICAL and HIGH SAST vulnerabilities from reaching the release branch
- Reduce mean time to remediation per vulnerability from ~3 days to ~30 minutes
- Reduce total review cycle from ~7 days to ~6 hours
- Maintain human-in-the-loop via PR review before any merge

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Developer Workflow                           │
│                                                                     │
│   Developer creates PR:  feature-branch → main                      │
│                │                                                    │
│                ▼                                                    │
│   ┌──────────────────────────┐                                      │
│   │ Security Scan (BAU)      │  ← security-scan.yml                 │
│   │ • Trivy (dependencies)   │    Runs on every PR to main          │
│   │ • Gitleaks (secrets)     │                                      │
│   │ • Semgrep (SAST)         │                                      │
│   └──────────┬───────────────┘                                      │
│              │ Outputs SARIF artifact                                │
│              ▼                                                      │
│   ┌──────────────────────────┐                                      │
│   │ Auto-Remediation         │  ← security-remediation.yml          │
│   │ (triggered by scan)      │    Runs via workflow_run              │
│   │                          │                                      │
│   │ 1. Download SARIF        │                                      │
│   │ 2. Parse & filter        │  ← parse_scan_report.py              │
│   │ 3. Trigger Devin API     │  ← trigger_devin_remediation.py      │
│   └──────────┬───────────────┘                                      │
│              │                                                      │
│              ▼                                                      │
│   ┌──────────────────────────┐                                      │
│   │ Devin Session            │  ← Uses: security-vulnerability-     │
│   │                          │    remediation playbook               │
│   │ • Reads scan report      │                                      │
│   │ • Fixes vulnerabilities  │                                      │
│   │ • Runs unit tests        │                                      │
│   │ • IDs false positives    │                                      │
│   │ • Creates PR             │                                      │
│   └──────────┬───────────────┘                                      │
│              │                                                      │
│              ▼                                                      │
│   ┌──────────────────────────┐                                      │
│   │ Developer Review         │  ← Human-in-the-loop                 │
│   │ • Reviews Devin's PR     │                                      │
│   │ • Merges if satisfied    │                                      │
│   │ • Triggers re-scan       │  ← CI runs again on merge            │
│   └──────────────────────────┘                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Components

### 1. Security Scan Workflow (`.github/workflows/security-scan.yml`)

**Existing BAU workflow** — enhanced to produce SARIF artifacts.

| Scanner | Purpose | Output |
|---------|---------|--------|
| Trivy | Dependency CVE scanning (CRITICAL/HIGH) | Table + exit code |
| Gitleaks | Secret detection across git history | Verbose + redacted |
| Semgrep | SAST (OWASP Top 10, security audit rules) | SARIF JSON artifact |

The SARIF artifact from Semgrep is uploaded and consumed by the remediation workflow.

### 2. Auto-Remediation Workflow (`.github/workflows/security-remediation.yml`)

Triggers automatically when the Security Scan workflow completes. Steps:

1. **Download** the SARIF artifact from the triggering scan run
2. **Parse** findings using `parse_scan_report.py` — filter by severity, group by service
3. **Trigger Devin** via API if actionable vulnerabilities are found
4. **Skip** if no CRITICAL/HIGH findings (no unnecessary Devin sessions)

### 3. Scan Report Parser (`scripts/security/parse_scan_report.py`)

Transforms raw SARIF JSON into a structured remediation report:

```json
{
  "summary": {
    "total_findings": 12,
    "critical": 3,
    "high": 9,
    "services_affected": ["api-gateway", "auth-service"]
  },
  "findings_by_service": {
    "api-gateway": {
      "language": "Go",
      "findings": [
        {
          "rule_id": "go.lang.security.audit.xss...",
          "severity": "HIGH",
          "file": "services/api-gateway/internal/handler/proxy.go",
          "line": 45,
          "message": "Direct write to ResponseWriter..."
        }
      ]
    }
  }
}
```

The parser knows OtterWorks' service layout and maps file paths to services and
their primary languages, which helps Devin apply language-appropriate fixes.

### 4. Devin API Trigger (`scripts/security/trigger_devin_remediation.py`)

Calls the Devin v1 REST API to create a remediation session:
- Builds a structured natural-language prompt from the parsed report
- Includes per-service vulnerability details with file paths and code snippets
- Optionally references a playbook ID for standardized remediation steps
- Creates the session targeting the PR's source branch

### 5. Remediation Playbook (`.devin/playbooks/security-vulnerability-remediation.md`)

Standard operating procedure for Devin during remediation:
1. Read and parse the scan report
2. Understand code context for each finding
3. Classify: Remediate / False Positive / Needs Investigation
4. Apply fixes following language-specific best practices
5. Run unit tests — all must pass without modification
6. Document false positives with justification
7. Create PR against the source branch with full disposition table
8. Loop guard: if a fix breaks tests, revert and flag for human review

## Configuration

### Required Secrets (GitHub Actions)

| Secret | Purpose |
|--------|---------|
| `DEVIN_API_TOKEN` | Bearer token for Devin v1 API (create at https://app.devin.ai/settings/api) |

### Required Variables (GitHub Actions)

| Variable | Purpose | Example |
|----------|---------|---------|
| `DEVIN_ORG_ID` | Devin organization ID | `org-012fdeb7...` |
| `SECURITY_PLAYBOOK_ID` | Playbook ID for remediation | `playbook-abc123` |

### Severity Threshold

By default, only **CRITICAL** and **HIGH** findings trigger remediation. To include
MEDIUM, update the `--severity` flag in `security-remediation.yml`:

```yaml
- name: Parse scan report
  run: |
    python scripts/security/parse_scan_report.py \
      --sarif-file semgrep-results.sarif \
      --severity CRITICAL,HIGH,MEDIUM \
      --output-file remediation-report.json
```

## Onboarding New Applications

To onboard a new application into this pipeline:

1. **Add the repository** to the Devin organization
2. **Generate DeepWiki** for code understanding (automatic on first session)
3. **Verify unit test coverage** — run a Devin session to audit and improve coverage
4. **Configure secrets** — add `DEVIN_API_TOKEN` to the repo's GitHub secrets
5. **Add the workflows** — copy `security-scan.yml` and `security-remediation.yml`
6. **Adapt the scan config** — update Semgrep rules or add Checkmarx integration as needed
7. **Test** — create a PR with a known vulnerability to verify the end-to-end flow

## Mapping to Azure DevOps + Checkmarx

This demo uses GitHub Actions + Semgrep to simulate the target environment.
The mapping to the production setup is:

| Component | OtterWorks Demo | Target: Azure DevOps + Checkmarx |
|-----------|-----------------|----------------------------------|
| CI/CD Platform | GitHub Actions | Azure DevOps Pipelines |
| SAST Scanner | Semgrep (SARIF output) | Checkmarx SAST (XML/SARIF output) |
| Dependency Scanner | Trivy | Checkmarx SCA / Black Duck |
| Report Format | SARIF JSON | Checkmarx REST API or SARIF export |
| Trigger Mechanism | `workflow_run` event | ADO pipeline task (post-scan step) |
| Source Control | GitHub PRs | Azure Repos PRs or GitHub Enterprise |
| Devin Integration | `DEVIN_API_TOKEN` secret | Same — stored in ADO variable group |
| Remediation PR | GitHub PR against feature branch | Same — PR against feature branch |
| Human Review | GitHub PR review | ADO PR review or GitHub PR review |

### Key Adaptation Points

1. **Checkmarx Integration:**
   - Replace the Semgrep scan step with a Checkmarx CLI or API call
   - Use Checkmarx's SARIF export or REST API to get the scan results
   - The `parse_scan_report.py` script already handles standard SARIF;
     for Checkmarx-specific XML, add a `parse_checkmarx_xml()` function

2. **Azure DevOps Pipeline:**
   - Replace `workflow_run` trigger with an ADO pipeline task
   - Add the Devin API call as a post-scan task in the existing pipeline YAML
   - Store `DEVIN_API_TOKEN` in an ADO variable group (marked as secret)

3. **GitHub Enterprise (on-prem):**
   - If Checkmarx can push findings as GitHub Issues, Devin can read them directly
   - Alternative: export the Checkmarx report and pass it to Devin via the API prompt

## Metrics & Success Criteria

| Metric | Before | Target | How Measured |
|--------|--------|--------|-------------|
| Mean time to remediation (per vuln) | ~3 days | ~30 minutes | Time from scan to merged PR |
| Total review cycle | ~7 days | ~6 hours | Time from PR creation to all vulns resolved |
| Developer effort per vuln | ~2 hours (coding) | ~15 minutes (review only) | Time spent by human |
| False positive documentation | Manual, inconsistent | Automated, standardized | Presence of justification in PR |
| Critical/High vulns reaching release | Occasional | Zero | Release branch scan results |

## Local Development

### Running the Scan Report Parser Locally

```bash
# Run a local Semgrep scan with SARIF output
semgrep scan --config p/default --config p/owasp-top-ten \
  --sarif --output semgrep-results.sarif

# Parse the results
python scripts/security/parse_scan_report.py \
  --sarif-file semgrep-results.sarif \
  --severity CRITICAL,HIGH \
  --output-file remediation-report.json

# View the report
cat remediation-report.json | python -m json.tool
```

### Makefile Targets

```bash
make parse-scan-report SARIF_FILE=semgrep-results.sarif
make trigger-remediation REPO=owner/repo BRANCH=feature-branch
```

## Troubleshooting

| Issue | Cause | Resolution |
|-------|-------|------------|
| No SARIF artifact found | Semgrep step failed before producing output | Check Semgrep installation and config in `security-scan.yml` |
| Devin session not created | `DEVIN_API_TOKEN` not set or expired | Regenerate token at https://app.devin.ai/settings/api |
| Remediation PR targets wrong branch | Branch name not passed correctly | Verify `workflow_run.head_branch` in the trigger payload |
| False positives not documented | Playbook not referenced in session | Set `SECURITY_PLAYBOOK_ID` variable |
| Tests fail after remediation | Fix introduced a regression | Devin's loop guard should catch this — check PR description |
