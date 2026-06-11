# Deep Security Audit — OtterWorks

> **These findings are not detectable by SAST/SCA tools** because they require cross-service reasoning, architectural context, or vulnerability chaining.

## Executive Summary

| Metric | Count |
|--------|-------|
| Services Audited | 11 backend + 2 frontends |
| Individual Findings | 14 |
| Critical (individual) | 2 |
| High (individual) | 4 |
| Medium (individual) | 5 |
| Low (individual) | 3 |
| Composite Chains | 5 |
| Critical (composite) | 3 |
| High (composite) | 2 |

**Top Risks:**
1. Multiple backend services (notification, analytics, audit, file, search) trust unauthenticated `X-User-ID` headers and are directly reachable — bypassing the gateway's JWT enforcement entirely.
2. The report-service explicitly marks all `/api/v1/reports/**` endpoints as `permitAll()` with no JWT validation.
3. The same weak default JWT secret is shared across all 11 services in docker-compose, enabling lateral movement if any single service is compromised.
4. `.trivyignore` contains a wildcard `CVE-2021-*` suppression and suppresses CVE-2025-29927 (Next.js critical middleware bypass).

---

## Architecture Overview

| Service | Language / Framework | Port | Dockerfile? | Has Own Auth? |
|---------|---------------------|------|-------------|---------------|
| api-gateway | Go / Chi | 8080 | Yes | JWT validation (gateway-level) |
| auth-service | Java / Spring Boot | 8081 | Yes | Yes (Spring Security + JWT filter) |
| file-service | Rust / Actix-web | 8082 | Yes | **No** — trusts X-User-ID header |
| document-service | Python / FastAPI | 8083 | Yes | Yes (validates JWT, fallback to X-User-ID if no secret) |
| collab-service | Node.js / Socket.io | 8084 | Yes | Yes (JWT on WebSocket handshake) |
| notification-service | Kotlin / Ktor | 8086 | Yes | **No** — trusts X-User-ID header or query param |
| search-service | Python / Flask | 8087 | Yes | **Partial** — trusts X-User-ID header presence |
| analytics-service | Scala / Akka HTTP | 8088 | Yes | **No** — zero auth |
| admin-service | Ruby / Rails | 8089 | Yes | Yes (JWT middleware, but excludes chaos/alerts) |
| audit-service | C# / ASP.NET Core | 8090 | Yes | **No** — zero auth |
| report-service | Java / Spring Boot (legacy) | 8091 | Yes | **No** — `permitAll()` on all API routes |

### Trust Boundary Map

| Boundary | Mechanism | Notes |
|----------|-----------|-------|
| External → Gateway | JWT validation (HS256/HS384) | Public paths: `/api/v1/auth/login`, `/api/v1/auth/register`, `/health`, `/metrics`, `/socket.io` |
| Gateway → Backend | `X-User-ID` header injection from JWT `sub` claim | Backend services receive identity as a trusted header |
| External → Backend (direct) | **None — ports exposed** | All backend ports (8081-8091) are mapped to the host in docker-compose |
| Service → Service (sync) | None (plain HTTP over shared network) | No mTLS, no service tokens in most inter-service calls |
| Service → Message Bus (SNS/SQS) | LocalStack with static test credentials | No message signing or source verification |
| Service → Database | Connection string in environment variables | Shared `otterworks` / `otterworks_dev` credentials across all services |
| Network Isolation | **None** | All services on single `otterworks-network`; no NetworkPolicy in k8s manifests |

---

## Individual Findings

