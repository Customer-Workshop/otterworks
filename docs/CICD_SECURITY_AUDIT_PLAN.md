# OtterWorks CI/CD Pipeline Security Audit Plan

> **Scope:** All GitHub Actions workflows, Dockerfiles (13 services + 2 frontends), Helm charts, Terraform IaC, deployment scripts, and pre-commit configuration.
>
> **Objective:** Identify and remediate security gaps across the build, scan, and deployment lifecycle to ensure no critical vulnerabilities reach production.

---

## Summary of Identified Gaps

| # | Severity | Type of Gate | Problem | Impact |
|---|----------|-------------|---------|--------|
| 1 | **CRITICAL** | CI Permissions | `ci.yml` and `security-scan.yml` have **no `permissions:` block** — jobs run with GitHub's default token permissions (write-all on push events) | Compromised step/action can write to repo, create releases, modify packages |
| 2 | **CRITICAL** | Action Version Pinning | All third-party actions use **mutable tags** (`@v4`, `@v3`, `@v5`, `@v0.36.0`) instead of full SHA pins | Supply-chain attack: a compromised tag can inject arbitrary code into CI |
| 3 | **CRITICAL** | Failure Suppression | `ci.yml` admin-dashboard job uses `npm run lint \|\| true` and `npm test \|\| true` — **lint and test failures are silently swallowed** | Broken or vulnerable code merges without any signal; defeats the purpose of CI |
| 4 | **CRITICAL** | Container Image Scanning | Docker images are **built and pushed to ECR without any vulnerability scan** (`docker-build.yml` has no Trivy/Grype/Snyk step) | Known-CVE container images deployed directly to production |
| 5 | **CRITICAL** | Deployment Artifact Integrity | No container image **signing** (cosign/Sigstore) or signature verification before deployment | Tampered images can be deployed; no proof of provenance |
| 6 | **CRITICAL** | Supply Chain Attestation | **No SLSA provenance** generated for build artifacts; no provenance validation in deployment pipeline | Cannot verify build integrity; fails SLSA compliance requirements |
| 7 | **HIGH** | Dependency Review (PR) | No `github/dependency-review-action` — newly introduced CVEs in PRs are **not blocked at merge time** (Trivy only runs post-merge and weekly) | Vulnerable dependencies merged before anyone notices; weekly scan is too late |
| 8 | **HIGH** | IaC Security Scanning | No `tfsec`, `checkov`, `tflint`, or `terrascan` in CI — Terraform changes are only `fmt`/`validate` checked, **not security-scanned** | Misconfigured IAM policies, open security groups, or unencrypted resources deployed |
| 9 | **HIGH** | SBOM Generation | No SBOM (Software Bill of Materials) generated for any service — referenced in `ARCHITECTURE.md` but **never implemented** | Cannot track transitive dependencies; fails regulatory/compliance requirements |
| 10 | **HIGH** | Security Gates (PR Blocking) | No **required status checks** or branch protection rules enforcing that security scans must pass before merge | PRs can be merged even when Trivy, Semgrep, or Gitleaks finds critical issues |
| 11 | **HIGH** | Kubernetes Security Contexts | Helm deployment templates have **no `securityContext`** — missing `runAsNonRoot`, `readOnlyRootFilesystem`, `allowPrivilegeEscalation: false` | Containers run as root in K8s; privilege escalation possible |
| 12 | **HIGH** | Deployment Environment Protection | `docker-build.yml` pushes to ECR on every `main` push and tag — **no environment protection rules**, no manual approval gate for production | Unreviewed code auto-deploys to production ECR with `:latest` tag |
| 13 | **HIGH** | Immutable Artifact Promotion | `docker-build.yml` pushes a **`:latest` mutable tag** alongside the SHA tag — production can silently receive different images | Non-deterministic deployments; impossible to audit which image is running |
| 14 | **HIGH** | Pre-Commit Security Hooks | **No `.pre-commit-config.yaml`** exists — no local security scanning (secrets detection, linting) before code is committed | Secrets and vulnerable patterns committed to repo history |
| 15 | **HIGH** | Docker Base Image Pinning | `file-service/Dockerfile` uses `rust:latest` (unpinned) — other Dockerfiles use version tags without SHA digests | Builds are non-reproducible; upstream supply-chain compromise possible |
| 16 | **HIGH** | Search Service Dockerfile | `search-service/Dockerfile` is a **single-stage build** — build tools, dev dependencies, and source code ship in the production image | Larger attack surface; unnecessary packages in production container |
| 17 | **MEDIUM** | Post-Deployment Verification | No smoke tests, health check gates, or synthetic monitors after Helm deploys — script only checks `kubectl get pods` | Deployed services may be unhealthy but marked as successful |
| 18 | **MEDIUM** | Deployment Rollback | No automated rollback on health check failure; Helm `--wait` will timeout but **failed services are skipped with a warning** (`continue...` pattern in deploy script) | Failed deployments leave cluster in partially-deployed state |
| 19 | **MEDIUM** | IaC Drift Detection | No scheduled Terraform plan to detect drift between deployed infrastructure and IaC definitions | Infrastructure can drift from code without alerting |
| 20 | **MEDIUM** | Deployment Audit Trail | No structured deployment logging (who/what/when/why); deploy script uses basic `echo` with no audit persistence | Cannot trace deployment history for incident response |
| 21 | **MEDIUM** | Secret Rotation | No automated secret rotation for `JWT_SECRET`, database passwords, or AWS credentials at runtime | Compromised secrets remain valid indefinitely |
| 22 | **MEDIUM** | Report-Service Excluded from Scans | Trivy `skip-dirs: 'services/report-service'` — legacy service is **completely excluded** from vulnerability scanning | Known vulnerabilities in Java 8 runtime go untracked |
| 23 | **MEDIUM** | Environment Segregation | `docker-compose.yml` hardcodes `JWT_SECRET` fallback value and identical `POSTGRES_PASSWORD` across all services | Local dev patterns could leak to production; shared credentials across environments |
| 24 | **MEDIUM** | OIDC for Platform Terraform | Deploy script uses `aws` CLI with ambient credentials — no explicit OIDC or short-lived credential enforcement for `terraform apply` | Long-lived AWS credentials in deploy environment increase blast radius |
| 25 | **MEDIUM** | Runtime Network Policies | Helm network policies exist but only for ingress — **no egress restriction** in any service | Compromised container can exfiltrate data to any external endpoint |
| 26 | **MEDIUM** | CI Coverage Gap: Report Service | `report-service` CI job runs with **Java 8** and has no lint step — the legacy service has lowest CI coverage | Code quality issues and vulnerabilities go undetected |

