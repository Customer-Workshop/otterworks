# ADR-003: Polyglot Services for Otter Species Diversity

| Field | Value |
|-------|-------|
| **Status** | Accepted |
| **Date** | 2025-03-01 |
| **Decision Makers** | Ollie Lutris, Harbor Giant, Estuary Atlas |

## Context

OtterWorks requires a decision on whether to standardize on a single language/framework or embrace polyglot microservices. The team has diverse expertise, and different services have different performance characteristics.

Just as the otter family (Lutrinae) contains 13 species adapted to different environments -- sea otters for kelp forests, river otters for freshwater, giant otters for tropical rivers -- our services should use the best tool for each environment.

## Decision

We will adopt a polyglot architecture with the following language assignments:

| Service | Language | Rationale |
|---------|----------|-----------|
| API Gateway | Go | Low-latency proxy, excellent concurrency model |
| Auth Service | Java/Spring | Mature security ecosystem, Spring Security |
| File Service | Rust | Memory safety, zero-cost abstractions for streaming |
| Document Service | Python/FastAPI | Rapid development, rich ML/NLP ecosystem |
| Collab Service | Node.js/TypeScript | Yjs native ecosystem, event-loop for WebSockets |
| Notification Service | Kotlin/Ktor | JVM performance with modern syntax |
| Search Service | Python/Flask | MeiliSearch client, lightweight wrapper |
| Analytics Service | Scala/Akka | Stream processing, functional data transforms |
| Admin Service | Ruby/Rails | Rapid CRUD, convention over configuration |
| Audit Service | C#/.NET | Strong typing for compliance, enterprise tooling |
| Report Service | Java/Spring Boot | Legacy; upgrade candidate |

## Consequences

### Positive
- Each service uses the best tool for its specific requirements
- Teams can leverage existing expertise
- Demonstrates real-world enterprise complexity for training/workshops

### Negative
- Higher operational complexity (11 build pipelines, 8 language runtimes)
- Harder to share code across services (mitigated by shared event schemas)
- Onboarding new engineers requires broader language familiarity

### Mitigations
- Standardized Docker builds and Helm charts for all services
- Shared event schema definitions in `shared/events/schemas/`
- OpenAPI specs for all REST APIs in `shared/openapi/`
- Common observability stack (OTel, Prometheus, Grafana) across all languages

## Alternatives Considered

1. **All Java/Spring**: Rejected -- poor fit for real-time WebSockets and file streaming
2. **All Go**: Rejected -- less ergonomic for rapid CRUD and data science workflows
3. **All TypeScript**: Rejected -- performance concerns for compute-heavy services
