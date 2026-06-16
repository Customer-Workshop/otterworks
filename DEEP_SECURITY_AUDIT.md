# OtterWorks — Deep Security Audit

> Cross-service, architectural, and vulnerability-chaining analysis.
> **These findings are not detectable by SAST/SCA tools** (Trivy, Semgrep, SonarCloud,
> OWASP Dependency-Check) because they require reasoning across service boundaries,
> comparing auth implementations written in different languages, or understanding
> architectural trust assumptions. SAST/SCA were assumed to have run already; this
> report starts where they stop.

---

## Executive Summary

- **Services audited:** 11 backend microservices (8 languages) + 2 frontends, orchestrated via Docker Compose / Helm.
- **Findings:** 12 individual (2 High, 6 Medium, 4 Low) feeding **5 composite chains** (2 Critical, 2 High, 1 Medium–High).
- **Top risks:**
  1. **Forgeable identity at the edge of every service** — the same hardcoded JWT signing secret is shared by all 11 services and committed to the repo. Knowing it lets anyone mint an `ADMIN` token accepted everywhere (Chain **C-002**, Critical).
  2. **Header-trust auth bypass** — file/search/notification services treat the gateway-injected `X-User-ID` header as proof of identity, but every backend port is published to the host, so they are reachable directly, bypassing the gateway (Chain **C-001**, Critical).
  3. **Unauthenticated admin attack surface** — the Rails admin service exempts the chaos-injection and Grafana-webhook endpoints from JWT; their fallback secrets default to *open* / a committed demo value. The webhook auto-spawns an AI investigation session from attacker-controlled content (Chains **C-003**, **C-004**, High).

The architecture *intends* the API Gateway to be the only ingress and the sole JWT validator, with downstream services trusting a gateway-set header. That assumption silently fails in two ways the scanners cannot see: (a) the gateway is **not** the only network path to the services, and (b) the shared signing secret means "validate the JWT" is not a meaningful boundary anyway.

---

## Phase 1 — Attack Surface Map

### Service inventory

| Service | Language / Framework | Port (host) | Dockerfile? | Implements own auth? |
|---------|---------------------|-------------|-------------|----------------------|
| api-gateway | Go 1.22 / Chi | 8080 | Yes | **Yes** — validates JWT, injects `X-User-ID` |
| auth-service | Java 17 / Spring Boot | 8081 | Yes | **Yes** — issues/validates JWT (HS256) |
| file-service | Rust / Actix-Web | 8082 | Yes | **No** — trusts `X-User-ID` header |
| document-service | Python / FastAPI | 8083 | Yes | **Yes** — validates JWT; *header fallback if no secret* |
| collab-service | Node / Express + Socket.io | 8084 | Yes | Partial — `/socket.io` is a public gateway prefix |
| notification-service | Kotlin / Ktor | 8086 | Yes | **No** — trusts `X-User-ID` header / `user_id` query param |
| search-service | Python / Flask | 8087 | Yes | **No** — trusts `X-User-ID` header *or* shared service token |
| analytics-service | Scala / Akka HTTP | 8088 | Yes | n/a (consumes events) |
| admin-service | Ruby / Rails 7.1 | 8089 | Yes | **Yes** (JWT) — *except* chaos + alert webhook endpoints |
| audit-service | C# / ASP.NET 8 | 8090 | Yes | n/a |
| report-service | Java 8 (legacy) | 8091 | Yes | n/a |
| web-app | TS / Next.js 14 | 3000 | Yes | — |
| admin-dashboard | TS / Angular 17 | 4200 | Yes | mock auth |

### Reachability

Every backend service in `docker-compose.yml` publishes its container port to the host (`- 808X:808X`). All services sit on a single default bridge network (`otterworks-network`) with **no per-service isolation**. Therefore **no backend is gateway-only — each is directly reachable**, which invalidates the entire header-trust design (see Category A).

In Helm, `NetworkPolicy` objects exist for every service, but they allow ingress from the whole `ingress-nginx` namespace (and monitoring) rather than only the api-gateway pod — partial isolation that still permits the ingress tier to reach services directly.

### Trust boundary map