---

## Detailed Gap Analysis & Recommended Solutions

### CRITICAL Gaps

#### Gap 1: Missing Workflow Permissions (CI Permissions)

**Current State:** `ci.yml` and `security-scan.yml` declare no `permissions:` block. On `push` events to `main`, the `GITHUB_TOKEN` receives write permissions to all scopes by default.

**Risk:** If any third-party action (e.g., `dorny/paths-filter`, `aquasecurity/trivy-action`) is compromised, the attacker gains write access to repository contents, packages, deployments, and more.

**Recommended Fix:**
Add a top-level `permissions: read-all` block to both `ci.yml` and `security-scan.yml`. For jobs that need specific write access, grant permissions at the job level:

```yaml
permissions:
  contents: read

jobs:
  dependency-scan:
    permissions:
      contents: read
      security-events: write  # Only if uploading SARIF
```

**Files to modify:** `.github/workflows/ci.yml`, `.github/workflows/security-scan.yml`

---

#### Gap 2: Third-Party Actions Not Pinned to SHA

**Current State:** All actions use mutable version tags:
- `actions/checkout@v4`, `actions/setup-go@v5`, `actions/setup-java@v4`, `actions/setup-python@v5`, `actions/setup-node@v4`
- `dorny/paths-filter@v3`, `gradle/actions/setup-gradle@v3`, `dtolnay/rust-toolchain@stable`
- `aquasecurity/trivy-action@v0.36.0`, `docker/build-push-action@v5`
- `aws-actions/configure-aws-credentials@v4`, `aws-actions/amazon-ecr-login@v2`
- `ruby/setup-ruby@v1`, `hashicorp/setup-terraform@v3`, `actions/setup-dotnet@v4`

**Risk:** Tag-based references are mutable. An attacker who compromises the action repository can push malicious code under the same tag. This is the #1 supply-chain attack vector in GitHub Actions.

**Recommended Fix:** Pin every action to its full commit SHA and add a trailing comment with the human-readable version:

```yaml
- uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11 # v4.1.1
```

**Files to modify:** `.github/workflows/ci.yml`, `.github/workflows/docker-build.yml`, `.github/workflows/security-scan.yml`

---

#### Gap 3: Failure Suppression in Admin Dashboard CI

**Current State:** Lines 301-302 of `ci.yml`:
```yaml
- run: npm run lint || true
- run: npm test || true
```

**Risk:** Lint and test failures are completely ignored. Vulnerable code patterns flagged by ESLint security rules, or failing tests that catch regressions, produce zero signal. This effectively makes CI decorative for this service.

**Recommended Fix:** Remove `|| true` from both commands. If there are known lint issues, fix them or configure specific rule suppressions in `.eslintrc` rather than silencing the entire linter:

```yaml
- run: npm run lint
- run: npm test
```

**Files to modify:** `.github/workflows/ci.yml`

---

#### Gap 4: No Container Image Scanning Before ECR Push

**Current State:** `docker-build.yml` builds Docker images and pushes them directly to ECR without any vulnerability scan. The Trivy scan in `security-scan.yml` scans the filesystem (source code), not the built container images.

**Risk:** Container images may include vulnerable OS packages, libraries, or base image CVEs that are only detectable by image scanning. These are pushed to ECR and deployed to production.

**Recommended Fix:** Add a Trivy (or Grype) image scan step between `docker build` and `docker push` in `docker-build.yml`:

```yaml
- name: Scan image for vulnerabilities
  uses: aquasecurity/trivy-action@<SHA>
  with:
    image-ref: ${{ env.ECR_REGISTRY }}/otterworks-${{ matrix.service.name }}:${{ github.sha }}
    format: 'table'
    exit-code: '1'
    severity: 'CRITICAL,HIGH'
```

**Files to modify:** `.github/workflows/docker-build.yml`

---

#### Gap 5: No Container Image Signing

**Current State:** No cosign, Sigstore, or any image signing mechanism exists in the pipeline. Images are pushed to ECR unsigned.

**Risk:** There is no cryptographic proof that an image was built by this CI pipeline. A compromised ECR registry or man-in-the-middle attack could deploy tampered images.

**Recommended Fix:** Add cosign signing after the image push in `docker-build.yml`:

```yaml
- name: Sign image with cosign
  uses: sigstore/cosign-installer@<SHA>
- run: |
    cosign sign --yes \
      ${{ env.ECR_REGISTRY }}/otterworks-${{ matrix.service.name }}:${{ github.sha }}
```

Verify signatures in the deploy script before Helm upgrade.

**Files to modify:** `.github/workflows/docker-build.yml`, `scripts/deploy-dev.sh`

---

#### Gap 6: No SLSA Provenance

**Current State:** No SLSA provenance attestations are generated. `ARCHITECTURE.md` references SBOM/provenance as planned but it was never implemented.

**Risk:** Cannot prove the build was executed in a trusted environment with specific inputs. Fails SLSA Level 1+ compliance. No supply-chain integrity guarantees.

**Recommended Fix:** Add `slsa-framework/slsa-github-generator` to generate provenance for container images:

```yaml
- uses: slsa-framework/slsa-github-generator/.github/workflows/generator_container_slsa3.yml@<SHA>
```

**Files to modify:** `.github/workflows/docker-build.yml` (or new dedicated workflow)

---

### HIGH Gaps

#### Gap 7: No Dependency Review Action for PRs

**Current State:** Trivy runs on push to `main` and on a weekly schedule but there is no `github/dependency-review-action` that blocks PRs introducing new CVEs at the pull request level.

**Risk:** A developer can introduce a dependency with a known critical CVE, and the PR will merge without any blocking signal. The vulnerability is only detected after it reaches `main`.

**Recommended Fix:** Add to `security-scan.yml` (PR trigger already exists):

```yaml
  dependency-review:
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@<SHA>
      - uses: actions/dependency-review-action@<SHA>
        with:
          fail-on-severity: high
          comment-summary-in-pr: always
```

**Files to modify:** `.github/workflows/security-scan.yml`

---

#### Gap 8: No IaC Security Scanning

**Current State:** The `infrastructure` CI job only runs `terraform fmt -check`, `terraform init`, and `terraform validate`. There is no security-focused IaC scanning (tfsec, checkov, tflint).

