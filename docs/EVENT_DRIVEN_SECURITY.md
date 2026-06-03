# Event-Driven Security Remediation Architecture

## Overview

OtterWorks uses an event-driven SAST pipeline where security findings detected
in pull requests are automatically routed to Devin for remediation. The pipeline
supports **two scanner paths** — Trivy (dependency CVEs) and SonarCloud (code
quality gate) — both feeding into the same Devin v3 API for autonomous fix
sessions. The pipeline runs without manual intervention for straightforward
fixes and escalates to human reviewers when automated remediation is
insufficient.

## Flow

```
Developer opens PR against main
        │
        ▼
┌───────────────────────────────────────────────────────┐
│                TWO PARALLEL SCAN PATHS                │
├─────────────────────┬─────────────────────────────────┤
│                     │                                 │
│  PATH 1: Trivy      │  PATH 2: SonarCloud             │
│  (pull_request)      │  (check_run)                    │
│                     │                                 │
│  ├ Is PR author     │  ├ Is check_run from             │
│  │ devin-bot?       │  │ sonarqubecloud app?           │
│  │  YES → skip      │  │  NO → skip                   │
│  │  NO  → scan      │  │  YES → continue               │
│  │                  │  │                                │
│  ├ Trivy fs scan    │  ├ Was quality gate FAILED?       │
│  │ HIGH+CRITICAL    │  │  NO → skip                   │
│  │                  │  │  YES → continue               │
│  ├ Findings = 0?    │  │                                │
│  │  YES → pass      │  ├ Already attempted fix?         │
│  │                  │  │  YES → skip (one-time)        │
│  ├ attempts < MAX?  │  │                                │
│  │  NO → escalate   │  │                                │
│  │                  │  │                                │
│  └─── Devin API ────┴──┴─── Devin v3 API ──────────────┤
│                                                       │
│       Devin checks out branch,                        │
│       fixes vulnerabilities,                          │
│       runs service tests,                             │
│       pushes fix commit                               │
│              │                                        │
│              ▼                                        │
│       Push triggers re-scan                           │
│       (Trivy: synchronize event)                      │
│       (SonarCloud: new check_run)                     │
│       → closed-loop verification                      │
└───────────────────────────────────────────────────────┘
```

## Scanner Paths

### Path 1: Trivy (Dependency CVEs)

Triggered by `pull_request` events (`opened`, `synchronize`). Trivy scans the
full filesystem for known dependency vulnerabilities (HIGH and CRITICAL
severity). Results are parsed into a structured findings summary and included
in the Devin prompt.

- **Re-scan loop:** Devin's fix push fires a `synchronize` event → Trivy
  re-scans automatically.
- **Escalation:** After `MAX_FIX_ATTEMPTS` (default: 2) fix cycles, a GitHub
  Issue is opened for manual review.

### Path 2: SonarCloud (Code Quality Gate)

Triggered by `check_run` events when the SonarCloud GitHub App completes its
analysis. The workflow filters for:

1. `github.event.check_run.app.slug == 'sonarqubecloud'`
2. `github.event.check_run.conclusion == 'failure'` (quality gate failed)

This path is a **one-time remediation attempt** — if Devin has already posted
a fix comment on the PR, no additional sessions are created.

- **Re-scan loop:** Devin's fix push triggers a new SonarCloud analysis via
  the GitHub App → if quality gate still fails, no new session (one-time).
- **Dashboard link:** The Devin prompt includes the SonarCloud dashboard URL
  for the specific PR.

## Bot-Loop Prevention

The workflow checks `github.event.pull_request.user.login` (Trivy path) and
`PR_AUTHOR` (SonarCloud path) against `devin-ai-integration[bot]`. PRs opened
by Devin are never scanned by this workflow. For Devin's *commits* on
human-authored PRs, the `synchronize` event still fires but the author check
passes (it is the human's PR), so the re-scan runs — which is the desired
closed-loop behavior.

**Trivy path:** A secondary guard counts Devin's commits on the PR. If that
count reaches `MAX_FIX_ATTEMPTS` (default: 2), the pipeline stops triggering
Devin and escalates instead.

**SonarCloud path:** Concurrency group `sast-fix-{pr_number}` ensures only one
remediation session per PR. A comment-based check prevents re-triggering after
the first attempt.

## Escalation Policy

When automated remediation is exhausted (Trivy path only):

1. A GitHub Issue is created with the `security` and `needs-human-review` labels
2. The issue body contains the full findings summary
3. A PR comment notifies the developer that manual review is required

## Devin API

Both paths use the **Devin v3 API** endpoint:

```
POST https://api.devin.ai/v3/organizations/{ORG_ID}/sessions
```

Request body includes:
- `prompt`: Scanner-specific remediation instructions + findings context
- `title`: Human-readable session title
- `repos`: Target repository
- `create_as_user_id`: Service user impersonation
- `tags`: Scanner type, security category

Required GitHub Actions secrets:
- `DEVIN_API_KEY` — Service user API token
- `DEVIN_ORG_ID` — Organization ID
- `DEVIN_CREATE_AS_USER_ID` — User ID for session ownership

## Scan Configuration

| Setting | Value | Source |
|---------|-------|--------|
| Trivy scanner | Trivy v0.62.2 | `.github/workflows/sast-auto-remediate.yml` |
| Trivy severity filter | CRITICAL, HIGH | `SEVERITY_THRESHOLD` env var |
| Trivy excluded dirs | `services/report-service` | Legacy Java 8 service (separate upgrade track) |
| Trivy suppressions | `.trivyignore` | Acknowledged CVEs with documented justification |
| SonarCloud project key | `Cognition-Partner-Workshops_otterworks` | `sonar-project.properties` |
| SonarCloud org | `cognition-partner-workshops` | `sonar-project.properties` |

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

## Extending to Snyk

The pipeline is scanner-agnostic. To add Snyk as a third scanner path:

Replace the Trivy step with `snyk/actions/node@master` (or the appropriate
ecosystem action). Parse `snyk test --json` output for `severity` fields. The
Devin prompt structure, bot-loop prevention, and escalation logic remain
unchanged.
