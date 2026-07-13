# Playbook: AWS Cloud-Native Modernization (managed & serverless) with a verification loop

> **Facilitator / author:** this file is the source for a **Devin Playbook**.
> Copy its contents into your Devin organization (Settings → Playbooks → *Create
> a new Playbook*) so sessions can invoke it as `!aws-cloud-native`. See
> [Creating Playbooks](https://docs.devin.ai/product-guides/creating-playbooks).

## Overview

Use this playbook to move one component of a running application off a
self-managed / always-on implementation and onto a **fully managed** or
**serverless** AWS service — and to **prove** the swap is behavior-preserving
before it is trusted. Examples: a self-managed search engine → **Amazon
OpenSearch Serverless**, a self-hosted cache → **ElastiCache**, a self-managed
relational DB → **Aurora Serverless v2**, a long-running sync microservice →
**AWS Lambda + API Gateway**, a hand-rolled event pipeline → **EventBridge + SQS
+ Lambda**, a container-hosted SPA → **S3 + CloudFront**.

The guiding principle: **the API contract is the source of truth, and a
migration is not "done" until the same contract tests that gate the original
implementation go green against the managed/serverless target — plus a
before/after performance run that is visible in the AWS console.** Confidence
comes from programmatic verification and a measurable performance delta, not from
"the new service came up."

A good run does not swap an SDK and declare victory. It reads the existing
component, provisions the managed/serverless target as **Infrastructure as Code**
in an isolated namespace, wires the app behind its existing interface, runs the
contract/parity suite, catches a real divergence (a query semantics gap, a
missing field, a status-code mismatch), fixes it against the contract, and then
runs a load test whose latency/throughput/cost shows up in CloudWatch (or the
target service's own console) — leaving the original untouched so the swap is
reversible.

## Required from user

- **The component and its target** — which component moves and to which AWS
  managed/serverless service (e.g., `search-service` → OpenSearch Serverless).
- **The contract / source of truth** — the OpenAPI spec + contract/flow tests
  that must stay green (e.g., `shared/openapi/<svc>.yaml` +
  `tests/contract/` / `tests/api/`). If you cannot state the programmatic check
  that proves parity, stop and define it first — it is the heart of the run.
- **The namespace** — an isolation suffix so the provisioned AWS resources and
  the deployment never collide with `main` or a concurrent run (e.g., `dev`,
  `os1`, `session3`). All new IaC and deploys are scoped to it.
- **The performance check** — the before/after load test and where its result is
  read (CloudWatch dashboard, OpenSearch Dashboards, Lambda/API Gateway metrics).

## Procedure

1. **Orient over the component and its contract.** Read the component's code and
   its interface abstraction (the client/adapter it talks to its backend
   through), the OpenAPI spec, and the contract/flow tests. Identify the exact
   behaviors the tests assert (endpoints, query params, response schemas, status
   codes, error bodies). This is what "parity" means — write it down.

2. **Establish the before-state baseline.** Bring up the component against its
   current backend, run the contract suite, and capture a **baseline performance
   run** (latency percentiles, throughput, and — where relevant — the ops cost of
   keeping the always-on backend alive). This is the "before" half of the story.

3. **Provision the managed/serverless target as IaC, in the namespace.** Add a
   Terraform module (or extend one) for the target service (OpenSearch
   Serverless collection + data-access policy, Aurora Serverless v2 cluster,
   Lambda + API Gateway, etc.), scoped by the namespace suffix and with
   **least-privilege IAM** (IRSA / execution role). `plan`, then `apply`. Never
   mutate shared/`main` resources — create namespaced ones.

4. **Wire the app behind its existing interface.** Add a target-backed adapter
   that implements the *same* interface the component already uses, selected by
   config/env (so the swap is a config flip, not a rewrite). Keep the original
   adapter in place. Inject the new endpoints/credentials via the deploy path,
   never committed.

5. **Run the verification loop.** Deploy to the namespace, then run the contract
   suite against the target-backed instance. Expect a real divergence the first
   time (backends differ in query semantics, pagination, ranking, empty-result
   shape, or error bodies). **Fix the adapter against the contract, not the
   test.** Re-run until green.

6. **Run the after performance test and capture the console view.** Replay the
   same load test against the managed/serverless target and record the delta
   (latency, throughput, scale-to-zero / autoscaling behavior, cost model). Open
   the target's AWS console view and confirm the story visually — indexing/query
   metrics in OpenSearch Dashboards, invocation/duration/concurrency in the
   Lambda + CloudWatch dashboards, connection/ACU graphs for Aurora Serverless.

7. **Open a PR and revert cleanly.** Land the IaC + adapter + verification report
   as a PR on the namespace branch (never merge the "after" into `main`). Confirm
   the one-command revert (`terraform destroy` of the namespaced module + redeploy
   of the original adapter) returns the system to the before-state.

## Specifications (postconditions the run must satisfy)

- **Contract green against the target.** The same contract/flow suite that gates
  the original passes unchanged against the managed/serverless-backed instance —
  no test was weakened to make it pass.
- **A real divergence was caught and fixed.** The verification loop surfaced at
  least one genuine behavioral gap between backends, fixed against the contract.
- **Managed/serverless target provisioned as least-privilege IaC**, namespaced,
  with no changes to shared or `main` resources.
- **Config-flip swap.** The app selects backend by config; the original adapter
  still works; no credentials or endpoints are committed.
- **Measurable, console-visible performance delta.** A before/after load test
  with the "after" confirmed in the AWS console (CloudWatch / the target's own
  dashboard).
- **Reversible.** A single documented path (`terraform destroy` of the namespaced
  module + revert the config flip) restores the before-state.

## Worked example — the divergence the verification caught

Migrating `search-service` from self-managed **MeiliSearch** to **OpenSearch
Serverless**, the OpenSearch adapter passed a naive `match` query for
`GET /api/v1/search/?q=report`. It compiled, connected, and returned `200` — so
"looks reasonable" review would have shipped it. But the contract suite
(`tests/contract/test_search_contract.py :: TestSuggestEndpoint`) failed:

```
TestSuggestEndpoint.test_suggest_valid_prefix
  Expected: prefix "tes" returns type-ahead suggestions
  Actual:   [] — OpenSearch `match` does not do prefix matching;
            MeiliSearch is prefix-first by default
```

The MeiliSearch backend is prefix-first (type-ahead), so `/suggest` returned
hits for a 3-char prefix; the OpenSearch `match` analyzer tokenizes on whole
terms and returned nothing. The fix was to map the suggest path to an OpenSearch
`search_as_you_type` / `match_phrase_prefix` query (a mapping change + query
rewrite in the adapter), not to relax the test. Re-run: green. The point — the
contract test against the OpenAPI spec caught a semantics gap a code review of a
"clean" SDK swap would have missed.

## Advice and pointers

- Lead with the verification loop and the performance delta. If a viewer
  remembers one thing, it should be "Devin proved the managed swap was
  behavior-identical *and* showed the cloud-native win in the console."
- Prefer swaps that keep the interface stable: add an adapter selected by
  config, don't rewrite the caller. This is what makes the swap reversible and
  the diff reviewable.
- Backends differ in the "boring" places — pagination, ranking, prefix vs. token
  matching, empty-result shape, error bodies, case sensitivity. That is exactly
  where the contract suite earns its keep; mine the run for the real divergence.
- Namespaces / unmerged branches from day one: provisioned AWS resources carry a
  namespace suffix so concurrent runs and repeats never collide, and
  `terraform destroy` of just that module is the revert.
- Frame isolation as a feature: each session runs in its own VM with scoped
  credentials and its own namespace, so parallel managed-migration runs are safe.
- No overstatement for probabilistic capabilities (DeepWiki, ranking-quality
  claims) — use "typically", "coverage depends on repo structure".

## Forbidden actions

- Do **not** merge the "after" (the managed/serverless swap) into `main` — `main`
  is the durable before-state so the demo repeats. Keep it on a namespace branch.
- Do **not** weaken, skip, or edit a contract/flow test to make a migration pass.
  A divergence means the adapter is wrong, not the test.
- Do **not** mutate shared or `main` AWS resources; provision namespaced,
  least-privilege ones and destroy them on revert.
- Do **not** commit endpoints, credentials, or secrets; inject them at deploy
  time.
- Do **not** claim a performance/cost win you did not measure, and do **not**
  claim platform capabilities the environment does not support.
- Do **not** include customer-identifying content or identify the requester in
  PRs/commits (multi-tenant privacy).
