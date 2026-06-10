# Deep Security Audit — OtterWorks

> **These findings are not detectable by SAST/SCA tools because they require cross-service reasoning, architectural context, or vulnerability chaining.**

## Executive Summary

| Metric | Value |
|--------|-------|
| Services audited | 11 (api-gateway, auth-service, file-service, document-service, collab-service, notification-service, search-service, analytics-service, admin-service, audit-service, report-service) |
| Languages | Go, Java, Rust, Python (×2), Node.js/TypeScript, Kotlin, Scala, Ruby, C#, Java (legacy) |
| Total individual findings | 21 |
| Critical (composite) | 4 |
| High (individual + composite) | 5 |
| Medium | 9 |
| Low | 7 |
| Composite vulnerability chains | 7 |
| Suppression file issues | 3 |

The most severe finding is an **architecture-wide authentication bypass**: all 11 backend services are directly reachable (bypassing the API gateway) and 7 of them either have no authentication at all or trust an unauthenticated `X-User-ID` header as proof of identity. Combined with a shared weak default JWT secret across all services, an attacker with network access can impersonate any user on any service.

---

## Service Inventory

| Service | Language / Framework | Port | Dockerfile? | Has Own Auth? |
|---------|---------------------|------|-------------|---------------|
| api-gateway | Go / Chi | 8080 | Yes | JWT validation (gateway) |
| auth-service | Java / Spring Boot | 8081 | Yes | JWT + Spring Security |
| file-service | Rust / Actix-Web | 8082 | Yes | **X-User-ID header trust only** |
| document-service | Python / FastAPI | 8083 | Yes | JWT with X-User-ID fallback |
| collab-service | Node.js / Socket.IO | 8084 | Yes | JWT (WebSocket only) |
| notification-service | Kotlin / Ktor | 8086 | Yes | **None — trusts X-User-ID / query param** |
| search-service | Python / Flask | 8087 | Yes | **X-User-ID header trust only** |
| analytics-service | Scala / Akka HTTP | 8088 | Yes | **None** |
| admin-service | Ruby / Rails | 8089 | Yes | JWT + secret-header for webhooks |
| audit-service | C# / ASP.NET | 8090 | Yes | **None** |
| report-service | Java / Spring Boot (legacy JDK 8) | 8091 | Yes | **permitAll on all report endpoints** |

---

## Trust Boundary Map

| Boundary | Mechanism | Notes |
|----------|-----------|-------|
| External → Gateway | JWT validation (HMAC HS256) | Public paths: `/api/v1/auth/login`, `/api/v1/auth/register`, `/health`, `/metrics`, `/socket.io` |
| Gateway → Backend | `X-User-ID` header injection | Set from validated JWT `sub` claim |
| Service → Service (sync) | **None** | No service tokens, no mTLS — services call each other over plain HTTP |
| Service → Message Bus (SNS/SQS) | AWS IAM (IRSA in k8s) / LocalStack creds (dev) | No SNS signature validation by consumers |
| Service → Database | Connection string in env vars | Shared password `otterworks_dev` in docker-compose |
| External → Backend (direct) | **None** | All services expose ports in docker-compose; k8s NetworkPolicies exist but docker-compose has flat network |

---

## Individual Findings