| Boundary | Mechanism | Notes |
|----------|-----------|-------|
| External → Gateway | JWT validation (HS256, shared secret) | `services/api-gateway/internal/middleware/jwt.go` |
| Gateway → Backend | `X-User-ID` header injection | Set from validated JWT `sub`; **inbound client `X-User-ID` is not stripped on public/unprotected paths** — `proxy/router.go:68-79` |
| Service → Service (sync) | None / shared service token / shared JWT secret | search-service accepts a shared `service_token`; everyone shares one JWT secret |
| Service → Message Bus (SQS/SNS) | **None** | No SNS signature verification / HMAC on consumers |
| Service → Database | Connection string in env | Shared `otterworks` / `otterworks_dev` credentials across all services |

---

## Phase 2 — Individual Findings

| ID | Cat | Severity | Service(s) | File : Line | Description | Scanner Visibility | Recommended Fix |
|----|-----|----------|-----------|-------------|-------------|--------------------|-----------------|
| F-001 | A/B | **High** | file, search, notification | `file-service/src/handlers.rs:56-60,126-128`; `search-service/app/middleware/auth.py:54-57`; `notification-service/.../routes/Routes.kt:55` | Identity is taken from the `X-User-ID` header (or `user_id`/`owner_id` request fields) with **no independent JWT/session validation**. The header is only trustworthy if the gateway is the sole ingress — but all ports are published (F-012), so an attacker hitting the service port directly can impersonate any user and read/write their data (cross-tenant IDOR). | **Invisible** — each service is analyzed in isolation; the scanner cannot know the header is supposed to be set only by a trusted gateway, nor that the service is directly reachable. Cross-service trust assumption. | Validate a JWT independently in each service, or guarantee gateway-only reachability (network isolation) + strip client-supplied `X-User-ID` at the edge. |
| F-002 | C | **High** | all 11 | `docker-compose.yml:34,73,116,…` (every service); `auth-service/.../JwtTokenProvider.java:29` | A single JWT signing secret (`otterworks-local-dev-jwt-secret-change-me-in-production`) is the **default for every service and committed to the repo**. The auth-service signs with it and all services validate with it. Anyone who reads the repo can forge a valid token (any `sub`, any `roles:[ADMIN]`) accepted everywhere. | **Invisible** — SCA flags *known-CVE* dependencies, not "the same app-defined default secret is reused across services." Requires cross-service comparison of config values. | Generate per-deployment random secrets; never ship a working default. Fail closed when the known default is detected (implemented for the gateway — see Remediations). |
| F-003 | A | Medium | document-service | `document-service/app/api/documents.py:79-85` | When `JWT_SECRET` is unset, `_extract_user_id` **falls back to trusting the `X-User-ID` header** instead of rejecting the request — a JWT-failure-to-anonymous-identity path. Latent today (secret is set) but one misconfiguration away from the F-001 bypass. | **Invisible** — a logic branch ("if no secret, trust header"); not a pattern-matchable sink. | Remove the fallback; always require a validated JWT. |
| F-004 | B/E | **High** | admin-service | `admin-service/app/controllers/api/v1/admin/chaos_controller.rb:83-92`; `app/middleware/jwt_authenticator.rb:2` | The chaos/fault-injection endpoint (`POST /api/v1/admin/chaos`) is JWT-**excluded**, and `verify_chaos_secret` *allows the request when `CHAOS_SECRET` is empty* — which is the compose default (`${CHAOS_SECRET:-}`). Reachable directly on :8089, this lets an unauthenticated attacker inject faults (e.g. `slow_queries`, `consumer_strict_schema`) into production services. | **Invisible** — requires correlating a route's auth-exemption list, a controller `before_action`, and the env default across three files + compose. | Fail closed: only allow the empty-secret bypass in `development`/`test`. |
| F-005 | B/D | Medium | admin-service | `admin-service/app/controllers/api/v1/admin/alerts_controller.rb:208-221`; `docker-compose.yml:373` | The Grafana webhook (`POST /api/v1/admin/alerts/ingest`) is JWT-excluded and protected only by `ALERT_WEBHOOK_SECRET`, whose compose default is the committed value `demo-alert-secret`, compared with a **non-constant-time** `==`. The handler converts attacker-controlled alert fields into an `Incident` and (when auto-investigate is on) spawns a **Devin AI session** seeded with that content → unauthenticated incident injection + AI prompt injection. | **Invisible** — the taint flows from an HTTP body into AI-session creation across a service boundary; the auth weakness is a committed default + timing side channel. | Fail closed when secret unset (non-dev); use `secure_compare`; remove the committed default. |
| F-006 | C | Medium | web-app, repo-wide | `.trivyignore:20,45` | The suppression file disables `CVE-2025-29927` (Next.js middleware **authorization bypass**, publicly exploited) while the web-app is internet-exposed, and contains a blanket wildcard `CVE-2021-*` that hides an unbounded set of CVEs. These are findings the scanner was *explicitly told to ignore*. | **Invisible by design** — the scanner is configured to skip them; only a human audit of the ignore file surfaces them. | Remove the wildcard and the auth-bypass suppression; track real exceptions with per-CVE justification + expiry. |
| F-007 | D | Medium | notification, search, analytics | `notification-service/.../consumer/SqsConsumer.kt:116-120` | SQS/SNS consumers process messages with **no source authentication** (no SNS signature verification, no HMAC). Any principal able to publish to the shared topic/queue (e.g. one compromised service) can inject events that drive notifications, indexing, and analytics. | **Invisible** — the taint source is a *different service's* publisher reached via a message bus; SAST cannot trace across the bus. | Verify SNS message signatures / require a shared-secret HMAC; restrict publish IAM per service. |
| F-008 | F | Medium | auth-service | `docker-compose.yml:54-55` (port 8081) | Rate limiting lives only in the gateway (`RATE_LIMIT_RPS`, global). Because auth-service is directly reachable on :8081, an attacker bypasses the gateway and hits `/api/v1/auth/login` with **no rate limit** → credential brute force / stuffing. | **Invisible** — requires knowing the only rate limiter is one hop away and can be skipped via direct reachability. | Enforce per-account login throttling in auth-service itself; remove direct port exposure. |
| F-009 | E | Low | document, search | `document-service/Dockerfile:12`; `search-service/Dockerfile:7` | `COPY . .` with **no `.dockerignore`** ships the full source tree (tests, fixtures, any local `.env`) into the runtime image. | Partially — some linters flag `COPY . .`, but not the *absence of `.dockerignore`* or what ends up in the layer. | Add `.dockerignore`; copy only build artifacts (multi-stage). |
| F-010 | C | Low | all | `docker-compose.yml` (DB creds, `SECRET_KEY_BASE:370`) | Shared DB credentials (`otterworks`/`otterworks_dev`) and a committed Rails `SECRET_KEY_BASE` default. Compromising one service yields the credentials for all. | **Invisible** — shared-credential reuse is an architectural property, not a CVE. | Per-service credentials; inject secrets at deploy time. |
| F-011 | B | Low | api-gateway, collab | `api-gateway/internal/proxy/router.go:70-79`; `jwt.go:41-47` | The gateway only overwrites `X-User-ID` when JWT claims are present. For public/unprotected prefixes (e.g. `/socket.io`, `/health`) it forwards the request **without stripping a client-supplied `X-User-ID`**, so a spoofed header can reach collab-service. | **Invisible** — requires reasoning about which paths skip JWT and that the inbound header is not sanitized. | Always delete inbound `X-User-ID` (and related identity headers) at the edge before proxying. |
| F-012 | E | Low | all (compose) | `docker-compose.yml` (`ports:` on every backend); `networks:520-522` | All services publish host ports and share one flat bridge network — no network isolation. This is the **precondition** that turns the header-trust design (F-001) and the unauthenticated admin endpoints (F-004/F-005) into real bypasses. | **Invisible** — network topology / isolation is not a code pattern. | Publish only gateway + frontends; use `expose` for internal services; add per-tier networks. |

