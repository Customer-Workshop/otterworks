# OtterWorks CI/CD Pipeline Security Audit Plan

## Executive Summary

This audit covers the full CI/CD surface of the OtterWorks polyglot microservices platform — 11 backend services in 8 languages, 2 frontends, Terraform IaC (platform + application layers), Helm-based Kubernetes deployments, and Docker Compose local dev. The analysis covers build-time security, per-service vulnerability scanning, and deployment-time security.

---

## Identified Gaps

| # | Severity | Gate Type | Problem | Impact |
|---|----------|-----------|---------|--------|
| 1 | **CRITICAL** | CI Permissions | `ci.yml` and `security-scan.yml` have **no `permissions:` block** — they run with GitHub's default token permissions (broad `write` on everything for push events) | A compromised or injected step can write to the repo, create releases, or access secrets unnecessarily |
| 2 | **CRITICAL** | Action Pinning | All third-party actions use **mutable tags** (e.g., `actions/checkout@v4`, `aquasecurity/trivy-action@v0.36.0`) instead of full SHA pins | Supply-chain attack vector — a compromised tag can inject malicious code into every CI run |
| 3 | **CRITICAL** | Container Image Scanning | Docker images are **built and pushed to ECR without any CI-side vulnerability scan** in `docker-build.yml` — ECR `scan_on_push` runs *after* the image is already in the registry | Vulnerable images reach the registry and can be deployed before scan results are reviewed |
| 4 | **CRITICAL** | Failure Suppression | `ci.yml` admin-dashboard job has `npm run lint \|\| true` and `npm test \|\| true` — **lint and test failures are silently swallowed** | Broken or insecure code in the admin dashboard can be merged without any CI gate catching it |
| 5 | **CRITICAL** | Deployment Environment Protection | No GitHub Environment protection rules exist — `docker-build.yml` pushes to ECR on every `main` push and any `v*` tag with **no manual approval, no branch restriction, no wait timer** | Any merge to main or any tag push deploys to production without human review |
| 6 | **CRITICAL** | Helm SecurityContext | **Zero `securityContext`** in any of the 13 Helm deployment templates — no `readOnlyRootFilesystem`, `runAsNonRoot`, `allowPrivilegeEscalation: false`, or `capabilities.drop` | Containers run as root by default in K8s, with full capabilities — container escape risk |
| 7 | **HIGH** | Dependency Review | **No `github/dependency-review-action`** on PRs — Trivy runs filesystem scans but doesn't catch newly introduced CVEs at the PR diff level | New vulnerable dependencies can be introduced in PRs without being flagged before merge |
| 8 | **HIGH** | IaC Security Scanning | Terraform CI only runs `fmt -check`, `init`, and `validate` — **no `tfsec`, `checkov`, or `trivy config`** scanning for security misconfigurations | Insecure IaC changes (open security groups, unencrypted resources, overly permissive IAM) merge without detection |
| 9 | **HIGH** | SBOM Generation | **No Software Bill of Materials** is generated at build time for any service or container image | Cannot track transitive dependencies, no supply-chain transparency, blocks compliance with EO 14028 / NTIA requirements |
| 10 | **HIGH** | Pre-Commit Hooks | **No `.pre-commit-config.yaml`** exists — no local security checks (secret scanning, linting, Terraform validation) run before commits | Secrets, misconfigurations, and code quality issues reach the remote repo unchecked |
| 11 | **HIGH** | Network Policy (Egress) | Helm NetworkPolicies only define **Ingress** rules — **no Egress** policies restrict outbound traffic from any pod | A compromised container can exfiltrate data to arbitrary external endpoints |
| 12 | **HIGH** | Artifact Signing | No container image signing (cosign/Sigstore) — images are pushed to ECR unsigned | No cryptographic guarantee that the deployed image was built by the CI pipeline; image substitution attacks possible |
| 13 | **HIGH** | Terraform State Security | S3 backend has **no `encrypt = true`** and **no DynamoDB lock table** configured | State file (containing DB passwords, resource ARNs) stored unencrypted; concurrent applies can corrupt state |
| 14 | **HIGH** | Wildcard IAM Resources | `notification-service` IRSA policy has `Resource = ["*"]` for `ses:SendEmail` and `ses:SendRawEmail`; `admin-service` has `Resource = ["*"]` for CloudWatch | Violates least-privilege; a compromised service can send email from any SES identity or read any CloudWatch metrics |
| 15 | **HIGH** | Report-Service Exclusion | `report-service` is excluded from Trivy via `skip-dirs` and from `.trivyignore` by design — **no alternative scanning** covers its known Java 8 CVEs | A legacy service with known vulnerabilities runs completely unscanned — any exploitation has no detection layer |
| 16 | **MEDIUM** | Search-Service Lint Missing | `search-service` CI job runs `pytest` only — **no linter** (ruff, flake8) is configured, unlike `document-service` which uses ruff | Code quality and potential security issues in search-service code go undetected |
| 17 | **MEDIUM** | Docker Base Image Pinning | `file-service` uses `rust:latest` (unpinned), `search-service` uses `python:3.12-slim` without a multi-stage build | Non-reproducible builds; `search-service` ships with pip/setuptools/build tools in production image |
| 18 | **MEDIUM** | Immutable Artifact Promotion | `docker-build.yml` pushes both `:<sha>` and `:latest` tags — but **no promotion workflow** exists to move a tested image from staging → production | Images are rebuilt per environment or `:latest` is deployed directly, breaking artifact immutability |
| 19 | **MEDIUM** | Deployment Rollback | `deploy-dev.sh` uses `helm upgrade --install` with `--wait` but has **no automated rollback** on failure — failed services are logged but deployment continues (`|| true` pattern) | A bad deployment can leave the cluster in a partially broken state without automatic recovery |
| 20 | **MEDIUM** | Post-Deployment Verification | No smoke tests, synthetic monitors, or health-check gates run **after** Helm deploys — only `kubectl get pods` status is checked | Silent failures (service is running but returning errors) are not caught until users report issues |
| 21 | **MEDIUM** | Deployment Audit Trail | No structured deployment logging — deploy script outputs to stdout only, no immutable record of who/what/when/why | Cannot audit or forensically reconstruct deployment history |
| 22 | **MEDIUM** | Secret Rotation | No automated secret rotation for `db_password` (passed as Terraform variable), JWT secrets, or `SECRET_KEY_BASE` | Long-lived secrets increase the blast radius of a credential compromise |
| 23 | **MEDIUM** | IaC Drift Detection | No scheduled `terraform plan` or drift detection mechanism — deployed infrastructure may diverge from IaC definitions silently | Configuration drift introduces untracked security misconfigurations |
| 24 | **MEDIUM** | SLSA Provenance | No SLSA provenance attestation is generated for any build artifact | Cannot verify the build origin or integrity of deployed artifacts; blocks SLSA Level 1+ compliance |
| 25 | **MEDIUM** | EKS Public Endpoint | EKS cluster has `endpoint_public_access = true` (suppressed via `nosemgrep`) — the K8s API is internet-accessible | Increases attack surface; brute-force or credential-stuffing attacks against the K8s API |
| 26 | **MEDIUM** | Docker Compose Secrets | `docker-compose.yml` hardcodes `JWT_SECRET`, `SECRET_KEY_BASE`, and database passwords in plaintext environment variables | Developers may copy these values to production configs; secrets are visible in `docker inspect` |