| ID | Category | Severity | Service(s) | File : Line | Description | Scanner Visibility | Recommended Fix |
|----|----------|----------|------------|-------------|-------------|-------------------|-----------------|
| F-001 | A | Medium | search-service | `services/search-service/app/middleware/auth.py:55` | Accepts `X-User-ID` header as sole authentication; no JWT validation. Combined with direct port exposure, any caller can impersonate any user. | Not detectable — cross-service trust assumption | Add JWT validation; only fall back to X-User-ID when JWT is absent AND request originates from a trusted source |
| F-002 | A | Medium | notification-service | `services/notification-service/src/main/kotlin/com/otterworks/notification/routes/Routes.kt:55` | Trusts `X-User-ID` header **or `user_id` query parameter** as identity with no auth middleware. Query-param fallback makes spoofing trivial. | Not detectable — cross-service trust assumption | Add JWT or service-token validation middleware |
| F-003 | A | Medium | file-service | `services/file-service/src/handlers.rs:56-60` | Uses `X-User-ID` header as authenticated owner with no independent JWT check on HTTP endpoints. | Not detectable — cross-service trust assumption | Add JWT validation middleware to Actix-Web |
| F-004 | A | Medium | document-service | `services/document-service/app/api/documents.py:79-85` | When `JWT_SECRET` is empty/unset, falls back to trusting `X-User-ID` header — conditional auth bypass. | Not detectable — requires understanding env-dependent code paths | Reject requests when JWT_SECRET is not configured instead of falling back |
| F-005 | B | High | audit-service | `services/audit-service/Program.cs:93-133` | **Zero authentication** on all endpoints including `POST /events`, `POST /archive`, `GET /export`. Any network-reachable caller can record fake audit events or export the full audit log. | Not detectable — absence of auth is architectural, not a pattern match | Add JWT validation middleware |
| F-006 | B | High | analytics-service | `services/analytics-service/src/main/scala/com/otterworks/analytics/Main.scala:34-38` | **Zero authentication** on all endpoints including user activity reports, dashboard data, event ingestion, and data export. | Not detectable — absence of auth is architectural | Add auth directive to Akka HTTP routes |
| F-007 | B | High | report-service | `services/report-service/src/main/java/com/otterworks/report/config/SecurityConfig.java:36` | `.antMatchers("/api/v1/reports/**").permitAll()` — all report endpoints are explicitly unauthenticated. Code comment reads `// TODO: Add JWT validation`. | SAST sees `permitAll()` but can't assess whether it's intentional; this requires architectural context | Change to `.authenticated()` and add JWT filter |
| F-008 | B | Medium | admin-service | `services/admin-service/app/middleware/jwt_authenticator.rb:2` | Alert ingest and chaos endpoints excluded from JWT auth. Secret-header fallback allows bypass when `ALERT_WEBHOOK_SECRET` has weak default (`demo-alert-secret`) or `CHAOS_SECRET` is empty (dev mode). | Not detectable — requires reasoning about env-var defaults and fallback logic | Remove endpoints from EXCLUDED_PATHS; validate secrets in the controller `before_action` after JWT middleware runs |
| F-009 | B | Medium | notification-service | `services/notification-service/src/main/kotlin/com/otterworks/notification/routes/Routes.kt:165` | WebSocket `/ws/notifications/{userId}` accepts any `userId` from URL path with no token validation. Attacker can subscribe to any user's real-time notifications. | Not detectable — WebSocket auth gaps are not pattern-matchable | Require JWT token as query param or first frame; validate before adding connection |
| F-010 | C | Medium | all services | `docker-compose.yml:34,73,116,159,199,242,284,324,364,415,467` | **Identical weak JWT secret** shared across all 11 services: `otterworks-local-dev-jwt-secret-change-me-in-production`. Compromise of any one service's config gives full impersonation across all services. | Not detectable — requires comparing env vars across services | Use per-service secrets or asymmetric keys; rotate shared secret |
| F-011 | C | Low | admin-service | `services/admin-service/config/secrets.yml:3` | Hardcoded `dev_jwt_secret_key` in secrets.yml differs from the shared JWT secret. JWTs issued by auth-service won't validate in admin-service when using this config. | Partially detectable (hardcoded secret) but the cross-service mismatch is not | Use env-var-sourced secret consistently |
| F-012 | C | Low | admin-service | `docker-compose.yml:370` | Hardcoded `SECRET_KEY_BASE: dev-secret-key-base-otterworks-change-in-production` in compose. | Detectable by secret scanners but severity assessment requires context | Source from env var |
| F-013 | C | Medium | all | `.trivyignore:45` | Wildcard `CVE-2021-*` suppresses ALL 2021 CVEs including potentially exploitable ones (e.g., Log4Shell-era vulnerabilities). No justification comment. | **This is a scanner blindspot by design** — Trivy was told to ignore these | Remove wildcard; enumerate specific CVEs with justifications |
| F-014 | C | Medium | web-app | `.trivyignore:20` | CVE-2025-29927 (Next.js middleware authorization bypass) is suppressed. If the web-app uses Next.js middleware for auth routing, this is exploitable. | **Scanner was told to skip this** | Evaluate and un-suppress or upgrade Next.js |
| F-015 | D | Medium | audit-service | `services/audit-service/src/Services/SnsConsumer.cs:103-106` | SQS consumer blindly deserializes any JSON message as `FileEventMessage` or `AuditEventMessage` with no schema validation or source verification. | Not detectable — cross-service data flow via message bus | Add schema validation; verify SNS message signature |
| F-016 | D | Medium | analytics-service | `services/analytics-service/src/main/scala/com/otterworks/analytics/service/EventProcessor.scala:77-86` | SQS consumer decodes events and passes `userId`, `resourceId` directly to DB operations without sanitization. | Not detectable — taint source is in a different service | Validate message schema; sanitize fields |
| F-017 | D | Low | audit-service, notification-service, analytics-service, search-service | Multiple SQS consumers | No SNS message signature validation in any consumer. Any entity that can publish to the SNS topic (or access LocalStack) can inject events. | Not detectable — requires cross-service trust analysis | Validate SNS `SignatureVersion`/`Signature` on received messages |
| F-018 | E | Low | all services | `docker-compose.yml` (all `ports:` directives) | Every service has host port mappings, making all directly reachable without going through the API gateway. Docker-compose uses a single flat network with no segmentation. | Not detectable — requires architectural understanding of gateway role | Remove external port mappings for non-gateway services; use internal-only networking |
| F-019 | E | Medium | search-service, document-service, audit-service, api-gateway, admin-service | `services/*/Dockerfile` | `COPY . .` without `.dockerignore` files. Build context may include `.env`, `.git/`, test fixtures, or secrets. | Partially detectable — SAST flags `COPY . .` but can't assess what's in the context | Add `.dockerignore` excluding `.env`, `.git`, `*.md`, test dirs |
| F-020 | E | Low | search-service | `services/search-service/Dockerfile:7` | Single-stage build — dev dependencies, build tools, and full source ship in the production image. | Partially detectable but requires multi-stage build reasoning | Convert to multi-stage build |
| F-021 | F | Low | notification-service | `services/notification-service/src/main/kotlin/com/otterworks/notification/routes/Routes.kt:55,78,88` | No rate limiting on notification endpoints when accessed directly. Combined with no auth, enables unbounded enumeration. | Not detectable — requires cross-service reasoning about rate limiting placement | Add per-IP rate limiting at service level |

