---
name: aws-cloud-native-modernization
description: >
  Repo-specific mechanics for migrating an OtterWorks component onto a fully
  managed / serverless AWS service with contract verification. Covers the
  migration menu, where each backend and its IaC module live, the exact adapter
  seams, deploy/config wiring, contract-test commands, namespacing, and revert.
  Auto-loaded when Devin works in this repository.
---

# AWS Cloud-Native Modernization — OtterWorks

This skill provides the repo-specific mechanics that the `!aws-cloud-native`
Playbook relies on. It is auto-loaded when Devin works in this repository.

OtterWorks deploys to EKS (`otterworks-dev`, v1.32, namespace `otterworks`) with
app resources provisioned by `infrastructure/terraform` and platform resources
(VPC/EKS/ECR) by `platform/terraform`, both with remote S3 state
(`s3://otterworks-terraform-state`). The two-layer Terraform + a stable set of
API contracts is what makes managed/serverless swaps verifiable.

## The migration menu (which component → which AWS target)

Two value themes an AWS-native audience cares about. Each row is one runnable
unit of the `!aws-cloud-native` playbook.

### Theme 1 — Retire the toil: self-managed → fully managed

| Component | Today (self-managed) | Managed AWS target | Contract / proof |
|---|---|---|---|
| **search-service** ⭐ | MeiliSearch on ECS Fargate (`modules/search`) + in-cluster fallback (`deploy-dev.sh :: deploy_meilisearch`) | **Amazon OpenSearch Serverless** | `tests/contract/test_search_contract.py` + `shared/openapi/search-service.yaml` |
| cache (all services) | already ElastiCache Redis (`modules/cache`) — reference for the pattern | ElastiCache (managed) | service boot + `/health/ready` |
| relational DB (auth/document/admin/report/analytics) | RDS PostgreSQL (`modules/database`) | **Aurora Serverless v2** (scale-to-zero) | `tests/api/` flows + Flyway migrations |
| **auth-service** identity | hand-rolled JWT issue/validate (Java/Spring) | **Amazon Cognito** (user pools already provisioned, `modules/auth`) | `tests/api/test_auth_flow.py` |

### Theme 2 — Capitalize on cloud-native: serverless compute & event-driven

| Component | Today | Serverless AWS target | Contract / proof |
|---|---|---|---|
| **report-service** (legacy Java 8 / Spring Boot 2.5) | always-on EKS pod | **AWS Lambda + API Gateway** (scale-to-zero, pay-per-request) | `tests/api/test_audit_analytics_report_flow.py` |
| **notification-service** (Kotlin/Ktor) | in-cluster consumer of SNS→SQS (`modules/messaging`) | **EventBridge + SQS + Lambda** (fully serverless async) | `tests/api/test_notification_admin_gateway_flow.py` |
| web-app / admin-dashboard | container `LoadBalancer` on EKS | **S3 + CloudFront** (serverless edge) | frontend build + smoke |

⭐ = flagship executed flow (best AWS-console story: OpenSearch Dashboards +
CloudWatch, and an existing contract harness).

## Flagship: search-service → Amazon OpenSearch Serverless

**The interface seam.** `search-service` talks to its backend only through
`app/services/meilisearch_client.py` (query/suggest/advanced/index/analytics),
configured by `app/config.py :: MeiliSearchConfig` from env
`MEILISEARCH_URL` / `MEILISEARCH_API_KEY` / `MEILISEARCH_*_INDEX`. Migrate by
adding a sibling `opensearch_client.py` implementing the **same** methods, and
select it by a new `SEARCH_BACKEND` env (`meilisearch` | `opensearch`, default
`meilisearch` so `main` is unchanged). Do **not** rewrite the API layer
(`app/api/*.py`) — it stays backend-agnostic.

**Behaviors the contract asserts** (`tests/contract/test_search_contract.py`) —
these are what "parity" means: `GET /api/v1/search/` (query, page/size, 400 on
bad params), `GET /api/v1/search/suggest` (**prefix/type-ahead**, empty for
<2 chars), `POST /api/v1/search/advanced` (type/tags/date filters), the index
endpoints, `/api/v1/search/analytics`, `/health`, `/health/ready`
(`meilisearch_unavailable` reason string), `/metrics` (Prometheus names). The
known divergence is `/suggest`: MeiliSearch is prefix-first; OpenSearch `match`
is not — map suggest to `search_as_you_type` / `match_phrase_prefix`.

