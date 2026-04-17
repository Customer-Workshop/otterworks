# OtterWorks

A collaborative file storage and document editing platform — functionally equivalent to Google Drive + Google Docs. Built as a polyglot microservices system to demonstrate a realistic enterprise technology stack.

## Quick Start (Local Development)

```bash
# Start infrastructure (Postgres, Redis, LocalStack for AWS services)
docker compose -f docker-compose.infra.yml up -d

# Start all services
docker compose up -d

# Seed development data
./scripts/seed-data.sh

# Open the app
open http://localhost:3000
```

## Services

| Service | Language | Framework | Port | Description |
|---------|----------|-----------|------|-------------|
| API Gateway | Go 1.22 | Chi | 8080 | Request routing, rate limiting, JWT validation |
| Auth Service | Java 17 | Spring Boot 3 | 8081 | Authentication, authorization, user management |
| File Service | Rust 1.77 | Actix-Web 4 | 8082 | File upload/download, S3 integration, versioning |
| Document Service | Python 3.12 | FastAPI | 8083 | Document CRUD, version history, snapshots |
| Collaboration Service | Node.js 20 | Socket.io | 8084/8085 | Real-time collaborative editing (CRDT) |
| Notification Service | Kotlin 1.9 | Ktor 2.3 | 8086 | Event-driven notifications (email, in-app, webhook) |
| Search Service | Python 3.12 | Flask 3.0 | 8087 | Full-text search via OpenSearch |
| Analytics Service | Scala 3.4 | Akka HTTP | 8088 | Usage analytics, data aggregation |
| Admin Service | Ruby 3.3 | Rails 7.1 | 8089 | Admin dashboard backend |
| Audit Service | C# 12 | ASP.NET 8 | 8090 | Immutable audit trail, compliance |

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
- S3 (file storage, data lake)
- RDS PostgreSQL
- ElastiCache Redis
- DynamoDB (file metadata, audit events)
- SQS/SNS (event bus)
- OpenSearch (full-text search)
- Cognito (identity)
- CloudFront (CDN)

### Kubernetes
Each service has a Helm chart in `infrastructure/helm/`. Deploys to EKS cluster managed by [platform-engineering-shared-services](https://github.com/Cognition-Partner-Workshops/platform-engineering-shared-services).

### Deploy to AWS

```bash
# Deploy infrastructure
cd infrastructure/terraform
terraform init
terraform apply -var-file=environments/dev.tfvars

# Deploy services to EKS
./scripts/deploy-dev.sh
```

### Tear Down

```bash
./scripts/teardown-dev.sh
```

## Observability

- **Logging**: Structured JSON logs → CloudWatch via Fluentd
- **Metrics**: Prometheus + Grafana dashboards
- **Tracing**: OpenTelemetry → Jaeger
- **Alerting**: PrometheusRule → Alertmanager

## Project Structure

```
otterworks/
├── services/           # Backend microservices (10 services, 8 languages)
├── frontend/           # Web app (React) + Admin dashboard (Angular)
├── infrastructure/     # Terraform + Helm charts
├── shared/             # Protobuf, OpenAPI specs, event schemas
├── observability/      # Grafana dashboards, Prometheus rules, Jaeger config
├── security/           # OPA policies, scanning configs, SBOM scripts
├── etl/                # Airflow DAGs + Spark jobs
├── scripts/            # Setup, deploy, teardown scripts
└── docs/               # API docs, runbooks, ADRs
```

## License

Proprietary - OtterWorks Inc.