---

## Composite Vulnerability Chains

### Chain C-001: Direct Port Access + X-User-ID Trust → Full Search Tenant Isolation Bypass

**Attack Chain:**
1. **Leverage F-018** (exposed port): Attacker connects directly to `search-service:8087`, bypassing the API gateway entirely.
2. **Leverage F-001** (X-User-ID trust): Attacker sets `X-User-ID: <victim-uuid>` header on the request.
3. **Impact**: Attacker can search, view, and enumerate all documents belonging to any user — full tenant isolation bypass.

**Individual Findings:** F-018 (Low), F-001 (Medium)
**Composite Severity:** **Critical**
**Justification:** Tenant isolation is the fundamental security boundary in a multi-user document platform. Bypassing it exposes all user content.
**Recommended Fix:** Add JWT validation to search-service (breaks the chain regardless of network exposure).

---

### Chain C-002: Direct Port Access + X-User-ID Trust → Notification Hijacking for Any User

**Attack Chain:**
1. **Leverage F-018** (exposed port): Attacker connects to `notification-service:8086`.
2. **Leverage F-002** (X-User-ID or query param trust): Attacker sets `user_id=<victim-uuid>` as query parameter.
3. **Impact**: Read all notifications, mark as read (DoS — victim misses alerts), delete notifications, subscribe to real-time WebSocket feed.

**Individual Findings:** F-018 (Low), F-002 (Medium), F-009 (Medium)
**Composite Severity:** **High**
**Justification:** Notification hijacking enables social engineering (reading password reset links, security alerts) and denial of service.
**Recommended Fix:** Add auth middleware to notification-service; require token for WebSocket.