| ID | Category | Severity | Service(s) | File : Line | Description | Scanner Visibility | Recommended Fix |
|----|----------|----------|------------|-------------|-------------|-------------------|-----------------|
| F-001 | A | High | notification-service | `services/notification-service/src/main/kotlin/com/otterworks/notification/routes/Routes.kt:55` | Reads `X-User-ID` header (or `user_id` query param) as sole identity without any JWT/auth validation. No auth middleware installed. | Not detectable by SAST — requires knowledge that the service is directly reachable | Add JWT validation middleware or reject requests without gateway-verified tokens |
| F-002 | A | High | search-service | `services/search-service/app/middleware/auth.py:55` | Accepts `X-User-ID` header presence as proof of authentication. Any non-empty value passes. | Not detectable — SAST sees it as a "header check" but can't evaluate trust boundary | Validate JWT independently or restrict network access |
| F-003 | A | High | file-service | `services/file-service/src/handlers.rs:58` | Trusts `X-User-ID` header for owner identity on file operations (upload, list, delete). No JWT middleware. | Cross-service trust assumption invisible to single-service SAST | Add JWT validation or block direct access |
| F-004 | B | Critical | report-service | `services/report-service/src/main/java/com/otterworks/report/config/SecurityConfig.java:29-36` | All `/api/v1/reports/**` endpoints are marked `permitAll()`. Comment says "TODO: Add JWT validation". Directly reachable on port 8091. | SAST flags `csrf.disable()` but cannot detect that `permitAll()` on data endpoints is a deliberate misconfiguration vs. intentional design |  Add JWT authentication filter |
| F-005 | B | Critical | analytics-service | `services/analytics-service/src/main/scala/com/otterworks/analytics/api/AnalyticsRoutes.scala` (all routes) | Zero authentication on any endpoint. User activity, document stats, storage usage, and data export endpoints are fully public on port 8088. | Not detectable — Akka HTTP routes without auth don't trigger SAST rules for "missing auth" | Add auth directive or restrict to gateway-only access |
| F-006 | B | High | audit-service | `services/audit-service/src/Controllers/AuditController.cs` (all endpoints) | No authorization middleware. Anyone can query, create, or export audit logs including user activity reports and compliance data. | Not detectable — ASP.NET Minimal API without `[Authorize]` doesn't trigger most SAST rules | Add authorization middleware |
| F-007 | C | Medium | all services | `docker-compose.yml` (11 occurrences) | All 11 services share the **identical** weak default JWT secret: `otterworks-local-dev-jwt-secret-change-me-in-production`. Compromise of one service's secret exposes all. | SAST can flag individual weak secrets but cannot detect cross-service secret reuse | Use per-service secrets or asymmetric keys (RS256) |
| F-008 | C | Medium | admin-service | `services/admin-service/config/secrets.yml:3` | Hardcoded `jwt_secret: dev_jwt_secret_key` in committed secrets.yml for development environment. Different from gateway secret, meaning admin-service can't validate gateway-issued tokens in dev. | Some SAST tools may flag this, but the cross-service key mismatch is not detectable | Remove hardcoded secrets; use environment variables consistently |
| F-009 | C | Medium | admin-service | `services/admin-service/app/controllers/api/v1/admin/chaos_controller.rb:85-90` | Chaos injection endpoint (`POST /api/v1/admin/chaos`) is excluded from JWT auth and its own secret check defaults to allow-all when `CHAOS_SECRET` env var is not set. | SAST sees `return if expected.nil?` but can't evaluate this in context of the JWT bypass | Require CHAOS_SECRET to be set; fail closed |
| F-010 | D | Medium | notification-service, audit-service | `services/notification-service/src/main/kotlin/com/otterworks/notification/consumer/SqsConsumer.kt:65-66` | SQS consumers do not verify SNS message signatures. Any entity that can publish to the shared SNS topic can inject arbitrary notifications or audit events. | Cross-service data flow not traceable by SAST | Validate SNS message signatures before processing |
| F-011 | E | Low | search-service | `services/search-service/Dockerfile:7` | Uses `COPY . .` without multi-stage build or `.dockerignore`. May copy `.env`, `.git`, test fixtures, or other sensitive files into the production image. | Some Dockerfile linters flag this but cannot assess actual exposure risk | Add `.dockerignore` or use multi-stage build |
| F-012 | E | Low | all services | `docker-compose.yml` (ports section) | All backend services expose ports directly to the host. No network segmentation between services meant for internal-only access and the external gateway. | Not detectable — infrastructure architecture decision | Remove host port mappings for internal services; only expose gateway |
| F-013 | E | Medium | file-service | `services/file-service/src/handlers.rs:355-371` | `download_file` endpoint does not verify the requesting user owns or has access to the file. Any user with a valid file_id UUID can download any file via presigned URL. | Logic flaw not pattern-matchable by SAST — requires understanding ownership model | Add owner/share permission check before generating presigned URL |
| F-014 | F | Low | .trivyignore | `.trivyignore:44` | Wildcard suppression `CVE-2021-*` blanket-ignores all 2021 CVEs. Also suppresses CVE-2025-29927 (Next.js middleware bypass, CVSS 9.1) which is directly exploitable given the frontend uses Next.js middleware for API proxying. | Scanners are explicitly told to skip these — this is the blindspot | Remove wildcard; assess each CVE individually; un-suppress CVE-2025-29927 |

