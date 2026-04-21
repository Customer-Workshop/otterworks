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
# 1. Start infrastructure (Postgres, Redis, LocalStack, OpenSearch, observability stack)
make infra-up

# 2. Wait for all infrastructure containers to become healthy (~30s)
docker compose -f docker-compose.infra.yml ps   # all should show "healthy"

# 3. Start all application services (builds images on first run)
make up

# 4. Open the app
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

### Environment Variables

All services share a common set of environment variables defined in `docker-compose.yml` via the `x-common-env` anchor. Key defaults for local development:

| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_REGION` | `us-east-1` | AWS region (LocalStack) |
| `AWS_ENDPOINT_URL` | `http://localstack:4566` | LocalStack endpoint for S3, SQS, SNS, DynamoDB |
| `POSTGRES_HOST` | `postgres` | PostgreSQL hostname |
| `POSTGRES_DB` | `otterworks` | PostgreSQL database name |
| `REDIS_HOST` | `redis` | Redis hostname |
| `OPENSEARCH_URL` | `http://opensearch:9200` | OpenSearch endpoint |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://otel-collector:4318` | OpenTelemetry Collector |

For production configuration, override these via Kubernetes ConfigMaps/Secrets or Terraform outputs.

### Verifying the Setup

After starting all services, verify they are running:

```bash
# Check all container health statuses
make logs          # Tail logs across all services

# Hit the API Gateway health endpoint
curl http://localhost:8080/health

# Verify individual services (replace PORT with the service port)
curl http://localhost:8081/health   # Auth Service
curl http://localhost:8082/health   # File Service
curl http://localhost:8083/health   # Document Service
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
| Search Service | Python 3.12 | Flask 3.0 | 8087 | Full-text search via OpenSearch |
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

```
                                 +------------------+
                                 |   CloudFront     |
                                 |   CDN            |
                                 +--------+---------+
                                          |
                                 +--------+---------+
                                 |  NGINX Ingress   |
                                 +--------+---------+
                                          |
                      +-------------------+-------------------+
                      |                                       |
             +--------+---------+                   +---------+--------+
             |  Web Frontend    |                   |  Admin Dashboard |
             |  (React/Next.js) |                   |  (Angular 17)    |
             +--------+---------+                   +---------+--------+
                      |                                       |
             +--------+---------+                             |
             |  API Gateway     +-----------------------------+
             |  (Go / Chi)      |
             +--------+---------+
                      |
  +---+---+---+---+---+---+---+---+---+---+
  |   |   |   |   |   |   |   |   |   |   |
 Auth File Doc  Co- Not- Sea- Ana- Adm- Aud- Rep-
 Java Rust Py   lab  ify  rch  lyt  in   it   ort
                JS   Kt   Py   Sc   Rb   C#   Java
  |   |   |   |   |   |   |   |   |   |   |
  +---+---+---+---+---+---+---+---+---+---+
  |            Data & Infrastructure           |
  | PostgreSQL | Redis | DynamoDB | S3         |
  | OpenSearch | SQS/SNS | Cognito            |
  +--------------------------------------------+
```

All client traffic enters through the **API Gateway** (Go/Chi), which handles JWT validation, rate limiting, and request routing to downstream microservices. Services communicate asynchronously via **SNS/SQS** for domain events and **Redis Pub/Sub** for real-time collaboration state. Data is persisted across **PostgreSQL** (relational), **DynamoDB** (NoSQL), **S3** (object storage), and **OpenSearch** (full-text search).

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full system design, data flow, and infrastructure details.

## Infrastructure

### AWS Resources (App-Specific)
Managed via Terraform in `infrastructure/terraform/`:
- S3 (file storage, data lake, static assets)
- RDS PostgreSQL
- ElastiCache Redis
- DynamoDB (file metadata, audit events, notifications)
- SQS/SNS (event bus)
- OpenSearch (full-text search)
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
| OpenSearch Dashboards | http://localhost:5601 | Log exploration and search analytics |

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

## Makefile Commands

Run `make help` to list all available commands. Key targets:

| Command | Description |
|---------|-------------|
| `make infra-up` | Start local infrastructure (Postgres, Redis, LocalStack, OpenSearch, observability) |
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

1. Fork the repository and create a feature branch from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```
2. Follow the [Quick Start](#quick-start-local-development) instructions to bring up the local environment.
3. Make your changes in the relevant service or module directory.

### Development Workflow

- **One service at a time**: Each service can be built and tested independently. Use the per-service Make targets (e.g., `make build-gateway`, `make build-auth`) during development.
- **Run tests** before committing:
  ```bash
  make test     # All services
  make lint     # All linters
  ```
- **Per-service test commands** (run from the service directory):
  | Service | Command |
  |---------|--------|
  | API Gateway | `go test ./...` |
  | Auth Service | `./gradlew test` |
  | File Service | `cargo test` |
  | Document Service | `pytest` |
  | Collab Service | `npm test` |
  | Notification Service | `./gradlew test` |
  | Search Service | `pytest` |
  | Analytics Service | `sbt test` |
  | Admin Service | `bundle exec rspec` |
  | Audit Service | `dotnet test` |
  | Web App | `npm test` |
  | Admin Dashboard | `npm test` |

### Commit and PR Guidelines

- Use [Conventional Commits](https://www.conventionalcommits.org/) for commit messages:
  ```
  feat(document-service): add template duplication endpoint
  fix(api-gateway): correct rate limiter token bucket refill
  docs: update README architecture diagram
  ```
- Keep PRs focused on a single service or concern when possible.
- CI runs automatically on every PR — lint, test, build, and security scans must all pass.
- Include a clear description of the change, motivation, and any testing performed.
- Link to any relevant issue or user story.

### Code Style

Each service follows the conventions of its language ecosystem. Linting is enforced in CI:

| Service | Linter |
|---------|--------|
| API Gateway (Go) | `golangci-lint` |
| Auth Service (Java) | Spotless (`./gradlew spotlessCheck`) |
| File Service (Rust) | `cargo clippy` |
| Document Service (Python) | `ruff` |
| Collab Service (Node.js) | ESLint (`npm run lint`) |
| Search Service (Python) | `ruff` |
| Web App (Next.js) | ESLint (`npm run lint`) |
| Admin Dashboard (Angular) | ESLint (`npm run lint`) |

### Adding a New Service

1. Create a directory under `services/<service-name>/` with a `Dockerfile` and health endpoint at `/health`.
2. Add the service to `docker-compose.yml` with the shared `x-common-env` anchor.
3. Add a Helm chart in `infrastructure/helm/<service-name>/`.
4. Register the service in the API Gateway routing configuration.
5. Add OpenAPI specs to `shared/openapi/` and event schemas to `shared/events/` as applicable.
6. Add build, test, and lint targets to the `Makefile`.
7. Update the CI workflow path filters in `.github/workflows/ci.yml`.
8. Update this README and `ARCHITECTURE.md`.

## License

Proprietary - OtterWorks Inc.