**IaC.** Add `infrastructure/terraform/modules/opensearch/` (an
`aws_opensearchserverless_collection` of type `SEARCH`, an encryption + network +
data-access policy scoped to the namespace, name suffixed by the namespace), wire
it in `infrastructure/terraform/main.tf` alongside `module "search"`, export the
collection endpoint in `outputs.tf`, and extend the `search-service` IRSA policy
in `main.tf` (block `"search-service"`) with `aoss:APIAccessAll` on the
collection ARN. Keep `module "search"` (MeiliSearch) in place — it is the before-state.

**Deploy wiring.** `scripts/deploy-dev.sh` sets `search-service` config via
`--set-string config.MEILISEARCH_URL=...` (see the `search-service)` case around
line 279). Add the OpenSearch endpoint + `SEARCH_BACKEND=opensearch` the same way
(config via `--set`, any key via the locked-down temp values file — never commit
endpoints/keys). The IaC provisions OpenSearch Serverless; for a fully in-cluster
run the before-state backend is the in-cluster MeiliSearch from `deploy_meilisearch`.

## Namespacing (isolation for parallel + repeatable runs)

Every run carries a namespace suffix (e.g., `os1`, `session3`). Apply it to: the
Terraform module name/resources, the branch (`migration/<name>-<ns>`), and any
per-run k8s objects. Concurrent runs and repeats never collide, and revert is
`terraform destroy` of just the namespaced module. This mirrors the
`otterworks_<ns>` convention in the synthetic-testdata skill.

## Commands

```bash
# --- Contract / parity (the verification loop) ---
pip install -r tests/api/requirements.txt          # pyyaml jsonschema requests pytest
# Run search-service (local) then point the contract suite at it:
SEARCH_SERVICE_URL=http://localhost:8087 \
  pytest tests/contract/test_search_contract.py -v
# Black-box API flow suites (per theme row):
make test-api-flows                                 # against the local API gateway

# --- IaC (namespaced target) ---
cd infrastructure/terraform
terraform init
terraform plan  -target=module.opensearch          # review before apply
terraform apply -target=module.opensearch

# --- Deploy the migrated service to EKS ---
AWS_ACCOUNT_ID=$AWS_ACCOUNT_ID DB_PASSWORD=$DB_PASSWORD ./scripts/deploy-dev.sh --skip-platform

# --- Performance (before/after; result visible in the AWS console) ---
# Baseline against MeiliSearch, then re-run against OpenSearch Serverless:
hey -z 60s -c 20 "http://<gateway>/api/v1/search/?q=report"   # or k6/artillery
# Read the "after" in: OpenSearch Dashboards (index/query latency),
# CloudWatch (collection metrics); for Lambda flows: Lambda + API Gateway metrics.

# --- Revert (one path back to the before-state) ---
cd infrastructure/terraform && terraform destroy -target=module.opensearch
# redeploy with SEARCH_BACKEND unset (defaults to meilisearch)
```

## Where things live (quick map)

| Concern | Path |
|---|---|
| Search backend adapter (the seam) | `services/search-service/app/services/meilisearch_client.py` |
| Search config (env → backend) | `services/search-service/app/config.py` |
| Search API (backend-agnostic) | `services/search-service/app/api/{search,index,health}.py` |
| Search contract + spec | `tests/contract/test_search_contract.py`, `shared/openapi/search-service.yaml` |
| App IaC (add managed target here) | `infrastructure/terraform/{main.tf,outputs.tf,modules/}` |
| IRSA least-privilege policies | `infrastructure/terraform/main.tf` (`module "irsa"`, per-service blocks) |
| Deploy / config+secret wiring | `scripts/deploy-dev.sh` (`build_helm_args`, `load_infra_outputs`, `deploy_meilisearch`) |
| Report-service (Lambda candidate) | `services/report-service/` (Java 8, Spring Boot 2.5.14) |
| Messaging (EventBridge/SQS candidate) | `infrastructure/terraform/modules/messaging`, `services/notification-service/` |
| Cognito user pools (identity target) | `infrastructure/terraform/modules/auth` |

## Golden-app rules (from repo `AGENTS.md`)

- `main` is the golden before-state: do **not** merge the managed/serverless swap
  into it, and keep the existing self-managed backend/module in place.
- `admin-service` crash-loops by design (planted Rails bug) — not part of this
  migration; leave it.
- Genuine IaC/wiring gaps you hit while migrating (missing config, IAM) should be
  fixed; planted bugs should not.