---

## Composite Vulnerability Chains

### Chain C-001: Direct Port Access + Header Trust → Full Auth Bypass on Notification Service

**Attack Chain:**
1. **[F-012]** Attacker connects directly to `notification-service:8086` (port exposed to host), bypassing the API gateway
2. **[F-001]** Attacker sets `X-User-ID: <victim-uuid>` header (or passes `user_id=<victim>` as query parameter)
3. **Impact:** Read all notifications for any user, mark them as read, delete them, modify preferences — complete account takeover of notification data

**Individual Findings:** F-012 (Low), F-001 (High)
**Composite Severity:** **Critical**
**Justification:** Gateway auth enforcement is the only protection; bypassing it yields unrestricted access to user-scoped data. The query parameter fallback (`user_id=<victim>`) makes this trivially exploitable without even needing to forge headers.
**Recommended Fix:** Remove direct port exposure for notification-service OR add JWT validation middleware.

---

### Chain C-002: Direct Port Access + Zero Auth → Full Data Exfiltration on Analytics

**Attack Chain:**
1. **[F-012]** Attacker connects directly to `analytics-service:8088`
2. **[F-005]** No authentication check exists — all endpoints respond to anonymous requests
3. **Impact:** Export all user activity logs, document stats, storage usage data, and analytics dashboards. The `/api/v1/analytics/export` endpoint delivers bulk data in CSV format.

**Individual Findings:** F-012 (Low), F-005 (Critical)
**Composite Severity:** **Critical**
**Justification:** Analytics data contains user behavior patterns, document access logs, and storage metrics — valuable for reconnaissance or direct privacy violation. Zero barriers to access.
**Recommended Fix:** Add authentication to analytics-service (weakest link: F-005).

---

### Chain C-003: Shared JWT Secret + Service Compromise → Lateral Movement Across All Services

**Attack Chain:**
1. **[F-007]** All services share the same JWT signing secret (weak default value)
2. **[F-012]** Multiple services are directly accessible
3. **Impact:** An attacker who extracts the JWT secret from any single service (via config leak, SSRF, or container escape) can forge valid JWTs accepted by all 11 services. Combined with direct port access, this provides authenticated access to every service including admin endpoints.

**Individual Findings:** F-007 (Medium), F-012 (Low)
**Composite Severity:** **Critical**
**Justification:** The shared secret collapses the entire authentication perimeter. Compromising the weakest service (e.g., the zero-auth analytics-service) potentially reveals the secret, which then grants admin-level access to auth-service, admin-service, etc.
**Recommended Fix:** Use per-service secrets or migrate to asymmetric JWT (RS256) where services only hold the public key.

---

### Chain C-004: Unauthenticated Chaos Endpoint + Redis Key Injection → Denial of Service

**Attack Chain:**
1. **[F-009]** The chaos endpoint (`POST /api/v1/admin/chaos`) skips JWT auth and has no CHAOS_SECRET configured by default
2. **[F-012]** Admin-service is directly reachable on port 8089
3. **Impact:** Attacker triggers chaos scenarios (e.g., `consumer_strict_schema` on notification-service) that cause production-visible failures: queue depth climbs, notifications stop delivering, alerts fire, and Devin sessions are auto-triggered.

**Individual Findings:** F-009 (Medium), F-012 (Low)
**Composite Severity:** **High**
**Justification:** Designed as a demo tool, but without authentication it becomes a weaponized DoS vector that also generates cost (auto-triggered Devin sessions) and obscures real incidents behind chaos-induced noise.
**Recommended Fix:** Require CHAOS_SECRET configuration (fail closed, not open).

---

### Chain C-005: Direct File Service Access + Missing Download Auth Check → Unauthorized File Download

**Attack Chain:**
1. **[F-012]** Attacker connects directly to `file-service:8082`, bypassing gateway JWT
2. **[F-003]** File service trusts `X-User-ID` header for identity (attacker can set any value)
3. **[F-013]** `download_file` endpoint doesn't check if the requesting user owns or has share access to the file
4. **Impact:** Attacker enumerates files via `GET /api/v1/files` with a forged `X-User-ID`, then downloads any file by ID — achieving full file store exfiltration

