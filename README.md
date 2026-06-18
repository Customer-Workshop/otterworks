# OtterWorks

A collaborative file storage and document editing platform — functionally equivalent to Google Drive + Google Docs. Built as a polyglot microservices system to demonstrate a realistic enterprise technology stack.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/) v2+
- ~12 GB of available RAM (for running all infrastructure and services locally)
- GNU Make (optional, for shorthand commands)
- Runs on both x86_64 and Apple Silicon (ARM64) — no Rosetta required

Individual service development may also require the language toolchains listed in the [Services](#services) table below.

## Quick Start (Local Development)

```bash
# Start infrastructure (Postgres, Redis, LocalStack, MeiliSearch, observability stack)
make infra-up

# Start all application services (builds images on first run)
make up

# Open the app
open http://localhost:3000        # Web App (React / Next.js)
open http://localhost:4200        # Admin Dashboard (Angular)
```

Or without Make:

```bash
docker compose -f docker-compose.infra.yml up -d
docker compose -f docker-compose.infra.yml -f docker-compose.yml up -d --build
```

On first run, `scripts/init-db.sql` creates the required Postgres databases and `scripts/localstack-init.sh` provisions S3 buckets, SQS queues, SNS topics, and DynamoDB tables in LocalStack automatically.

To stop everything:

```bash
make down
```

## Services

| Service | Language | Framework | Port | Description |
|---------|----------|-----------|------|-------------|
| API Gateway | Go 1.22 | Chi | 8080 | Request routing, rate limiting, JWT validation |
| Auth Service | Java 17 | Spring Boot 3 | 8081 | Authentication, authorization, user management |
| File Service | Rust 1.77 | Actix-Web 4 | 8082 | File upload/download, S3 integration, versioning |
| Document Service | Python 3.12 | FastAPI | 8083 | Document CRUD, version history, snapshots |
| Collaboration Service | Node.js 20 | Socket.io | 8084 (HTTP) / 8085 (WS) | Real-time collaborative editing (CRDT via Yjs) |
| Notification Service | Kotlin 1.9 | Ktor 2.3 | 8086 | Event-driven notifications (email, in-app, webhook) |
| Search Service | Python 3.12 | Flask 3.0 | 8087 | Full-text search via MeiliSearch |
| Analytics Service | Scala 3.4 | Akka HTTP | 8088 | Usage analytics, data aggregation |
| Admin Service | Ruby 3.3 | Rails 7.1 | 8089 | Admin dashboard backend |
| Audit Service | C# 12 | ASP.NET 8 | 8090 | Immutable audit trail, compliance |
| Report Service *(legacy)* | Java 8 | Spring Boot 2.5 | 8091 | PDF/CSV/Excel report generation (tech-debt: upgrade target Java 17+, Spring Boot 3.2+) |

> **Note:** The Report Service intentionally uses outdated dependencies (Java 8, Spring Boot 2.5, JUnit 4, javax.\*) and is a candidate for a framework-upgrade exercise. See `services/report-service/pom.xml` for details.

## Frontend Applications

| App | Framework | Port | Description |
|-----|-----------|------|-------------|
| Web App | React 18 / Next.js 14 | 3000 | Main user-facing application |
| Admin Dashboard | Angular 17 | 4200 | Administrative interface |

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full system design, data flow, and infrastructure details.

## Infrastructure

### AWS Resources (App-Specific)
Managed via Terraform in `infrastructure/terraform/`:
- S3 (file storage, data lake, static assets)
- RDS PostgreSQL
- ElastiCache Redis
- DynamoDB (file metadata, audit events, notifications)
- SQS/SNS (event bus)
- MeiliSearch (full-text search)
- Cognito (identity federation)
- CloudFront (CDN)
- ECR (container image repositories)

### Kubernetes
- Helm charts per service in `infrastructure/helm/`
- Base namespace resources (ResourceQuota, LimitRange) in `infrastructure/k8s/`
- Deploys to EKS cluster managed by [platform-engineering-shared-services](https://github.com/Cognition-Partner-Workshops/platform-engineering-shared-services)

### Deploy to AWS

```bash
# Initialize and apply Terraform
make tf-init
make tf-apply          # uses environments/dev.tfvars

# Deploy services to EKS
make deploy-dev
```

### Tear Down

```bash
make teardown-dev
```

## Observability

All observability services run locally via `docker-compose.infra.yml`.

| Tool | URL | Purpose |
|------|-----|---------|
| Grafana | http://localhost:3001 | Dashboards and metrics visualization (admin / otterworks) |
| Prometheus | http://localhost:9090 | Metrics collection and alerting rules |
| Jaeger | http://localhost:16686 | Distributed tracing UI |
| MeiliSearch | http://localhost:7700 | Search engine dashboard |

- **Logging**: Structured JSON logs → Fluent Bit → CloudWatch (production) / stdout (local)
- **Metrics**: Prometheus scraping `/metrics` endpoints + Grafana dashboards in `observability/grafana/dashboards/`
- **Tracing**: OpenTelemetry SDK per service → OTel Collector → Jaeger
- **Alerting**: PrometheusRule definitions in `observability/prometheus/` → Alertmanager

## CI/CD

GitHub Actions workflows in `.github/workflows/`:

| Workflow | Trigger | Description |
|----------|---------|-------------|
| `ci.yml` | Push / PR to `main` | Lint, test, and build changed services (change-detection via path filters) |
| `docker-build.yml` | Push to `main` / tags | Build and push Docker images to ECR |
| `security-scan.yml` | Push / PR | SAST, dependency audit, and container scanning |

## Security Vulnerability Management

OtterWorks uses [Trivy](https://github.com/aquasecurity/trivy) as its primary vulnerability scanner, integrated into CI and backed by an automated remediation pipeline. This section covers how vulnerabilities are detected, how each service should be remediated, and how the auto-fix loop works.

### Scanning Overview

| Layer | Tool | Where It Runs |
|-------|------|---------------|
| Dependency CVEs (CRITICAL/HIGH) | Trivy | CI (`security-scan.yml`, `sast-auto-remediate.yml`), local (`make security-scan`) |
| Code quality / bugs | SonarCloud | CI (`sast-auto-remediate.yml`) |
| Secret detection | Gitleaks | CI (`security-scan.yml`) |
| Static analysis (OWASP) | Semgrep | CI (`security-scan.yml`) |

Trivy configuration lives in `security/scanning/trivy-config.yaml` and filters to CRITICAL and HIGH severity for both OS packages and language-specific libraries.

### Per-Service Remediation Guide

Each microservice uses a different language and package manager. The table below shows how to upgrade dependencies when Trivy reports a vulnerable package in a given service.

| Service | Language | Manifest | Lock File | Upgrade Command | Notes |
|---------|----------|----------|-----------|-----------------|-------|
| api-gateway | Go 1.22 | `go.mod` | `go.sum` | `go get <pkg>@<version> && go mod tidy` | Run `go vet ./...` and `go test ./...` after upgrading |
| auth-service | Java 17 | `build.gradle` | — | Update version in `build.gradle`, run `./gradlew dependencies` | Gradle resolution; check Spring Boot BOM compatibility |
| file-service | Rust | `Cargo.toml` | `Cargo.lock` | `cargo update -p <crate>` or edit version in `Cargo.toml` | Run `cargo clippy` and `cargo test` after upgrading |
| document-service | Python 3.12 | `pyproject.toml` | `poetry.lock` | `poetry update <pkg>` or `poetry add <pkg>@^<version>` | Poetry-managed; regenerates lock file automatically |
| collab-service | Node.js 20 | `package.json` | `package-lock.json` | `npm install <pkg>@<version>` | Run `npm audit` to verify fix, then `npm test` |
| notification-service | Kotlin 1.9 | `build.gradle.kts` | — | Update version in `build.gradle.kts`, run `./gradlew dependencies` | Kotlin DSL; check Ktor BOM compatibility |
| search-service | Python 3.12 | `requirements.txt` | — | Edit version pin in `requirements.txt`, `pip install -r requirements.txt` | No lock file — pin exact versions |
| analytics-service | Scala 3.4 | `build.sbt` | — | Update version in `build.sbt`, run `sbt update` | Check Akka HTTP cross-version compatibility |
| admin-service | Ruby 3.3 | `Gemfile` | `Gemfile.lock` | `bundle update <gem>` | Run `bundle exec rspec` after upgrading; Rails 7.1 constraints apply |
| audit-service | C# 12 | `AuditService.csproj` | — | `dotnet add package <pkg> --version <version>` | Run `dotnet test` after upgrading |
| report-service | Java 8 | `pom.xml` | — | **Excluded from scans** — intentionally legacy | Earmarked for a separate Java 17 / Spring Boot 3 framework upgrade exercise |
| web-app | Node.js 20 | `package.json` | `package-lock.json` | `npm install <pkg>@<version>` | Next.js 14 — some CVEs require a major upgrade to 14.2.25+ or 15.x |
| admin-dashboard | Node.js 20 | `package.json` | `package-lock.json` | `npm install <pkg>@<version>` | Angular 17 — some CVEs require a major upgrade to 19+ |

### Automated Remediation Pipeline

The `sast-auto-remediate.yml` workflow implements a closed-loop scan → fix → re-scan cycle:

```
PR opened/updated → Trivy scan → findings? ──NO──→ ✓ pass
                                    │
                                   YES
                                    │
                      attempts < MAX (2)? ──NO──→ escalate (GitHub Issue)
                                    │
                                   YES
                                    │
                      trigger Devin webhook → Devin fixes deps,
                      runs service tests, pushes commit → re-scan
```

Key behaviors:
- **Bot-loop prevention**: PRs authored by `devin-ai-integration[bot]` are never scanned by this workflow. Devin's fix commits on human-authored PRs *do* trigger a re-scan (the desired closed-loop verification).
- **Attempt cap**: After `MAX_FIX_ATTEMPTS` (default: 2) Devin fix cycles, the pipeline stops and opens a GitHub Issue labeled `security` + `needs-human-review` with the remaining findings.
- **SonarCloud path**: A parallel path triggers a one-time Devin remediation session when the SonarCloud quality gate fails. Unlike the Trivy path, it does not retry.

### `.trivyignore` — Suppressed CVEs

Acknowledged vulnerabilities that cannot be fixed without a major version upgrade are listed in `.trivyignore` at the repo root, grouped by service with comments explaining the blocker:

```
# --- services/admin-service: requires Rails 7.2+ upgrade (activestorage CVEs) ---
CVE-2026-33195
CVE-2026-33658
```

**Rules for `.trivyignore` entries:**
- Each entry must reference a specific CVE (no glob patterns like `CVE-2021-*`).
- Each entry must have a comment explaining which service/package is affected, what blocks remediation, and when it will be revisited.
- CRITICAL/HIGH CVEs with RCE or auth-bypass impact require strong justification.
- Remove entries as soon as the blocking upgrade is completed.

See `docs/labs/security-sprint-guide.md` for the full triage and audit process.

### Running Scans Locally

```bash
# Full scan suite (Trivy + npm audit + pip-audit + bundle-audit)
make security-scan

# Trivy only (all services, CRITICAL+HIGH)
trivy fs --config security/scanning/trivy-config.yaml .

# Trivy without severity filter (see everything)
trivy fs .
```

The `report-service` directory is excluded from CI scans via `--skip-dirs` and from `.trivyignore` scope. It is a legacy Java 8 service intentionally kept at outdated dependency versions for framework upgrade exercises.

## Makefile Commands

Run `make help` to list all available commands. Key targets:

| Command | Description |
|---------|-------------|
| `make infra-up` | Start local infrastructure (Postgres, Redis, LocalStack, MeiliSearch, observability) |
| `make up` | Build and start all application services |
| `make down` | Stop all services and infrastructure |
| `make build` | Build all service Docker images |
| `make logs` | Tail logs for all services |
| `make test` | Run tests for all services |
| `make lint` | Lint all services |
| `make tf-plan` | Plan Terraform changes (dev) |
| `make deploy-dev` | Deploy all services to dev EKS |
| `make teardown-dev` | Tear down the dev environment |

Per-service build targets are also available (e.g., `make build-gateway`, `make build-auth`).

## Project Structure

```
otterworks/
├── services/              # Backend microservices (11 services, 8 languages)
│   ├── api-gateway/       #   Go / Chi
│   ├── auth-service/      #   Java / Spring Boot
│   ├── file-service/      #   Rust / Actix-Web
│   ├── document-service/  #   Python / FastAPI
│   ├── collab-service/    #   Node.js / Socket.io
│   ├── notification-service/ # Kotlin / Ktor
│   ├── search-service/    #   Python / Flask
│   ├── analytics-service/ #   Scala / Akka HTTP
│   ├── admin-service/     #   Ruby / Rails
│   ├── audit-service/     #   C# / ASP.NET
│   └── report-service/    #   Java 8 / Spring Boot 2.5 (legacy)
├── frontend/              # Web app (React/Next.js) + Admin dashboard (Angular)
├── infrastructure/
│   ├── terraform/         #   App-specific AWS resources (S3, RDS, DynamoDB, etc.)
│   ├── helm/              #   Per-service Helm charts
│   └── k8s/               #   Base Kubernetes resources (namespace, quotas, limits)
├── shared/
│   ├── proto/             #   Protobuf / gRPC service definitions
│   ├── openapi/           #   OpenAPI specs per service
│   └── events/            #   Event schema definitions (JSON Schema)
├── observability/
│   ├── grafana/           #   Dashboards and provisioning
│   ├── prometheus/        #   Scrape config, alert rules, recording rules
│   ├── jaeger/            #   Jaeger deployment config
│   ├── otel/              #   OpenTelemetry Collector config
│   └── logging/           #   Fluent Bit config and parsers
├── security/
│   ├── policies/          #   Network policies (default-deny, DNS, namespace egress)
│   └── scanning/          #   Trivy container scanning config
├── etl/
│   ├── airflow/           #   Airflow DAGs, plugins, and tests
│   └── spark/             #   Scala Spark processing jobs
├── scripts/               # Deploy and teardown scripts
└── .github/workflows/     # CI/CD pipelines (ci, docker-build, security-scan)
```

## Contributing

### Getting Started

1. Fork the repository and create a feature branch from `main`.
2. Follow the [Quick Start](#quick-start-local-development) instructions to bring up the local environment.
3. Make your changes in the relevant service or module directory.

### Code Standards

- Each service follows the idiomatic conventions of its language (e.g., `go fmt`, `cargo clippy`, `ruff`, `eslint`).
- Run `make lint` before committing to catch issues early.
- Run `make test` to execute the full test suite.

### Commit Guidelines

- Use clear, descriptive commit messages.
- Keep commits focused — one logical change per commit.

### Pull Requests

1. Push your branch and open a PR against `main`.
2. Ensure CI passes (lint, test, build, security scan).
3. Include a concise description of **what** changed and **why**.
4. Link to any relevant issue or user story.

### Adding a New Service

1. Create a directory under `services/<service-name>/` with a `Dockerfile`.
2. Add the service to `docker-compose.yml` with the shared environment block (`x-common-env`).
3. Create a Helm chart in `infrastructure/helm/<service-name>/`.
4. Add OpenAPI and event schemas to `shared/`.
5. Update this README and `ARCHITECTURE.md`.

## License

Proprietary - OtterWorks Inc.