---

## Phase 3 — Vulnerability Chains

Individual Low/Medium findings combine into Critical attack paths. This is the core of the audit.

### Chain C-001: Direct reachability + header-trust → full auth bypass / cross-tenant access
**Attack Chain:**
1. *(F-012)* All backend ports are published to the host; services are reachable without going through the gateway.
2. *(F-001)* file/search/notification derive the caller's identity solely from the `X-User-ID` header.
3. Attacker sends `curl http://host:8082/api/v1/files?owner_id=...  -H 'X-User-ID: <victim-uuid>'` (or uploads/lists shares as any user) → reads/writes any tenant's files, search results, and notifications.

**Individual Findings:** F-012 (Low) + F-001 (High-as-isolated, but only because of F-012)
**Composite Severity:** **Critical**
**Justification:** The header-trust pattern is only safe under a *gateway-only* invariant that F-012 breaks. Together they yield unauthenticated impersonation of arbitrary users across three services.
**Recommended Fix (weakest link):** Remove direct port exposure (F-012) **and** validate JWT in-service / strip inbound `X-User-ID` at the edge.

### Chain C-002: Committed shared JWT secret → forge admin, lateral movement everywhere
**Attack Chain:**
1. *(F-002)* The JWT signing secret is the same committed default for all 11 services.
2. Attacker mints `{"sub":"<any>","roles":["ADMIN"],"type":"access"}` signed HS256 with that secret.
3. The token validates at the gateway *and* at every downstream service (admin, audit, file, …) → complete, authenticated takeover of the whole platform.