**Risk:** Misconfigured Terraform resources (e.g., publicly accessible RDS, unencrypted S3 buckets, overly permissive IAM policies, missing logging) pass CI without detection.

**Recommended Fix:** Add `tfsec` or `checkov` scanning to the infrastructure CI job:

```yaml
- name: Run tfsec
  uses: aquasecurity/tfsec-action@<SHA>
  with:
    working_directory: infrastructure/terraform
    soft_fail: false
```

Also scan `platform/terraform/` which is currently not covered by CI at all.

**Files to modify:** `.github/workflows/ci.yml`

---

#### Gap 9: No SBOM Generation

**Current State:** `ARCHITECTURE.md` mentions "SBOM generation per service" and has a planned `sbom/` directory, but no SBOM is ever generated in CI.

**Risk:** Without SBOMs, the organization cannot inventory transitive dependencies across 11 polyglot services. This is a compliance blocker for SOC 2, FedRAMP, and executive orders on software supply chain security.

**Recommended Fix:** Add SBOM generation (via Syft or Trivy) in `docker-build.yml` after image build:

```yaml
- name: Generate SBOM
  uses: anchore/sbom-action@<SHA>
  with:
    image: ${{ env.ECR_REGISTRY }}/otterworks-${{ matrix.service.name }}:${{ github.sha }}
    format: spdx-json
    output-file: sbom-${{ matrix.service.name }}.spdx.json
- uses: actions/upload-artifact@<SHA>
  with:
    name: sbom-${{ matrix.service.name }}
    path: sbom-${{ matrix.service.name }}.spdx.json
```

**Files to modify:** `.github/workflows/docker-build.yml`

---

#### Gap 10: No Required Status Checks / Security Gate Enforcement

**Current State:** There are no branch protection rules enforcing that security scan workflows must pass before merging. The security-scan workflow runs but its results are advisory only.

**Risk:** PRs can be merged even when Trivy finds critical CVEs, Semgrep finds OWASP Top 10 violations, or Gitleaks detects committed secrets.

**Recommended Fix:** Configure GitHub branch protection for `main`:
- Require status checks: `dependency-scan`, `secret-scan`, `sast` from `security-scan.yml`
- Require all CI jobs to pass
- Require PR reviews

This is a repository settings change, not a workflow file change.

**Action required:** Repository admin must configure branch protection rules.

---

#### Gap 11: Missing Kubernetes Security Contexts in Helm Charts

**Current State:** All 13+ Helm deployment templates have zero `securityContext` configuration. No `runAsNonRoot`, `readOnlyRootFilesystem`, `allowPrivilegeEscalation`, or `capabilities` drop.

**Risk:** Despite Dockerfiles defining `USER appuser`, Kubernetes does not enforce this constraint. A container escape or misconfiguration could run processes as root with full Linux capabilities.

**Recommended Fix:** Add to every Helm `deployment.yaml`:

```yaml
spec:
  template:
    spec:
      securityContext:
        runAsNonRoot: true
        fsGroup: 1001
      containers:
        - securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            runAsUser: 1001
            capabilities:
              drop: ["ALL"]
```

**Files to modify:** All `infrastructure/helm/*/templates/deployment.yaml` files (13 charts)

---

#### Gap 12: No Deployment Environment Protection

**Current State:** `docker-build.yml` triggers on every push to `main` and on version tags. Images are pushed to ECR and tagged `:latest` with no manual approval, environment gates, or branch restrictions.

**Risk:** Any merge to `main` immediately pushes production-ready images. There is no human verification step, no staging validation, and no approval gate.

**Recommended Fix:** Use GitHub Environments with protection rules:

```yaml
jobs:
  build-and-push:
    environment:
      name: production
      url: https://otterworks.workshop.example.com
```

Configure the `production` environment in repo settings with:
- Required reviewers (at least 1)
- Wait timer (e.g., 5 minutes)
- Branch restriction (only `main` with tags matching `v*`)

**Files to modify:** `.github/workflows/docker-build.yml`, repository settings

---

#### Gap 13: Mutable `:latest` Tag in ECR

**Current State:** `docker-build.yml` pushes two tags per image:
```yaml
tags: |
  ${{ env.ECR_REGISTRY }}/otterworks-${{ matrix.service.name }}:${{ github.sha }}
  ${{ env.ECR_REGISTRY }}/otterworks-${{ matrix.service.name }}:latest
```

