# Security scan triage — `workshop-ep-secfix`

Base: `workshop` @ `84862170`. Scanners mirror `.github/workflows/security-scan.yml`:

| Scanner | Version | Invocation |
|---|---|---|
| Trivy | 0.71.0 | `trivy fs . --severity CRITICAL,HIGH --skip-dirs services/report-service --ignorefile .trivyignore --offline-scan` |
| Semgrep | 1.176.1 | `semgrep scan --config p/owasp-top-ten --config p/security-audit` |
| Gitleaks | 8.21.2 | `gitleaks detect --source .` (history) and `--no-git` (working tree) |

Raw counts: Trivy 49 vulnerabilities (48 HIGH, 2 CRITICAL, after `.trivyignore`),
Semgrep 45 (2 ERROR, 39 WARNING, 2 INFO), Gitleaks 24 history hits / 1 in the working tree.

Severity mapping: Trivy severity as reported; Semgrep `ERROR` = HIGH, `WARNING` = MEDIUM,
`INFO` = LOW; any secret still present in the working tree = HIGH. Findings are deduplicated
on (component, package|rule, id|line).

## HIGH / CRITICAL by component

| Component | CRITICAL | HIGH | Findings |
|---|---|---|---|
| `services/admin-service` | 1 | 8 | activestorage 7.1.6 (CVE-2026-33202 **CRITICAL**, CVE-2026-33174, CVE-2026-66066), activesupport 7.1.6 (CVE-2026-33176), puma 6.6.1 (CVE-2026-47736, CVE-2026-47737), websocket-driver 0.8.0 (CVE-2026-54463, CVE-2026-54465, CVE-2026-61666) |
| `services/api-gateway` | 0 | 8 | golang.org/x/net v0.35.0 (CVE-2026-33814, CVE-2026-25681, CVE-2026-27136, CVE-2026-39821, CVE-2026-46600), golang.org/x/text v0.22.0 (CVE-2026-56852), google.golang.org/grpc v1.61.1 (GHSA-hrxh-6v49-42gf, CVE-2026-84304) |
| `services/collab-service` | 0 | 5 | @opentelemetry/propagator-jaeger 1.22.0 (CVE-2026-59892), @opentelemetry/sdk-node 0.49.1 (CVE-2026-44902), engine.io 6.6.6 (CVE-2026-59724, CVE-2026-59725), socket.io-parser 4.2.6 (CVE-2026-69185) |
| `services/document-service` | 0 | 3 | starlette 0.37.2 (CVE-2026-48818, CVE-2026-54283); Semgrep `avoid-sqlalchemy-text` — string-built SQL in `owner_stats` (`app/api/documents.py:380`, `owner_id` path param interpolated into `WHERE`) |
| `services/file-service` | 0 | 1 | rustls-webpki 0.101.7 (GHSA-82j2-j2ch-gfr8) |
| `frontend/admin-dashboard` | 0 | 9 | @angular/common, core, compiler 17.3.12 (CVE-2026-50170, CVE-2026-50171, CVE-2026-54266, CVE-2026-54268, CVE-2026-68945, CVE-2026-54267, CVE-2026-69151); Gitleaks `jwt` — hard-coded signed JWT in `src/app/core/services/auth.service.ts:81` |
| `frontend/client-app` | 0 | 5 | browserslist 4.28.2 (CVE-2026-73088, CVE-2026-73089), nanoid 3.3.16 (CVE-2026-67213), react-router 7.18.1 (GHSA-qwww-vcr4-c8h2), socket.io-parser 4.2.6 (CVE-2026-69185) |
| `demo-platform/dashboard` | 1 | 10 | tar 7.5.11 (CVE-2026-59873 **CRITICAL**, CVE-2026-59874, CVE-2026-73566), next 15.5.20 (CVE-2026-64641, CVE-2026-64645, CVE-2026-64649), postcss 8.4.31 (CVE-2026-45623, CVE-2026-73646), js-yaml 4.3.0 (GHSA-5p4m-2wfm-xmqj), nanoid 3.3.16 (CVE-2026-67213), sharp 0.34.5 (GHSA-f88m-g3jw-g9cj) |
| `.github/workflows` (repo-level, not a service) | 0 | 1 | Semgrep `gha-curl-pipe-shell` — `sast-auto-remediate.yml:64` pipes a remote install script into `sh`. Fixed on this branch. |

Clean at HIGH/CRITICAL: `analytics-service`, `audit-service`, `auth-service`, `billing-service`,
`industry-solutions`, `legacy-billing`, `legacy-portal`, `notification-service`, `search-service`,
`frontend/web-app`. `report-service` is excluded by the workflow's `--skip-dirs` (legacy Java 8
upgrade exercise).

## Not actionable in this pass

- **Gitleaks history-only hits (23):** the strings are no longer in the working tree
  (`.migration/recon/**` probe outputs, `docs/tech-partnerships/runbook-aws-portal-showcase.md`,
  `services/api-gateway/internal/config/config_test.go`, `services/collab-service/src/services/export-utils.ts`,
  `services/report-service/target/surefire-reports/*.xml`, `services/search-service/tests/test_auth_middleware.py`,
  `infrastructure/terraform-databricks/variables.tf`). Removing them needs a history rewrite of
  `workshop`, which is not safe to do from a PR. Rotate anything that was ever real.
- **Semgrep WARNING/INFO (41):** mutable action tags in `ci.yml`/`sast-auto-remediate.yml`,
  nginx `$host` use, an exported Android activity, `dangerouslySetInnerHTML` in
  `frontend/client-app/src/pages/search.tsx`, plain-http requests in `search-service`. Medium/low;
  out of scope for this HIGH/CRITICAL pass.
- **Suppressed by `.trivyignore`:** unchanged; nothing was added to it in this pass.