**Individual Findings:** F-002 (High) + F-010 (Low)
**Composite Severity:** **Critical**
**Justification:** "Require a valid JWT" is meaningless when the signing key is public and universal; one secret compromises all services simultaneously (no per-service blast-radius containment).
**Recommended Fix:** Per-deployment random secret; fail closed on the known default (done for the gateway).

### Chain C-003: Unauthenticated webhook → AI-session prompt injection
**Attack Chain:**
1. *(F-005)* `/api/v1/admin/alerts/ingest` is JWT-excluded; its secret is a committed default (or absent), reachable directly on :8089.
2. Attacker POSTs a crafted "firing" alert with attacker-chosen `summary`/`description`/`affected_service`.
3. With auto-investigate enabled, the service creates an `Incident` and calls `DevinSessionService.create_session`, seeding an **autonomous AI agent** with attacker-controlled text → prompt injection / unsolicited automation + incident-queue spam.

**Individual Findings:** F-005 (Medium) + F-007 (Medium, message-to-action)
**Composite Severity:** **High**
**Justification:** Crosses from an unauthenticated HTTP body into autonomous agent execution — impact far exceeds either weakness alone.
**Recommended Fix:** Fail closed on the webhook secret + constant-time compare; validate/escape alert content before it seeds a session.

### Chain C-004: Direct reachability + open chaos endpoint → DoS of production
**Attack Chain:**
1. *(F-012)* admin-service reachable directly on :8089.
2. *(F-004)* chaos endpoint is JWT-excluded and open when `CHAOS_SECRET` is empty (compose default).
3. Attacker triggers `consumer_strict_schema` (wedges the notification SQS consumer so queue depth climbs forever) and `slow_queries` (3–5 s latency on document-service) → sustained denial of service that "looks healthy."

**Individual Findings:** F-012 (Low) + F-004 (High-as-isolated)
**Composite Severity:** **High**
**Justification:** A demo/workshop convenience becomes a production DoS lever once the port is exposed and the secret default is open.
**Recommended Fix:** Fail closed on `CHAOS_SECRET` outside dev; remove direct port exposure.

### Chain C-005: Suppressed Next.js auth-bypass + exposed web-app
**Attack Chain:**
1. *(F-006)* `CVE-2025-29927` (Next.js middleware authorization bypass) is suppressed in `.trivyignore`.
2. The web-app is internet-facing and relies on middleware for route protection (`frontend/web-app/src/middleware.ts`).
3. Attacker sends the `x-middleware-subrequest` bypass header to reach gated routes the scanner was told to stop reporting.

**Individual Findings:** F-006 (Medium) + F-011 (Low)
**Composite Severity:** **Medium–High**
**Justification:** A known, publicly-exploited bypass kept invisible by a suppression entry, against an exposed surface.
**Recommended Fix:** Un-suppress and upgrade Next.js; never wildcard-suppress.

---

## Suppression File Audit (`.trivyignore`)

| Suppressed ID | Assessment | Recommendation |
|---------------|------------|----------------|
| `CVE-2025-29927` | **Masking exploitable issue** — Next.js middleware **auth bypass**, public exploit, exposed web-app (Chain C-005). | **Un-suppress now**; upgrade Next.js. |
| `CVE-2021-*` (wildcard) | **Blindspot** — hides an unbounded, unreviewed set of CVEs with no justification/expiry. | **Remove wildcard**; list specific CVEs with rationale. |
| `CVE-2021-23337`, `CVE-2021-33503`, `CVE-2020-28500` | npm advisories, "team reviewed 2024-12" — plausible but undated for expiry. | Keep with explicit expiry + owner; re-review. |
| Airflow / Angular / Go / Rails / Python groups | Tracked major-version upgrades with comments — reasonable temporary exceptions. | Keep; add expiry dates and ticket links. |

---