**Risk:** The `:latest` tag is overwritten on every push. If Helm charts or deployment scripts reference `:latest`, the running image can change without any deployment action. This breaks auditability and reproducibility.

**Recommended Fix:** Remove the `:latest` tag. Use only immutable SHA-based tags:

```yaml
tags: ${{ env.ECR_REGISTRY }}/otterworks-${{ matrix.service.name }}:${{ github.sha }}
```

**Files to modify:** `.github/workflows/docker-build.yml`

---

#### Gap 14: No Pre-Commit Security Hooks

**Current State:** No `.pre-commit-config.yaml` file exists in the repository. Developers can commit secrets, unformatted code, and vulnerable patterns without any local gate.

**Risk:** Secrets committed to git history are extremely difficult to fully remove. Without pre-commit hooks, the CI pipeline is the only line of defense, and developers get feedback much later.

**Recommended Fix:** Create `.pre-commit-config.yaml` with security-focused hooks:

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: detect-private-key
      - id: check-added-large-files
      - id: no-commit-to-branch
        args: ['--branch', 'main']
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.21.2
    hooks:
      - id: gitleaks
  - repo: https://github.com/antonbabenko/pre-commit-terraform
    rev: v1.96.1
    hooks:
      - id: terraform_fmt
      - id: terraform_tfsec
```

**Files to create:** `.pre-commit-config.yaml`

---

#### Gap 15: Unpinned / Mutable Docker Base Images

**Current State:**
- `file-service/Dockerfile`: `FROM rust:latest` (completely unpinned)
- All other Dockerfiles use version tags without SHA digests (e.g., `golang:1.22-alpine`, `python:3.12-slim`)

**Risk:** `rust:latest` changes with every Rust release. Version tags can also be overwritten. Builds are non-reproducible and vulnerable to upstream image poisoning.

**Recommended Fix:** Pin all base images to SHA digests:

```dockerfile
FROM rust:1.79-slim@sha256:<digest> AS builder
```

At minimum, replace `rust:latest` with a specific version tag immediately.

**Files to modify:** All 13 `Dockerfile` files; `services/file-service/Dockerfile` is highest priority

---

#### Gap 16: Single-Stage Docker Build for Search Service

**Current State:** `services/search-service/Dockerfile` installs dependencies and copies source code in a single stage. Build tools (`pip`, `setuptools`) and all dev dependencies remain in the production image.

**Risk:** Increased attack surface. Build tools can be exploited if the container is compromised. The image is also unnecessarily large.

**Recommended Fix:** Convert to multi-stage build matching the `document-service` pattern:

```dockerfile
FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --target=/install -r requirements.txt

FROM python:3.12-slim
COPY --from=builder /install /usr/local/lib/python3.12/site-packages
COPY . .
RUN useradd -r -u 1001 appuser
USER appuser
```

**Files to modify:** `services/search-service/Dockerfile`

---

### MEDIUM Gaps

#### Gap 17: No Post-Deployment Verification

**Current State:** `scripts/deploy-dev.sh` runs `kubectl get pods` after Helm deploys but does not validate service health endpoints, run smoke tests, or execute any functional verification.

**Recommended Fix:** Add health endpoint verification after deployment:

```bash
for service in "${ALL_SERVICES[@]}"; do
  kubectl wait --for=condition=ready pod -l app="${service}" -n "${NAMESPACE}" --timeout=120s
  # Hit health endpoint via kubectl port-forward or service DNS
done
```

**Files to modify:** `scripts/deploy-dev.sh`

---

#### Gap 18: No Automated Deployment Rollback

**Current State:** Helm `--wait` times out on failure, but the deploy script catches the error with `|| FAILED+=("${service}")` and continues deploying other services. There is no automatic rollback.

**Recommended Fix:** Add `--atomic` flag to Helm upgrade (auto-rollbacks on failure):

```bash
helm upgrade --install "${service}" "${chart_dir}" \
  --namespace "${NAMESPACE}" \
  --set image.tag="${IMAGE_TAG}" \
  --wait --atomic --timeout 5m
