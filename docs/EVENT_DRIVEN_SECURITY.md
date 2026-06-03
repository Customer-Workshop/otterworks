# Event-Driven Security Remediation Architecture

## Overview

OtterWorks uses an event-driven SAST pipeline where security findings detected
in pull requests are automatically routed to Devin for remediation. The pipeline
runs without manual intervention for straightforward dependency upgrades and
escalates to human reviewers when automated fixes are insufficient.

## Flow

```
Developer opens PR against main
        │
        ▼
GitHub Actions: sast-auto-remediate.yml
        │
        ├── Is PR author devin-ai-integration[bot]?
        │       YES → skip (prevent infinite loop)
        │       NO  → continue
        │
        ▼
Trivy filesystem scan (HIGH + CRITICAL severity)
        │
        ├── Findings = 0 → pass, no action
        │
        ├── Findings > 0, attempts < MAX_FIX_ATTEMPTS
        │       │
        │       ├── Post findings summary as PR comment
        │       └── Call Devin API with:
        │               • branch ref
        │               • structured findings summary
        │               • remediation instructions
        │                       │
        │                       ▼
        │               Devin checks out branch,
        │               upgrades dependencies,
        │               runs service tests,
        │               pushes fix commit
        │                       │
        │                       ▼
        │               Push triggers re-scan (synchronize event)
        │               → loop back to top
        │
        └── Findings > 0, attempts >= MAX_FIX_ATTEMPTS
                │
                ├── Open GitHub Issue with remaining findings
                └── Comment on PR: escalated to human review
```

## Bot-Loop Prevention

The workflow checks `github.event.pull_request.user.login` against
`devin-ai-integration[bot]`. PRs opened by Devin are never scanned by this
workflow. For Devin's *commits* on human-authored PRs, the `synchronize` event
still fires but the author check passes (it is the human's PR), so the re-scan
runs — which is the desired closed-loop behavior.

A secondary guard counts how many commits Devin has already made on the PR. If
that count reaches `MAX_FIX_ATTEMPTS` (default: 2), the pipeline stops
triggering Devin and escalates instead.

## Escalation Policy

When automated remediation is exhausted:

1. A GitHub Issue is created with the `security` and `needs-human-review` labels
2. The issue body contains the full findings summary
3. A PR comment notifies the developer that manual review is required

## Scan Configuration

| Setting | Value | Source |
|---------|-------|--------|
| Scanner | Trivy | `.github/workflows/sast-auto-remediate.yml` |
| Severity filter | CRITICAL, HIGH | `SEVERITY_THRESHOLD` env var |
| Excluded dirs | `services/report-service` | Legacy Java 8 service (separate upgrade track) |
| Suppressions | `.trivyignore` | Acknowledged CVEs with documented justification |
| Trivy config | `security/scanning/trivy-config.yaml` | Severity and format settings |

## Services Covered

| Service | Language | Manifest | Scan Target |
|---------|----------|----------|-------------|
| api-gateway | Go 1.22 | `go.mod` | Go modules |
| auth-service | Java 17 | `build.gradle` | Gradle dependencies |
| file-service | Rust | `Cargo.toml` | Cargo crates |
| document-service | Python 3.12 | `pyproject.toml` | Poetry packages |
| collab-service | Node.js 20 | `package.json` | npm packages |
| notification-service | Kotlin | `build.gradle.kts` | Gradle dependencies |
| search-service | Python 3 | `requirements.txt` | pip packages |
| analytics-service | Scala 3.4 | `build.sbt` | sbt dependencies |
| admin-service | Ruby 3.3 | `Gemfile` | Bundler gems |
| audit-service | C# 12 | `AuditService.csproj` | NuGet packages |
| report-service | Java 8 | `pom.xml` | **Excluded** (legacy upgrade track) |

## Extending to Snyk or SonarQube

The pipeline is scanner-agnostic. To swap or add scanners:

**Snyk:** Replace the Trivy step with `snyk/actions/node@master` (or the
appropriate ecosystem action). Parse `snyk test --json` output for `severity`
fields. The Devin prompt structure stays the same.

**SonarQube:** Add a `sonarqube-scan` step that runs
`sonar-scanner -Dsonar.qualitygate.wait=true`. Parse the
`/api/qualitygates/project_status` response. Route `ERROR` status findings to
Devin with the SonarQube issue keys and descriptions.

In either case, the Devin API call, bot-loop prevention, and escalation logic
remain unchanged.