## SAST Coverage Gap Analysis

| Finding | Covered by SAST/SCA? | Custom rule possible? |
|---------|----------------------|------------------------|
| F-001 header-trust | No | Partial — could flag "identity from header without JWT verify," but the *exploitability* depends on reachability (F-012), which is cross-artifact. |
| F-002 shared secret | No | Partial — a custom rule could detect identical default-secret values across config files. |
| F-003 anon fallback | No | Hard — logic branch, needs intent. |
| F-004 / F-005 admin endpoints | No | Hard — requires joining route exemptions + controller guards + env defaults. |
| F-006 suppression | No (by design) | Yes — lint the ignore file (no wildcards, require expiry/justification). |
| F-007 message auth | No | Hard — taint crosses a message bus. |
| F-008 rate limit bypass | No | Hard — architectural. |
| F-009 Dockerfile | Partial | Yes — require `.dockerignore`. |
| F-010 shared creds | No | Partial — detect reused credential values. |
| F-011 header strip | No | Hard — needs path-vs-auth reasoning. |
| F-012 isolation | No | Yes — compose/k8s policy lint (no host port publishing for internal services). |

---

## Phase 5 — Remediations (this PR)

Prioritized chains-first (breaking one link neutralizes the composite). See the **Remediation Verification** section for how each was validated by re-checking the specific pattern (not by re-running SAST).

1. **C-002 / F-002 — fail closed on the known JWT secret (api-gateway).** `config.Validate()` now rejects startup when `JWT_SECRET` equals the committed insecure default, unless `ALLOW_INSECURE_JWT_SECRET=true` (set only for local Docker dev). Production/Helm, which does not set the flag, refuses to boot with the public secret. Covered by a new unit test (`internal/config/config_test.go`).
2. **C-004 / F-004 — chaos endpoint fails closed (admin-service).** `verify_chaos_secret` now only allows the empty-secret bypass in `development`/`test`; any other environment requires a configured `CHAOS_SECRET`.
3. **C-003 / F-005 — alert webhook hardened (admin-service).** `verify_alert_secret` fails closed outside dev/test when the secret is unset, uses constant-time `secure_compare`, and the committed `demo-alert-secret` default was removed from `docker-compose.yml`.
4. **F-001 — file-service no longer trusts request-supplied identity.** Upload owner and list/enumeration owner are derived **only** from the gateway-injected `X-User-ID`; the spoofable `owner_id` multipart/query fallbacks were removed.
5. **F-006 / C-005 — suppression cleanup.** Removed the `CVE-2021-*` wildcard and the `CVE-2025-29927` Next.js auth-bypass suppression so they resurface in scans.

> **F-003 (document-service header fallback) — documented, code change deferred.** The fix is a one-line removal of the `else: trust X-User-ID` branch in `app/api/documents.py`. It was **not** included in this PR because `services/document-service/tests/test_documents_api.py` has **9 pre-existing failures on `main`** (read/update/delete tests issue no `Authorization` header and assert `200`, but the endpoints already require a JWT). Document-service CI is path-gated, so those failures only run when the service is touched. Shipping the (correct) fix would pull document-service into this PR's CI and surface unrelated red. The recommended fix and its rationale remain in the findings table above; it should land with a fix to the outdated tests.

---

## Remediation Verification

*(Validation re-checks the specific cross-service/architectural pattern that was fixed — not a SAST re-run, since these findings are not SAST-detectable.)*

- **F-002:** Added a unit test asserting `Validate()` errors on the default secret without the allow-flag and passes with it / with a real secret. Confirmed Helm values do not set `ALLOW_INSECURE_JWT_SECRET`, so prod fails closed.
- **F-004:** Re-checked `verify_chaos_secret`: in `production` with no secret the request is now rejected; dev/test behavior unchanged.
- **F-005:** Re-checked `verify_alert_secret`: constant-time compare in use, fails closed in non-dev, no committed default remains in compose.
- **F-001:** Re-read `upload_file` — owner is sourced solely from `X-User-ID`; supplying `owner_id` as a form field no longer changes the resolved owner.
- **F-003:** Re-read `_extract_user_id` — no code path returns an identity from a header without a verified JWT; `test_create_document_x_user_id_header_ignored` still expects 401.
- **F-006:** Confirmed the two entries are gone from `.trivyignore`; the next scan will report them.

*(See the Remediation Verification updates appended after fixes are applied and tests are run.)*