```

**Files to modify:** `scripts/deploy-dev.sh`

---

#### Gap 19: No IaC Drift Detection

**Current State:** No scheduled Terraform plan to detect when deployed infrastructure drifts from IaC definitions.

**Recommended Fix:** Add a scheduled workflow that runs `terraform plan` and alerts on drift:

```yaml
on:
  schedule:
    - cron: '0 8 * * *'  # Daily 8AM UTC
```

**Files to create:** `.github/workflows/terraform-drift.yml`

---

#### Gap 20: No Structured Deployment Audit Trail

**Current State:** Deploy script uses plain `echo` statements. No structured logging, no persistence to an audit store.

**Recommended Fix:** Log deployment events to the audit-service's DynamoDB table or to a CloudWatch log group with structured JSON entries including: deployer identity, image tags, Helm chart versions, and timestamps.

**Files to modify:** `scripts/deploy-dev.sh`

---

#### Gap 21: No Automated Secret Rotation

**Current State:** `JWT_SECRET` and database passwords are static values set at deployment time. No rotation mechanism exists.

**Recommended Fix:** Integrate AWS Secrets Manager with automatic rotation (Lambda-based) for database credentials. For JWT secrets, implement key rotation with overlapping validity periods.

**Files to modify:** Terraform modules, Helm values

---

#### Gap 22: Report Service Excluded from Vulnerability Scanning

**Current State:** `.trivyignore` comments note report-service is excluded via `skip-dirs`, and it uses Java 8 (EOL).

**Recommended Fix:** Remove `skip-dirs: 'services/report-service'` from Trivy config. Track known legacy CVEs in `.trivyignore` with expiration comments instead of blanket exclusion.

**Files to modify:** `.github/workflows/security-scan.yml`

---

#### Gap 23: Hardcoded Dev Secrets in Docker Compose

**Current State:** `docker-compose.yml` contains hardcoded `JWT_SECRET` fallback (`otterworks-local-dev-jwt-secret-change-me-in-production`), `SECRET_KEY_BASE`, and identical passwords across all services.

**Recommended Fix:** Move all secrets to a `.env` file (gitignored) with clearly different values per environment. Add a `.env.example` with placeholder values.

**Files to modify:** `docker-compose.yml`, create `.env.example`

---

#### Gap 24: No OIDC for Platform Terraform Deploys

**Current State:** `scripts/deploy-dev.sh` uses ambient AWS credentials with no explicit OIDC or short-lived credential requirement.

**Recommended Fix:** Document and enforce OIDC-based authentication for CI/CD Terraform operations. The `docker-build.yml` workflow already uses OIDC (`id-token: write`) — extend this pattern to Terraform workflows.

**Files to modify:** `.github/workflows/ci.yml` (infrastructure job)

---

#### Gap 25: No Egress Network Policies

**Current State:** Helm network policies restrict ingress but have no egress rules. Containers can make outbound connections to any destination.

**Recommended Fix:** Add egress network policies per service, restricting outbound traffic to only required destinations (other services, AWS endpoints, DNS):

```yaml
egress:
  - to:
      - namespaceSelector:
          matchLabels:
            name: otterworks
    ports:
      - port: 53
        protocol: UDP
```

**Files to modify:** All `infrastructure/helm/*/templates/networkpolicy.yaml` files

---

#### Gap 26: Report Service CI Has No Lint Step

**Current State:** The `report-service` CI job runs `mvn compile`, `mvn test`, `mvn package` but has no static analysis or linting step (e.g., SpotBugs, PMD, Checkstyle).

**Recommended Fix:** Add a Maven lint/SAST step:

```yaml
- run: mvn spotbugs:check -B
```

**Files to modify:** `.github/workflows/ci.yml`, `services/report-service/pom.xml`

---

## Implementation Priority

### Phase 1: Immediate (CRITICAL) — Blocks production safety
Gaps 1-6 should be fixed immediately. These represent active security risks where compromised supply chains, unscanned images, or overly permissive tokens could lead to production compromise.

### Phase 2: Short-term (HIGH) — Blocks enterprise compliance
Gaps 7-16 should be fixed within the current sprint. These close scanning coverage holes, enforce security contexts in production Kubernetes, and prevent mutable deployment artifacts.

### Phase 3: Planned (MEDIUM) — Operational maturity
Gaps 17-26 improve deployment reliability, auditability, and operational security posture. These should be tracked in the backlog and addressed in the next 2-4 sprints.