**Individual Findings:** F-012 (Low), F-003 (High), F-013 (Medium)
**Composite Severity:** **High**
**Justification:** Three individually-manageable issues combine to provide unauthenticated access to the entire file store. An attacker can list files as any user and download them without ownership verification.
**Recommended Fix:** Add ownership check to download_file (breaks the chain at F-013, the cheapest fix).

---

## Suppression File Audit

| File | Suppressed ID | Assessment | Recommendation |
|------|--------------|------------|----------------|
| `.trivyignore` | CVE-2025-29927 | **Critical** — Next.js middleware authorization bypass (CVSS 9.1). The frontend uses `middleware.ts` for API proxying. An attacker can bypass the rewrite and access internal paths. Public exploit available. | **Un-suppress immediately.** Upgrade Next.js to 14.2.25+ or 15.x. |
| `.trivyignore` | CVE-2021-* (wildcard) | **Dangerous** — Blanket suppression of 100+ CVEs from 2021. Impossible to assess individual risk when all are hidden. Some 2021 CVEs have known public exploits (e.g., CVE-2021-44228 Log4Shell, CVE-2021-23337 lodash prototype pollution). | Remove wildcard. Assess each CVE individually. |
| `.trivyignore` | CVE-2025-30204 | Medium — golang-jwt/jwt DoS via crafted tokens. API gateway is the affected service. | Keep suppressed only if rate limiting mitigates (it does partially). Document rationale. |
| `.trivyignore` | CVE-2024-53981 | Medium — Redis client vulnerability affecting document-service. | Assess exploitability; likely low risk behind gateway. |
| `.trivyignore` | CVE-2024-47874 | Medium — Starlette multipart form parser DoS. Affects document-service. | Upgrade when feasible; acceptable to suppress short-term with justification. |

---

## SAST Coverage Gap Analysis

| Finding | Covered by SAST/SCA? | Custom Rule Possible? | Fundamental Limitation |
|---------|---------------------|----------------------|----------------------|
| F-001 to F-003 (Header trust) | No | Partially — could flag `X-User-ID` reads without JWT verify in same file | Requires knowing service is directly reachable (architectural context) |
| F-004, F-005, F-006 (Missing auth) | Partially — some tools flag `permitAll()` | Yes for F-004; No for F-005/F-006 (different frameworks) | Framework-specific, and "intentional public endpoint" vs "missing auth" is indistinguishable without business context |
| F-007 (Shared secret) | No | No — requires comparing values across files/services | Fundamentally cross-service reasoning |
| F-009 (Chaos auth bypass) | No | Partially — could flag `return if nil` patterns | Requires understanding the security implications of nil-means-allow |
| F-010 (Message source verification) | No | No | Cross-service data flow |
| F-013 (Download without ownership) | No | No | Logic flaw requiring business context (ownership model) |
| F-014 (Suppression wildcard) | No | Yes — lint rule for wildcard CVE patterns | Trivial custom rule |

---

## Remediation Verification

| Finding | Status | Fix Applied | Verification |
|---------|--------|-------------|-------------|
| F-001 | **Remediated** | Added `intercept` plugin to `/api/v1/notifications` and `/api/v1/preferences` route groups that rejects requests missing `X-User-ID` header with 401. Removed `user_id` query parameter fallback. | Direct request to `:8086/api/v1/notifications` without `X-User-ID` → 401 Unauthorized. Chain C-001 broken. |
| F-004 | **Remediated** | Added `GatewayAuthFilter` servlet filter that rejects requests without `X-User-ID` header before they reach Spring Security. | Direct request to `:8091/api/v1/reports` without `X-User-ID` → 401. |
| F-009 | **Remediated** | Changed `verify_chaos_secret` to return 403 when `CHAOS_SECRET` is not configured (fail-closed instead of fail-open). | `POST /api/v1/admin/chaos` without CHAOS_SECRET env var → 403 Forbidden. Chain C-004 broken. |
| F-013 | **Remediated** | Added ownership/share-access check in `download_file`. Requires `X-User-ID` header matching file owner or share list. | Request to download a file not owned/shared → 403 Forbidden. Chain C-005 broken. |
| F-014 | **Remediated** | Removed `CVE-2021-*` wildcard suppression. Un-suppressed CVE-2025-29927 (Next.js middleware bypass). | CVE-2025-29927 will now appear in Trivy scans, forcing upgrade to Next.js 14.2.25+. |