---

## Detailed Gap Analysis & Recommended Solutions

### CRITICAL Findings

#### Gap 1: CI Workflow Permissions — No Least-Privilege

**Current state:** `ci.yml` and `security-scan.yml` have no `permissions:` block. On `push` events, GitHub Actions defaults to broad read/write permissions on the `GITHUB_TOKEN`.

**Risk:** A compromised or supply-chain-attacked action step inherits write access to repository contents, packages, deployments, and more.

**Recommended fix:**
Add explicit top-level permissions to both `ci.yml` and `security-scan.yml`:
```yaml
permissions:
  contents: read
  # Add specific write permissions only where needed (e.g., security-uploads for Trivy SARIF)
```

---

#### Gap 2: Third-Party Actions Use Mutable Tags

**Current state:** Every action reference uses a mutable tag: `actions/checkout@v4`, `actions/setup-go@v5`, `dorny/paths-filter@v3`, `aquasecurity/trivy-action@v0.36.0`, `docker/build-push-action@v5`, etc.

**Risk:** A malicious actor who compromises any of these upstream repos can move the tag to a malicious commit, injecting code into every CI run. This is the #1 GitHub Actions supply-chain attack vector (per GitHub's own security guidance).

**Recommended fix:**
Pin every third-party action to its full commit SHA. Example:
```yaml
- uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
```
Keep the tag as a trailing comment for human readability. Use Dependabot or Renovate to propose SHA updates.