---

### Chain C-003: Direct Port Access + X-User-ID Trust → File Upload/Access as Any User

**Attack Chain:**
1. **Leverage F-018** (exposed port): Attacker connects to `file-service:8082`.
2. **Leverage F-003** (X-User-ID trust): Attacker sets `X-User-ID: <victim-uuid>`.
3. **Impact**: Upload malicious files to victim's account, list and download victim's files, share files to exfiltrate data.

**Individual Findings:** F-018 (Low), F-003 (Medium)
**Composite Severity:** **High**
**Justification:** File access represents the core data asset of the platform.
**Recommended Fix:** Add JWT validation to file-service Actix handlers.

---

### Chain C-004: Shared Weak JWT Secret → Forge Tokens → Lateral Movement Across All Services

**Attack Chain:**
1. **Leverage F-010** (shared weak default secret): The secret `otterworks-local-dev-jwt-secret-change-me-in-production` is readable in `docker-compose.yml` (or any service's env).
2. **Forge JWT**: Attacker creates a valid JWT with arbitrary `sub`, `email`, `roles` claims signed with the known secret.
3. **Impact**: Forged JWT is accepted by all 11 services. Attacker has full authenticated access as any user with any role on every service simultaneously.

**Individual Findings:** F-010 (Medium), F-018 (Low)
**Composite Severity:** **Critical**
**Justification:** A single known secret compromises the entire authentication perimeter across all services. Even services with proper JWT validation (auth-service, collab-service, admin-service) are defeated.
**Recommended Fix:** Use unique per-service secrets or asymmetric signing (RS256 with public key distribution). Never embed defaults in source-controlled compose files.

---

### Chain C-005: Unauthenticated Audit Endpoints + Blind Message Deserialization → Audit Trail Poisoning

**Attack Chain:**
1. **Leverage F-005** (no audit auth): Attacker calls `POST /api/v1/audit/events` directly on port 8090 with fabricated audit events.
2. **Leverage F-015** (blind deserialization): Alternatively, attacker publishes crafted messages to the SNS topic; the SQS consumer ingests them without validation.
3. **Impact**: Fabricated audit trail — attacker can plant evidence of actions that never happened or flood the audit log to obscure real malicious activity. `POST /archive` can trigger premature archival, `GET /export` leaks the full audit trail.

**Individual Findings:** F-005 (High), F-015 (Medium)
**Composite Severity:** **Critical**
**Justification:** Audit integrity is a compliance requirement. Poisoned audit logs undermine forensics, incident response, and regulatory reporting.
**Recommended Fix:** Add JWT validation to audit-service; validate SNS message signatures.

---

### Chain C-006: Unauthenticated Report + Analytics Services → Business Intelligence Exfiltration

**Attack Chain:**
1. **Leverage F-007** (report-service permitAll): Attacker accesses `report-service:8091/api/v1/reports/*` — all report generation endpoints are public.
2. **Leverage F-006** (analytics-service no auth): Attacker accesses `analytics-service:8088/api/v1/analytics/*` — dashboard summaries, user activity, document stats, storage usage, and CSV/JSON export.
3. **Impact**: Complete exfiltration of business intelligence: who uses the platform, what they work on, storage patterns, collaboration metrics.

**Individual Findings:** F-007 (High), F-006 (High)
**Composite Severity:** **Critical**
**Justification:** Business intelligence data reveals organizational structure, project details, and user behavior — high-value for competitive intelligence.
**Recommended Fix:** Fix report-service `permitAll` to `.authenticated()` (one-line change breaks this chain).

---

### Chain C-007: Weak Default Chaos Secret + JWT Bypass → Service Disruption via Chaos Injection

**Attack Chain:**
1. **Leverage F-008** (chaos endpoint exempt from JWT): The chaos endpoint is excluded from JWT auth in `jwt_authenticator.rb`.
2. **Leverage empty CHAOS_SECRET**: In dev/default config, `CHAOS_SECRET` is empty string, so `verify_chaos_secret` returns early (allows all).
3. **Impact**: Attacker triggers chaos scenarios on any service (S3 errors, strict JSON parsing, query latency), causing real user-facing outages.

**Individual Findings:** F-008 (Medium)
**Composite Severity:** **High**
**Justification:** Chaos engineering endpoints are designed to break services. Exposing them without strong auth turns a testing tool into an attack vector.
**Recommended Fix:** Remove `/api/v1/admin/chaos` from EXCLUDED_PATHS; require both JWT and chaos secret.

---

## Suppression File Audit

| File | Suppressed ID | Assessment | Recommendation |
|------|--------------|------------|----------------|
| `.trivyignore:45` | `CVE-2021-*` (wildcard) | **Dangerous** — blanket suppression of all 2021 CVEs. This could mask Log4Shell (CVE-2021-44228) and hundreds of other exploitable vulnerabilities. No justification provided. | **Remove immediately.** Enumerate specific CVEs with inline justification comments. |
| `.trivyignore:20` | CVE-2025-29927 | **Risky** — Next.js middleware authorization bypass. If `web-app` uses Next.js middleware for auth gating, this is a direct auth bypass. | Assess whether Next.js middleware is used for auth; if so, prioritize upgrade. |
| `.trivyignore:29` | CVE-2025-30204 | JWT library vulnerability in api-gateway's Go dependencies. Given the gateway is the primary auth enforcement point, this warrants investigation. | Evaluate impact; prioritize upgrade of `golang-jwt/jwt` if exploitable in current usage. |

---

## SAST Coverage Gap Analysis

| Finding | Covered by SAST/SCA? | Custom Rule Possible? | Requires Cross-Service Reasoning? |
|---------|----------------------|----------------------|----------------------------------|
| F-001 – F-004 (X-User-ID trust) | No | Partial — can flag X-User-ID reads, but can't determine if gateway is the only caller | **Yes** — must know gateway sets the header after JWT validation |
| F-005 – F-007 (missing auth) | No (absence of code isn't a pattern) | No — can't rule-match "auth middleware not installed" | **Yes** — requires understanding the expected auth architecture |
| F-008 (exempt endpoints + weak secrets) | Partial — can flag hardcoded defaults | No — requires env-var default analysis + auth exclusion list reasoning | **Yes** |
| F-009 (WebSocket no auth) | No | Partial — can flag WebSocket without auth checks | **Yes** — must understand expected auth model |
| F-010 (shared JWT secret) | No | No — requires comparing env vars across compose services | **Yes** |
| F-013 – F-014 (suppression audit) | **No — by definition** | N/A — these are scanner configuration issues | No, but requires human judgment |
| F-015 – F-017 (event bus) | No | No — taint across message buses isn't traced | **Yes** |
| F-018 (flat network) | No | No — requires architectural context | **Yes** |
| All 7 chains | **No** | **No** | **Yes — chaining is fundamentally cross-service** |

---

## Remediation Verification

*Updated after Phase 5 remediations — see below.*

| Finding | Remediated? | Verification |
|---------|-------------|--------------|
| F-007 | Yes | `report-service` `ReportAuthFilter` validates JWT HMAC-SHA256 signature on `/api/v1/reports/**` using `JWT_SECRET` (no external library — uses `javax.crypto.Mac`); chain C-006 broken |
| F-008 | Yes | `/api/v1/admin/chaos` removed from `EXCLUDED_PATHS`; JWT now required before chaos controller secret check (defense-in-depth). `/api/v1/admin/alerts/ingest` remains excluded because Grafana webhooks authenticate via `X-Alert-Secret` header, not JWT; chain C-007 broken |
| F-001 | Yes | `search-service` auth middleware validates JWT independently; `X-User-ID` header alone is no longer sufficient — a valid JWT or service token must accompany every request; chain C-001 broken |
| F-013 | Yes | Wildcard `CVE-2021-*` removed from `.trivyignore`; individual pre-existing low-priority entries retained with line-level comments |
| F-009 | Yes | Notification-service WebSocket now requires `token` query parameter validated as JWT before connection is established |