---

#### Gap 3: No Container Image Scanning Before ECR Push

**Current state:** `docker-build.yml` builds and pushes images directly to ECR. ECR has `scan_on_push = true`, but that scan happens *after* the image is already in the registry and available for deployment.

**Risk:** Vulnerable images are stored in ECR and could be deployed by Helm/ArgoCD before ECR scan results are reviewed (there's no gate on scan results).

**Recommended fix:**
Add a Trivy container image scan step in `docker-build.yml` between `docker build` and `docker push`:
```yaml
- name: Scan image with Trivy
  uses: aquasecurity/trivy-action@<sha>
  with:
    image-ref: ${{ env.IMAGE_TAG }}
    exit-code: '1'
    severity: 'CRITICAL,HIGH'
    format: 'table'
```
This blocks the push if CRITICAL/HIGH CVEs are found.

---

#### Gap 4: Failure Suppression in Admin-Dashboard CI

**Current state:** `ci.yml` lines 301-302:
```yaml
- run: npm run lint || true
- run: npm test || true
```

**Risk:** Lint errors and test failures in the admin-dashboard are completely ignored. Security-relevant lint rules (XSS, injection patterns) and failing security-related tests will not block PRs.

**Recommended fix:**
Remove `|| true` from both commands:
```yaml
- run: npm run lint
- run: npm test
```
If there are known flaky tests or lint issues that need to be deferred, track them in a backlog rather than suppressing all failures.

---

#### Gap 5: No Deployment Environment Protection

**Current state:** `docker-build.yml` triggers on `push` to `main` and any `v*` tag. There is no GitHub Environment defined, so there are no manual approvals, required reviewers, wait timers, or branch restrictions.

**Risk:** Any merge to main automatically pushes 13 container images to ECR — effectively an unprotected deployment to production.

**Recommended fix:**
1. Create GitHub Environments (`staging`, `production`) with protection rules:
   - Required reviewers (at least 1-2 for production)
   - Wait timer (e.g., 5 minutes for staging, configurable for production)
   - Branch restriction: only `main` can deploy to production
2. Update `docker-build.yml` to reference these environments:
```yaml
jobs:
  build-and-push:
    environment: production
```

---

#### Gap 6: No SecurityContext in Helm Deployments

**Current state:** All 13 Helm deployment templates define containers with no `securityContext` at either pod or container level. There is no `readOnlyRootFilesystem`, `runAsNonRoot`, `allowPrivilegeEscalation`, or `capabilities.drop`.

**Risk:** While the Dockerfiles all set `USER appuser`, Kubernetes does not enforce this without `securityContext`. If a base image is changed or a runtime exploit allows privilege escalation, the container runs as root with full Linux capabilities.

**Recommended fix:**
Add a `securityContext` to every Helm deployment template:
```yaml
spec:
  template:
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 1001
        fsGroup: 1001
      containers:
        - name: {{ .Chart.Name }}
          securityContext:
            readOnlyRootFilesystem: true
            allowPrivilegeEscalation: false
            capabilities:
              drop:
                - ALL
```

---

### HIGH Findings

#### Gap 7: No Dependency Review Action on PRs

**Current state:** Trivy runs filesystem scans on push/PR/weekly, but there is no `github/dependency-review-action` that specifically analyzes the *diff* of a PR to catch newly introduced CVEs.

**Recommended fix:**
Add a new job to `security-scan.yml` (or a dedicated PR workflow):
```yaml
dependency-review:
  runs-on: ubuntu-latest
  if: github.event_name == 'pull_request'
  permissions:
    contents: read
    pull-requests: write
  steps:
    - uses: actions/checkout@<sha>
    - uses: actions/dependency-review-action@<sha>
      with:
        fail-on-severity: high
        comment-summary-in-pr: always
```

---

#### Gap 8: No IaC Security Scanning

**Current state:** The `infrastructure` CI job only runs `terraform fmt -check`, `terraform init`, and `terraform validate`. No security scanner (tfsec, checkov, trivy config) is used.

**Recommended fix:**
Add `trivy config` (or `tfsec`/`checkov`) scanning to the infrastructure CI job:
```yaml
- name: Scan Terraform for misconfigurations
  uses: aquasecurity/trivy-action@<sha>
  with:
    scan-type: 'config'
    scan-ref: 'infrastructure/terraform'
    exit-code: '1'
    severity: 'CRITICAL,HIGH'
```
Also scan `platform/terraform` in a parallel job.

---

#### Gap 9: No SBOM Generation

**Current state:** No Software Bill of Materials is generated for any service or container image at build time.

**Recommended fix:**
Use `anchore/sbom-action` (or `syft` directly) in the Docker build pipeline to generate SBOMs:
```yaml
- name: Generate SBOM
  uses: anchore/sbom-action@<sha>
  with:
    image: ${{ env.IMAGE_TAG }}
    format: spdx-json
    output-file: sbom-${{ matrix.service.name }}.spdx.json
- uses: actions/upload-artifact@<sha>
  with:
    name: sbom-${{ matrix.service.name }}
    path: sbom-${{ matrix.service.name }}.spdx.json
```

---

#### Gap 10: No Pre-Commit Hooks

**Current state:** No `.pre-commit-config.yaml` exists. There are no local security checks before code is pushed.

**Recommended fix:**
Create `.pre-commit-config.yaml` with security-relevant hooks:
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
    rev: v1.96.2
    hooks:
      - id: terraform_fmt
      - id: terraform_validate
      - id: terraform_tfsec
```

---

#### Gap 11: No Egress Network Policies

**Current state:** Helm NetworkPolicies only restrict Ingress. There are no Egress policies on any service.

**Recommended fix:**
Add Egress rules to each service's NetworkPolicy to restrict outbound traffic to known endpoints only:
```yaml
policyTypes:
  - Ingress
  - Egress
egress:
  - to:
      - podSelector: {}        # Allow intra-namespace communication
    ports:
      - protocol: TCP
        port: 5432             # PostgreSQL
      - protocol: TCP
        port: 6379             # Redis
  - to:
      - namespaceSelector:
          matchLabels:
            kubernetes.io/metadata.name: kube-system
    ports:
      - protocol: UDP
        port: 53               # DNS
```

---

#### Gap 12: No Container Image Signing

**Current state:** Images are pushed to ECR without cryptographic signatures. No verification happens before deployment.

**Recommended fix:**
Add cosign signing after image push in `docker-build.yml`:
```yaml
- name: Sign image with cosign
  uses: sigstore/cosign-installer@<sha>
- run: cosign sign --yes ${{ env.ECR_REGISTRY }}/otterworks-${{ matrix.service.name }}@${{ steps.build.outputs.digest }}
```
Add cosign verification in the Helm deploy script or use a Kubernetes admission controller (e.g., Kyverno, Connaisseur).

---

#### Gap 13: Terraform State Not Encrypted, No Lock Table

**Current state:** Both S3 backends lack `encrypt = true` and `dynamodb_table` for state locking.

**Recommended fix:**
```hcl
backend "s3" {
  bucket         = "otterworks-terraform-state"
  key            = "otterworks/terraform.tfstate"
  region         = "us-east-1"
  encrypt        = true
  dynamodb_table = "otterworks-terraform-locks"
}
```
Create the DynamoDB table for state locking.

---

#### Gap 14: Wildcard IAM Resources

**Current state:** `notification-service` has `Resource = ["*"]` for SES actions; `admin-service` has `Resource = ["*"]` for CloudWatch actions.

**Recommended fix:**
Scope SES to specific verified identities:
```hcl
Resource = ["arn:aws:ses:${var.aws_region}:${data.aws_caller_identity.current.account_id}:identity/otterworks.example.com"]
```
Scope CloudWatch to the project's namespace:
```hcl
Resource = ["arn:aws:cloudwatch:${var.aws_region}:${data.aws_caller_identity.current.account_id}:metric-stream/otterworks-*"]
```

---

#### Gap 15: Report-Service Fully Excluded from Scanning

**Current state:** `report-service` is excluded from Trivy via `skip-dirs` and its known CVEs are not tracked elsewhere. It uses Java 8 with known vulnerabilities.

**Recommended fix:**
Instead of excluding, scan `report-service` separately with known CVEs acknowledged in `.trivyignore` and add a dedicated job:
```yaml
report-service-scan:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@<sha>
    - uses: aquasecurity/trivy-action@<sha>
      with:
        scan-type: 'fs'
        scan-ref: 'services/report-service'
        severity: 'CRITICAL,HIGH'
        exit-code: '0'  # Advisory-only until Java upgrade
        format: 'table'
```
This ensures *new* CVEs in report-service are still detected even while known ones are acknowledged.

---

### MEDIUM Findings

#### Gap 16: Search-Service Missing Linter

**Recommended fix:** Add `ruff check .` (or `flake8`) step to the `search-service` CI job, matching `document-service`'s pattern.

---

#### Gap 17: Docker Base Image Pinning & Multi-Stage

**Recommended fix:**
- Pin `file-service` builder to a specific Rust version: `rust:1.82-slim` instead of `rust:latest`
- Convert `search-service` Dockerfile to multi-stage: build in `python:3.12-slim`, copy only the venv to a distroless or slim runtime image

---

#### Gap 18: No Immutable Artifact Promotion

**Recommended fix:** Implement a promotion workflow: CI builds and pushes to a `staging` ECR repo; a separate promotion job (with approval gate) copies/re-tags the *same* image to the `production` ECR repo. Never rebuild.

---

#### Gap 19: No Automated Deployment Rollback

**Recommended fix:** Add `--atomic` to `helm upgrade` in `deploy-dev.sh` (automatically rolls back on failure). For production, implement canary/blue-green via Argo Rollouts or Flagger.

---

#### Gap 20: No Post-Deployment Verification

**Recommended fix:** Add smoke test steps after Helm deploys that hit each service's `/health` endpoint and verify HTTP 200. Gate deployment success on these checks.

---

#### Gap 21: No Deployment Audit Trail

**Recommended fix:** Log deployment metadata (git SHA, deployer, timestamp, environment, service, Helm revision) to an immutable store (S3, CloudWatch Logs, or the audit-service's own DynamoDB table).

---

#### Gap 22: No Secret Rotation

**Recommended fix:** Use AWS Secrets Manager with auto-rotation Lambda for `db_password`. Rotate JWT signing keys on a schedule. Reference secrets via External Secrets Operator in K8s.

---

#### Gap 23: No IaC Drift Detection

**Recommended fix:** Add a scheduled GitHub Actions workflow that runs `terraform plan` (read-only) and alerts on drift:
```yaml
on:
  schedule:
    - cron: '0 8 * * *'  # Daily
```

---

#### Gap 24: No SLSA Provenance

**Recommended fix:** Use `slsa-framework/slsa-github-generator` to generate SLSA Level 3 provenance for container images and attach to ECR via cosign.

---

#### Gap 25: EKS Public API Endpoint

**Recommended fix:** Set `endpoint_public_access = false` (or restrict via `public_access_cidrs` to known CIDR blocks). Access the cluster only via VPN/bastion.

---

#### Gap 26: Docker Compose Hardcoded Secrets

**Recommended fix:** Move secrets to a `.env` file (gitignored) and reference via `${VARIABLE}` syntax in docker-compose.yml. Add `.env.example` with placeholder values. This is a dev-only concern but prevents secret sprawl.

---

## Priority Implementation Roadmap

### Phase 1 — Immediate (CRITICAL)
1. Add `permissions:` blocks to all workflows (Gap 1)
2. Pin all third-party actions to full SHAs (Gap 2)
3. Add container image scanning before ECR push (Gap 3)
4. Remove `|| true` failure suppression (Gap 4)
5. Add GitHub Environment protection rules (Gap 5)
6. Add SecurityContext to all Helm deployments (Gap 6)

### Phase 2 — Short-term (HIGH)
7. Add dependency-review-action (Gap 7)
8. Add IaC security scanning (Gap 8)
9. Add SBOM generation (Gap 9)
10. Create pre-commit hooks (Gap 10)
11. Add egress network policies (Gap 11)
12. Implement container image signing (Gap 12)
13. Enable Terraform state encryption + locking (Gap 13)
14. Scope wildcard IAM resources (Gap 14)
15. Add report-service scanning (Gap 15)

### Phase 3 — Near-term (MEDIUM)
16–26. Remaining medium findings

---

*Generated by CI/CD Security Audit — OtterWorks Platform*
