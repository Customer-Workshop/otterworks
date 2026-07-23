# /// script
# requires-python = ">=3.11"
# dependencies = ["psycopg2-binary", "bcrypt"]
# ///
"""
OtterWorks GOLDEN reference synthetic-data generator.

Produces a large, realistic, internally-consistent dataset that mirrors a busy,
real company. It is loaded once into the permanent shared reference database and
used as the starting state for demos.

Design goals:
  * Deterministic — a fixed random seed makes every run structurally identical,
    so the dataset is reproducible and re-runnable.
  * Namespaced — writes to schema ``otterworks_<ns>`` (``--ns golden`` by
    default), so it never collides with other test-data runs.
  * Valid — respects every enum, foreign key, uniqueness, temporal-ordering and
    business rule enforced by ``testdata/harness/validate.py``.

Usage:
    make testdata-setup-schema NS=golden
    python testdata/generated/golden/generate.py --ns golden
    make testdata-validate NS=golden CRITERIA=testdata/generated/golden/criteria.json

Environment overrides (defaults match docker-compose.infra.yml):
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
"""

from __future__ import annotations

import argparse
import os
import random
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import psycopg2
from psycopg2.extras import Json, execute_values

# ── Scale ─────────────────────────────────────────────────────────────────────
# Roughly models a mid-size engineering org with ~18 months of activity.

DEFAULT_SEED = 20240117
NUM_USERS = 500
NUM_ADMIN_USERS = 25
NUM_AUDIT_LOGS = 5000
NUM_FEATURE_FLAGS = 30
NUM_ANNOUNCEMENTS = 20
NUM_INCIDENTS = 50
NUM_SYSTEM_CONFIGS = 40

HISTORY_DAYS = 540  # ~18 months

# ── Deterministic UUIDs ───────────────────────────────────────────────────────
# uuid5 keeps IDs stable across runs so cross-table FK references always resolve.

NS_UUID = uuid.UUID("9f1e2d3c-4b5a-6c7d-8e9f-0a1b2c3d4e5f")


def stable_id(category: str, index: int) -> str:
    return str(uuid.uuid5(NS_UUID, f"golden::{category}::{index}"))


# ── Time helpers ──────────────────────────────────────────────────────────────

def now() -> datetime:
    return datetime.now(timezone.utc)


# ── Reference data pools ──────────────────────────────────────────────────────

DEPARTMENTS = [
    "Platform Engineering", "Backend", "Frontend", "Mobile", "DevOps",
    "SRE", "QA", "Data Engineering", "Data Science", "ML Engineering",
    "Security", "Infrastructure", "Product", "Design", "Developer Experience",
    "Support", "IT", "Finance", "Legal", "People Ops",
]

_DEPT_WEIGHTS = {
    "Platform Engineering": 30, "Backend": 35, "Frontend": 25, "Mobile": 15,
    "DevOps": 18, "SRE": 14, "QA": 16, "Data Engineering": 18,
    "Data Science": 12, "ML Engineering": 12, "Security": 8,
    "Infrastructure": 14, "Product": 14, "Design": 10,
    "Developer Experience": 10, "Support": 16, "IT": 8, "Finance": 6,
    "Legal": 4, "People Ops": 6,
}
_DEPT_POPULATION: list[str] = []
for _d in DEPARTMENTS:
    _DEPT_POPULATION.extend([_d] * _DEPT_WEIGHTS.get(_d, 8))

TEAMS = [
    "Core API", "Auth Team", "Search Team", "Billing", "Notifications",
    "CI/CD", "Observability", "Data Pipeline", "ML Platform", "Mobile iOS",
    "Mobile Android", "Web Platform", "Design Systems", "Security Ops",
    "Infra Automation", "Release Engineering", "Developer Tools",
    "Performance", "Reliability", "Growth",
]

FIRST_NAMES = [
    "Aarav", "Abigail", "Adaeze", "Aditya", "Akiko", "Alejandro", "Amara",
    "Amina", "Anastasia", "Andrei", "Ananya", "Antonio", "Arjun", "Arun",
    "Ayumi", "Benjamin", "Bianca", "Boris", "Camila", "Carlos", "Carmen",
    "Chandra", "Charlotte", "Chen", "Chidinma", "Chloe", "Daisuke", "Daniel",
    "Daniela", "David", "Deepika", "Diego", "Dmitri", "Elena", "Elif",
    "Emeka", "Emma", "Enrique", "Erik", "Esperanza", "Ethan", "Farah",
    "Fatima", "Felix", "Fernanda", "Gabriel", "Gabriela", "Gita", "Grace",
    "Haruki", "Hassan", "Helena", "Henrik", "Hugo", "Ibrahim", "Ingrid",
    "Isabella", "Javier", "Jia", "Jin", "Jonas", "Jorge", "Josephine",
    "Juan", "Julia", "Jun", "Kaia", "Kai", "Kamila", "Kaori", "Karthik",
    "Kavya", "Kenji", "Khadija", "Kofi", "Kwame", "Layla", "Leandro",
    "Lena", "Leo", "Li", "Liam", "Linh", "Lucia", "Luis", "Luna",
    "Magdalena", "Mai", "Malik", "Manish", "Mara", "Marco", "Maria",
    "Mariana", "Marina", "Mateo", "Maya", "Mei", "Michael", "Miguel",
    "Mika", "Min", "Miriam", "Mohammed", "Naomi", "Nadia", "Naveen",
    "Neha", "Nia", "Nikolai", "Nina", "Noah", "Nora", "Obinna", "Olga",
    "Oliver", "Omar", "Paloma", "Paolo", "Petra", "Priya", "Qiang",
    "Rafael", "Rahul", "Rania", "Raquel", "Rashid", "Ren", "Ricardo",
    "Rosa", "Rui", "Sakura", "Samuel", "Sandra", "Santiago", "Sara",
    "Sasha", "Satoshi", "Sebastian", "Shreya", "Sofia", "Soren", "Suki",
    "Sunita", "Takeshi", "Tanya", "Tariq", "Tatiana", "Thiago", "Tomoko",
    "Umar", "Valentina", "Viktor", "Wei", "Xiomara", "Yara", "Yuki",
    "Yusuf", "Zara", "Zhi",
]

LAST_NAMES = [
    "Abadi", "Achebe", "Adeyemi", "Aguilar", "Ahmed", "Akiyama", "Alvarez",
    "Andersen", "Antonov", "Arora", "Bautista", "Bergstrom", "Bhatt",
    "Bianchi", "Boateng", "Brennan", "Castillo", "Chakraborty", "Chan",
    "Chang", "Chen", "Cho", "Costa", "Cruz", "Dahl", "Das", "Delgado",
    "Desai", "Diallo", "Dimitrov", "Dubois", "Duong", "Eriksson", "Espinoza",
    "Fernandez", "Fischer", "Flores", "Fujimoto", "Garcia", "Gomes",
    "Gonzalez", "Gupta", "Gutierrez", "Hansen", "Hara", "Hayashi",
    "Hernandez", "Holm", "Huang", "Hussein", "Inoue", "Islam", "Ito",
    "Ivanov", "Jain", "Jensen", "Johansson", "Johnson", "Kang", "Kapoor",
    "Kawamura", "Khan", "Kim", "Kowalski", "Kumar", "Larsson", "Lee",
    "Li", "Lim", "Liu", "Lopez", "Lundgren", "Machado", "Malik", "Martinez",
    "Matsumoto", "Mendes", "Meyer", "Mishra", "Morales", "Moreau", "Mori",
    "Muller", "Nakamura", "Narang", "Navarro", "Nguyen", "Nielsen", "Nwosu",
    "Ochoa", "Okamoto", "Okafor", "Oliveira", "Ortega", "Ortiz", "Ota",
    "Owusu", "Ozturk", "Patel", "Park", "Perez", "Petrov", "Pham",
    "Popov", "Prasad", "Quispe", "Rahman", "Ramirez", "Rao", "Reddy",
    "Reyes", "Rivera", "Rodriguez", "Rossi", "Roy", "Ruiz", "Saarinen",
    "Saito", "Salazar", "Santos", "Sato", "Schmidt", "Shah", "Sharma",
    "Silva", "Singh", "Smirnov", "Sokolov", "Soto", "Suzuki", "Takahashi",
    "Tanaka", "Tran", "Torres", "Ueda", "Vargas", "Vasquez", "Volkov",
    "Wang", "Weber", "Williams", "Wong", "Wu", "Yamamoto", "Yang", "Yilmaz",
    "Yoshida", "Zhang", "Zhou",
]

SUSPENDED_REASONS = [
    "Repeated policy violations",
    "Unauthorized data export attempt",
    "Account compromised — pending investigation",
    "Extended leave of absence",
    "Failed security audit review",
    "Pending HR disciplinary review",
    "Suspicious login activity detected",
    "Non-compliance with MFA requirement",
]

_GB = 1024 ** 3
TIER_SPECS = {"free": 5 * _GB, "basic": 50 * _GB, "pro": 200 * _GB, "enterprise": 1024 * _GB}
TIER_WEIGHTS = [("free", 20), ("basic", 30), ("pro", 35), ("enterprise", 15)]
_TIER_NAMES = [t for t, _ in TIER_WEIGHTS]
_TIER_W = [w for _, w in TIER_WEIGHTS]

BROWSER_UAS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
]
SYSTEM_UA = "OtterWorks-API/1.0"

RESOURCE_ACTIONS: dict[str, list[str]] = {
    "AdminUser": [
        "user.created", "user.updated", "user.suspended", "user.activated",
        "user.deactivated", "user.role_changed", "user.password_reset",
    ],
    "StorageQuota": ["quota.updated", "quota.upgraded"],
    "FeatureFlag": ["feature_flag.created", "feature_flag.updated", "feature_flag.toggled"],
    "SystemConfig": ["config.updated", "config.created"],
    "Announcement": ["announcement.created", "announcement.updated", "announcement.published"],
    "Incident": ["incident.created", "incident.updated", "incident.resolved"],
    "ApiKey": ["api_key.created", "api_key.revoked"],
    "Export": ["export.requested", "export.completed"],
    "Document": ["document.created", "document.updated", "document.deleted", "document.shared"],
    "File": ["file.uploaded", "file.downloaded", "file.deleted", "file.restored"],
}
SYSTEM_ACTIONS = [
    ("system.backup_completed", "SystemConfig"),
    ("system.maintenance_started", "SystemConfig"),
    ("system.maintenance_completed", "SystemConfig"),
    ("system.index_rebuilt", "SystemConfig"),
]

FEATURE_FLAGS = [
    ("dark_mode_v2", "Toggle dark mode V2 UI across web and mobile clients"),
    ("realtime_collab", "Enable real-time collaborative editing via CRDT sync"),
    ("ai_code_review", "AI-powered code review suggestions on pull requests"),
    ("new_search_engine", "Switch to the new full-text search backend"),
    ("graphql_api", "Expose the GraphQL API layer for external integrations"),
    ("kubernetes_autoscale", "Enable HPA-based autoscaling for all deployments"),
    ("observability_dashboard_v3", "Rollout of the redesigned observability dashboard"),
    ("sso_okta_integration", "Okta SSO provider support for enterprise tenants"),
    ("webhook_retry_v2", "Exponential backoff retry logic for webhook delivery"),
    ("batch_export", "Allow bulk CSV/JSON export of workspace data"),
    ("mobile_push_notifications", "Push notification support for iOS and Android"),
    ("advanced_rbac", "Granular role-based access control with custom roles"),
    ("audit_log_export", "Export audit logs to external SIEM integrations"),
    ("ai_document_summary", "AI-generated summaries for uploaded documents"),
    ("file_versioning_v2", "Improved file version history with diff viewer"),
    ("custom_workflows", "User-defined approval and review workflows"),
    ("api_rate_limiting_v2", "Token-bucket rate limiting with per-tenant quotas"),
    ("elasticsearch_migration", "Migrate search index from Solr to Elasticsearch"),
    ("redis_cache_layer", "Enable Redis caching layer for hot-path queries"),
    ("ci_cd_pipeline_v2", "Next-gen CI/CD pipeline with parallel stage execution"),
    ("canary_deployments", "Canary deployment strategy for production rollouts"),
    ("feature_flag_analytics", "Track flag evaluation metrics and exposure events"),
    ("user_impersonation", "Allow admins to impersonate users for debugging"),
    ("bulk_user_import", "Bulk user provisioning via CSV upload"),
    ("slack_integration_v2", "Bidirectional Slack integration with thread sync"),
    ("teams_integration", "Microsoft Teams notifications and bot commands"),
    ("jira_sync", "Two-way sync between internal tasks and Jira issues"),
    ("github_pr_linking", "Auto-link GitHub PRs to internal documents"),
    ("automated_backups_v2", "Incremental backup strategy with point-in-time restore"),
    ("data_retention_policies", "Configurable data retention and auto-purge rules"),
    ("gdpr_export_tool", "Self-service GDPR data export for end users"),
    ("incident_auto_escalation", "Auto-escalate unacknowledged incidents after SLA breach"),
    ("performance_profiler", "In-app performance profiling with flame graphs"),
    ("smart_notifications", "ML-based notification batching and prioritization"),
]

ANNOUNCEMENTS = [
    ("New CI/CD pipeline dashboard now available",
     "The revamped CI/CD pipeline dashboard is live in the developer portal with "
     "build history, deployment frequency, and failure rates across all services.",
     "info", "active", ["DevOps", "Backend", "Frontend"], [], 3, 30),
    ("Platform latency improvements — P99 reduced by 40%",
     "After the infrastructure push we reduced P99 API latency from 210 ms to 125 ms "
     "across all public endpoints. Grafana baselines were updated accordingly.",
     "info", "active", [], [], 7, None),
    ("Welcome new SRE team members!",
     "Please welcome the engineers joining the SRE team this week. They will be "
     "ramping up on the on-call rotation over the next two sprints.",
     "info", "active", ["SRE", "Infrastructure"], [], 2, 14),
    ("Kubernetes certification workshop — sign up now",
     "We are offering a sponsored CKA certification prep workshop. Sessions run every "
     "Wednesday for six weeks. Register via the Learning Portal to reserve your spot.",
     "info", "active", [], [], 5, 20),
    ("New Slack channel: #platform-announcements",
     "All platform-wide announcements will now be mirrored to #platform-announcements. "
     "Subscribe to stay informed about maintenance windows and incident updates.",
     "info", "active", [], [], 10, None),
    ("OpenTelemetry tracing enabled for all services",
     "Distributed tracing via OpenTelemetry is now enabled across the service mesh. "
     "Traces are exported to Grafana Tempo and queryable from the Explore tab.",
     "info", "active", [], [], 6, None),
    ("Upcoming: GitHub Copilot enterprise rollout",
     "We are planning to roll out Copilot Business licenses to all engineering staff. "
     "A pilot group will start next quarter; enrollment details to follow.",
     "info", "draft", [], [], None, None),
    ("Draft: New on-call compensation policy",
     "Leadership is finalizing a revised on-call compensation policy that includes "
     "tiered pay for weeknight and weekend pages. Review concludes end of month.",
     "info", "draft", ["SRE", "DevOps", "Infrastructure"], [], None, None),
    ("Draft: Shared component library v2 RFC open for review",
     "The Design Systems team published an RFC for the next major version of the shared "
     "component library, including tree-shakeable exports. Comment by end of week.",
     "info", "draft", ["Frontend", "Design", "Developer Experience"], [], None, None),
    ("Office network maintenance completed",
     "The scheduled office network maintenance has completed. All VPN tunnels and "
     "internal DNS resolvers are restored to normal operation.",
     "info", "expired", [], [], 45, -5),
    ("Hackathon results announced",
     "Congratulations to the winning team for their real-time anomaly detection "
     "prototype. All project repos have been archived under the hackathon org.",
     "info", "expired", [], [], 60, -10),
    ("Mandatory password rotation by end of quarter",
     "Per the updated security policy, all employees must rotate their SSO passwords. "
     "Accounts with passwords older than 90 days will be locked.",
     "warning", "active", [], [], 15, 7),
    ("Legacy REST API v1 sunset scheduled",
     "REST API v1 will be permanently decommissioned. All consumers must migrate to v2 "
     "beforehand. The migration guide and compatibility shim are in the API wiki.",
     "warning", "active", ["Backend", "Platform Engineering"], [], 30, 60),
    ("Updated data retention policy effective next month",
     "The revised data retention policy takes effect soon. PII in non-production "
     "databases must be purged within 30 days of creation.",
     "warning", "active", ["Data Engineering", "Data Science", "Security"], [], 10, 25),
    ("SOC 2 audit preparation — action items for all teams",
     "Our annual SOC 2 Type II audit begins soon. Every team must verify access reviews "
     "are current and runbooks are up to date.",
     "warning", "active", [], ["admin"], 5, 40),
    ("Draft: Deprecation of internal PyPI mirror",
     "We are planning to deprecate the self-hosted PyPI mirror in favor of Artifactory. "
     "A migration timeline will be shared after security review.",
     "warning", "draft", ["Data Engineering", "ML Engineering", "Backend"], [], None, None),
    ("VPN certificate renewal deadline passed",
     "The deadline to renew VPN client certificates has passed. All certificates were "
     "reissued automatically; re-download your profile if you cannot connect.",
     "warning", "expired", [], [], 50, -8),
    ("Database migration scheduled this weekend",
     "A critical PostgreSQL schema migration will run this weekend. Expect up to 15 "
     "minutes of read-only mode on the primary cluster; batch jobs are paused.",
     "critical", "active", ["Backend", "Data Engineering", "SRE"], [], 1, 3),
    ("Post-mortem: recent outage — S3 connectivity",
     "The root cause of the recent outage was an expired IAM role trust policy for the "
     "file-service. Remediation includes automated policy expiry alerts.",
     "critical", "active", [], [], 8, 30),
    ("Resolved: elevated error rates on auth-service",
     "The elevated 5xx error rates on auth-service have been resolved. A misconfigured "
     "rate-limiter was throttling legitimate traffic; the config has been corrected.",
     "critical", "expired", [], [], 35, -3),
]

INCIDENT_TEMPLATES = [
    ("API Gateway 502 errors spike",
     "Upstream services returning 502 Bad Gateway intermittently. Load balancer health "
     "checks passing but individual requests timing out after 30s.", "api-gateway"),
    ("Redis connection pool exhaustion",
     "Redis connection pool hit max capacity of 256 connections. Clients blocking on "
     "connection acquisition with 5s timeout.", "auth-service"),
    ("S3 upload failures in us-east-1",
     "PutObject calls returning 503 SlowDown errors. AWS reporting elevated error rates "
     "in us-east-1. Retry with exponential backoff mitigating but not eliminating.", "file-service"),
    ("Document service OOM kills",
     "OOMKilled events on document-service pods processing large DOCX conversions. "
     "Memory spiking to the 4Gi limit during concurrent PDF renders.", "document-service"),
    ("Search index corruption after reindex",
     "Full reindex job corrupted the primary search index shard. Queries returning "
     "stale or missing results for recently updated documents.", "search-service"),
    ("Auth service JWT validation failures",
     "JWT signature verification failing for tokens issued before the last key rotation. "
     "Clients caching the old public key. ~8% of authenticated requests affected.", "auth-service"),
    ("Database connection leak in file-service",
     "PostgreSQL connection count growing linearly over 72h due to a misconfigured "
     "maxLifetime. Database approaching the max_connections limit.", "file-service"),
    ("CI/CD pipeline stuck — GitHub webhook backlog",
     "GitHub webhook delivery queue backed up with thousands of pending events. "
     "Pipeline triggers delayed by 25+ minutes.", "admin-service"),
    ("Grafana dashboard 503 errors",
     "Grafana returning 503 on all dashboard loads. Underlying Prometheus data source "
     "timing out on long range queries.", "analytics-service"),
    ("DynamoDB throttling on metadata writes",
     "WriteCapacityUnits exceeded on the file-metadata table during bulk import. "
     "Switching to on-demand capacity mode resolved throttling.", "file-service"),
    ("Certificate expiry — collab-service TLS",
     "TLS certificate for the collab-service internal endpoint expired, causing mutual "
     "TLS handshake failures with api-gateway.", "collab-service"),
    ("Memory leak in notification-service",
     "Heap usage growing 50MB/hour without recovery. Profiling identified an unbounded "
     "cache of rendered email templates.", "notification-service"),
    ("Slow queries on audit_logs table",
     "SELECT queries exceeding 30s for time-range filters. Missing index on created_at. "
     "Adding a BRIN index reduced p99 from 32s to 120ms.", "audit-service"),
    ("Cross-site scripting vulnerability in admin dashboard",
     "Reflected XSS found in the admin search query parameter. User input rendered "
     "without sanitization in error messages.", "admin-service"),
    ("Data loss in analytics pipeline",
     "ETL job silently dropping events with null user_id. ~4% of analytics events lost "
     "over a two-week window.", "analytics-service"),
    ("Notification delivery delays exceeding SLA",
     "Email and push notifications delayed by 45+ minutes during peak hours. SQS queue "
     "depth growing due to insufficient consumer concurrency.", "notification-service"),
    ("Collab-service WebSocket disconnections",
     "Frequent WebSocket disconnects during collaborative editing. ALB idle timeout "
     "dropping inactive but open sessions.", "collab-service"),
    ("Report generation timeout for large datasets",
     "Report-service timing out generating exports with >100k rows. Single-threaded CSV "
     "serialization consuming 100% CPU.", "report-service"),
    ("Admin dashboard RBAC bypass",
     "Non-admin users able to access restricted endpoints via direct URL manipulation. "
     "Server-side authorization check missing on three routes.", "admin-service"),
    ("Search service latency spike during peak traffic",
     "p99 search latency increased from 200ms to 4.5s. OpenSearch cluster running hot "
     "with JVM heap pressure above 85%.", "search-service"),
    ("File versioning race condition",
     "Concurrent uploads to the same file creating orphaned versions. Optimistic lock "
     "using a stale version number in 0.3% of cases.", "file-service"),
    ("API gateway request routing misconfiguration",
     "Traffic to /api/v2/documents routed to the legacy v1 handler after a deploy. "
     "Ingress config overwritten by a Helm chart upgrade.", "api-gateway"),
    ("Auth token refresh loop",
     "Clients entering an infinite refresh loop when access and refresh tokens expire "
     "simultaneously. Race condition in the refresh middleware.", "auth-service"),
    ("Audit service write amplification",
     "Audit event inserts causing 10x write amplification due to over-indexing. INSERT "
     "p99 at 800ms blocking upstream completion.", "audit-service"),
    ("Document conversion service crash loop",
     "soffice process crashing on malformed .pptx files, causing CrashLoopBackOff. "
     "Added input validation and a conversion timeout.", "document-service"),
    ("Analytics event schema drift",
     "Frontend SDK sending events with renamed fields after a release. Pipeline "
     "rejecting 22% of incoming events as schema violations.", "analytics-service"),
    ("API gateway rate limiter false positives",
     "Legitimate clients rate-limited due to a shared IP behind a corporate proxy. "
     "Switched the rate-limit key to the authenticated user ID.", "api-gateway"),
    ("Notification template rendering failure",
     "Template engine throwing on an undefined variable in the welcome email. New "
     "registrations not receiving confirmation emails for 6h.", "notification-service"),
    ("File service presigned URL expiry too short",
     "Users receiving 403 when downloading large files shared via link. Presigned URL "
     "TTL too short for large downloads; increased to 1h.", "file-service"),
    ("Collab-service CRDT merge conflict",
     "Document state diverging between two concurrent editors, traced to clock skew in "
     "the awareness protocol.", "collab-service"),
    ("Admin service background job deadlock",
     "Workers deadlocked on competing row locks during nightly cleanup. Job queue "
     "backed up to 12k pending jobs by morning.", "admin-service"),
    ("Search indexing lag exceeding 30 minutes",
     "Document updates not appearing in search for 30+ minutes. Indexing consumer "
     "falling behind on large payload deserialization.", "search-service"),
    ("Report service PDF rendering blank pages",
     "PDF exports containing blank pages for documents with embedded SVG charts. "
     "Headless renderer failing silently on foreignObject elements.", "report-service"),
    ("Auth service LDAP sync failure",
     "LDAP directory sync failing with connection timeout to corporate AD. New user "
     "provisioning blocked until a manual sync.", "auth-service"),
    ("API gateway memory leak under load",
     "Go runtime heap growing unboundedly under sustained load. Goroutine leak in the "
     "middleware chain not cancelling context on client disconnect.", "api-gateway"),
    ("Analytics service Kafka consumer lag",
     "Consumer group falling behind by 2M messages during reprocessing. Partition "
     "rebalance storm from an aggressive session timeout.", "analytics-service"),
    ("File service thumbnail generation backlog",
     "Thumbnail queue depth at 45k with a 6h estimated drain time. Image processing "
     "pods CPU-throttled at their limit.", "file-service"),
    ("Document service concurrent edit limit reached",
     "Maximum concurrent editors per document hit on a planning doc. Users receiving "
     "429 when joining the editing session.", "document-service"),
    ("Notification service SMS gateway errors",
     "SMS gateway returning unverified-destination errors for international numbers. "
     "Registered additional sender IDs for EU and APAC.", "notification-service"),
    ("Audit log export CSV injection",
     "Audit log export including unsanitized user input in CSV cells, enabling formula "
     "injection. Added cell value escaping.", "audit-service"),
    ("Admin dashboard SSO integration failure",
     "SAML assertion validation failing after IdP certificate rotation. Admins unable "
     "to log in until the new fingerprint was added.", "admin-service"),
    ("Search service query injection vulnerability",
     "OpenSearch query DSL injection via unsanitized search terms. Input sanitization "
     "and parameterized queries deployed as an emergency fix.", "search-service"),
    ("API gateway TLS 1.0 deprecation breakage",
     "Legacy clients using TLS 1.0 failing to connect after security hardening. Added a "
     "TLS 1.2 minimum with a grace period for migration.", "api-gateway"),
    ("Collab-service presence tracking stale users",
     "Presence indicators showing users online hours after disconnecting. Redis TTL on "
     "presence keys not refreshed on WebSocket close.", "collab-service"),
    ("Report service memory spike on pivot tables",
     "Pivot aggregation loading the entire dataset into memory. Pod OOMKilled generating "
     "a large report; refactored to streaming aggregation.", "report-service"),
    ("File service virus scan queue backup",
     "Scan queue growing unboundedly due to a hung scanner process. Added a scan timeout "
     "and automatic process recycling.", "file-service"),
    ("Auth service brute force detection gaps",
     "Login rate limiting only counting successful attempts. Updated the limiter to "
     "count all attempts regardless of outcome.", "auth-service"),
    ("Analytics dashboard data inconsistency",
     "Dashboard totals differing by time granularity. Pre-aggregated rollup tables "
     "diverging due to a timezone conversion bug.", "analytics-service"),
    ("Notification service webhook retry storm",
     "Failed webhook deliveries retrying every 5s without backoff. Implemented "
     "exponential backoff with a maximum retry count.", "notification-service"),
    ("API gateway health check false healthy",
     "Health endpoint returning 200 while downstream services are unreachable. "
     "Implemented a deep health check with circuit breaker status.", "api-gateway"),
]

SYSTEM_CONFIGS = [
    ("max_upload_size_bytes", "10737418240", "integer", "Maximum file upload size in bytes (10 GB)", False),
    ("session_timeout_minutes", "30", "integer", "User session idle timeout", False),
    ("max_concurrent_uploads", "10", "integer", "Maximum simultaneous file uploads per user", False),
    ("default_storage_tier", "free", "string", "Default storage tier for new organizations", False),
    ("maintenance_mode", "false", "boolean", "Global maintenance mode toggle", False),
    ("api_rate_limit_per_minute", "1000", "integer", "API rate limit per authenticated user per minute", False),
    ("search_index_refresh_interval_seconds", "30", "integer", "Interval between search index refreshes", False),
    ("max_file_version_count", "50", "integer", "Maximum number of versions retained per file", False),
    ("audit_log_retention_days", "365", "integer", "Number of days to retain audit log entries", False),
    ("backup_schedule_cron", "0 2 * * *", "string", "Daily backup schedule in cron syntax (02:00 UTC)", False),
    ("smtp_host", "smtp.otterworks.io", "string", "SMTP relay hostname for outbound email", False),
    ("redis_max_connections", "100", "integer", "Maximum Redis connection pool size", False),
    ("cors_allowed_origins", "https://app.otterworks.io,https://admin.otterworks.io", "string",
     "Comma-separated list of allowed CORS origins", False),
    ("feature_flag_cache_ttl_seconds", "60", "integer", "TTL for feature flag evaluation cache", False),
    ("max_team_members", "500", "integer", "Maximum members per team", False),
    ("webhook_retry_max_attempts", "5", "integer", "Maximum retry attempts for failed webhook deliveries", False),
    ("webhook_retry_backoff_seconds", "30", "integer", "Base backoff interval between webhook retries", False),
    ("oauth_token_expiry_seconds", "3600", "integer", "OAuth2 access token lifetime", False),
    ("encryption_algorithm", "AES-256-GCM", "string", "Default encryption algorithm for data at rest", False),
    ("database_pool_size", "20", "integer", "PostgreSQL connection pool size per service instance", False),
    ("log_level", "info", "string", "Global application log level", False),
    ("sentry_dsn", "https://***@sentry.otterworks.io/1", "string", "Sentry error tracking DSN", True),
    ("slack_webhook_url", "https://hooks.slack.com/services/***", "string",
     "Slack integration webhook URL for alerts", True),
    ("aws_region", "us-east-1", "string", "Primary AWS region for infrastructure", False),
    ("cdn_base_url", "https://cdn.otterworks.io", "string", "CDN base URL for static asset delivery", False),
    ("max_document_size_bytes", "104857600", "integer", "Maximum document size in bytes (100 MB)", False),
    ("password_min_length", "12", "integer", "Minimum password length for user accounts", False),
    ("mfa_enforcement", "optional", "string", "MFA enforcement policy: disabled, optional, required", False),
    ("file_scan_enabled", "true", "boolean", "Enable virus scanning for uploaded files", False),
    ("max_api_key_count", "10", "integer", "Maximum API keys per user", False),
    ("jwt_signing_algorithm", "RS256", "string", "JWT signing algorithm", False),
    ("datadog_api_key", "dd-***-otterworks", "string", "Datadog API key for metrics export", True),
    ("pagerduty_integration_key", "pd-***-otterworks", "string", "PagerDuty integration key for incident routing", True),
    ("s3_bucket_primary", "otterworks-files-prod", "string", "Primary S3 bucket for file storage", False),
    ("max_search_results", "200", "integer", "Maximum results returned per search query", False),
    ("websocket_max_connections_per_doc", "50", "integer", "Maximum concurrent WebSocket connections per document", False),
    ("email_from_address", "noreply@otterworks.io", "string", "Default sender address for system emails", False),
    ("idle_session_cleanup_minutes", "1440", "integer", "Idle session cleanup interval in minutes (24h)", False),
    ("default_language", "en", "string", "Default UI language for new users", False),
    ("signup_enabled", "true", "boolean", "Whether self-service signup is enabled", False),
]

# ── DB helpers ────────────────────────────────────────────────────────────────

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "otterworks"),
    "user": os.getenv("DB_USER", "otterworks"),
    "password": os.getenv("DB_PASSWORD", "otterworks_dev"),
}


def bulk_insert(cur, table, columns, rows, on_conflict="DO NOTHING", template=None):
    if not rows:
        return 0
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES %s ON CONFLICT {on_conflict}"
    execute_values(cur, sql, rows, template=template)
    return len(rows)


# ── Generators ────────────────────────────────────────────────────────────────

def gen_users(rng, ref_now, pw_hash):
    """Return (rows, meta) where meta[i] = {id, created_at}."""
    columns = [
        "id", "email", "password_hash", "display_name", "avatar_url",
        "email_verified", "mfa_enabled", "mfa_secret",
        "created_at", "updated_at", "last_login_at",
    ]
    rows, meta = [], []
    used_emails: set[str] = set()

    for i in range(NUM_USERS):
        uid = stable_id("user", i)
        first = rng.choice(FIRST_NAMES)
        last = rng.choice(LAST_NAMES)
        base = f"{first.lower()}.{last.lower()}"
        email = f"{base}@otterworks.io"
        suffix = 1
        while email in used_emails:
            suffix += 1
            email = f"{base}{suffix}@otterworks.io"
        used_emails.add(email)

        created_at = ref_now - timedelta(
            days=rng.uniform(1, HISTORY_DAYS), seconds=rng.uniform(0, 86400)
        )
        updated_at = min(created_at + timedelta(days=rng.uniform(0, 45)), ref_now)
        last_login_at = None
        if rng.random() < 0.78:
            last_login_at = ref_now - timedelta(days=rng.uniform(0, 45))

        mfa_enabled = rng.random() < 0.18
        mfa_secret = (
            "".join(rng.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567", k=32))
            if mfa_enabled else None
        )

        rows.append((
            uid, email, pw_hash, f"{first} {last}",
            f"https://avatars.otterworks.io/{uid}.png",
            rng.random() < 0.82, mfa_enabled, mfa_secret,
            created_at, updated_at, last_login_at,
        ))
        meta.append({"id": uid, "created_at": created_at})

    return columns, rows, meta


def gen_user_settings(rng, user_meta):
    columns = [
        "user_id", "notification_email", "notification_in_app",
        "notification_desktop", "theme", "language",
    ]
    themes = ["system"] * 50 + ["dark"] * 30 + ["light"] * 20
    languages = ["en"] * 70 + ["es"] * 10 + ["ja"] * 8 + ["de"] * 5 + ["fr"] * 4 + ["zh"] * 3
    rows = []
    for u in user_meta:
        rows.append((
            u["id"], rng.random() < 0.85, rng.random() < 0.90,
            rng.random() < 0.25, rng.choice(themes), rng.choice(languages),
        ))
    return columns, rows


def gen_user_roles(rng, user_meta):
    columns = ["user_id", "role"]
    extra_rates = {"EDITOR": 0.45, "ADMIN": 0.12, "OWNER": 0.03}
    rows = []
    n = len(user_meta)
    for idx, u in enumerate(user_meta):
        rows.append((u["id"], "USER"))
        seniority = 1.0 - 0.4 * (idx / max(n - 1, 1))
        # At most one extra role, keeping every user at 1-2 roles.
        for role, rate in extra_rates.items():
            if rng.random() < rate * seniority:
                rows.append((u["id"], role))
                break
    return columns, rows


def gen_refresh_tokens(rng, ref_now, user_meta):
    columns = ["id", "user_id", "token_id", "expires_at", "revoked", "created_at"]
    rows = []
    idx = 0
    for u in user_meta:
        # ~55% of users have active sessions; some on multiple devices.
        r = rng.random()
        if r < 0.45:
            count = 0
        elif r < 0.80:
            count = 1
        else:
            count = 2
        for _ in range(count):
            token_created = max(
                u["created_at"],
                ref_now - timedelta(days=rng.uniform(0, 90)),
            )
            lifetime = timedelta(days=rng.uniform(7, 30))
            roll = rng.random()
            if roll < 0.15:
                revoked = True
                expires_at = token_created + lifetime
            elif roll < 0.40:
                # expired but expires strictly after created
                revoked = False
                short = timedelta(hours=rng.uniform(1, 24))
                expires_at = token_created + short
                if expires_at > ref_now:
                    expires_at = token_created + timedelta(hours=1)
            else:
                revoked = False
                expires_at = max(token_created + lifetime, ref_now + timedelta(days=rng.uniform(1, 14)))
            rows.append((
                stable_id("refresh-token", idx), u["id"],
                f"rt_{rng.getrandbits(128):032x}", expires_at, revoked, token_created,
            ))
            idx += 1
    return columns, rows


def gen_admin_users(rng, ref_now):
    columns = [
        "id", "email", "display_name", "role", "status", "avatar_url",
        "metadata", "last_login_at", "suspended_at", "suspended_reason",
        "created_at", "updated_at",
    ]
    roles = ["viewer"] * 12 + ["editor"] * 7 + ["admin"] * 4 + ["super_admin"] * 2
    statuses = ["active"] * 21 + ["suspended"] * 3 + ["deactivated"] * 1
    rng.shuffle(roles)
    rng.shuffle(statuses)

    first_pool = list(FIRST_NAMES)
    last_pool = list(LAST_NAMES)
    rng.shuffle(first_pool)
    rng.shuffle(last_pool)

    rows, meta = [], []
    used_emails: set[str] = set()
    for i in range(NUM_ADMIN_USERS):
        uid = stable_id("admin-user", i)
        first = first_pool[i % len(first_pool)]
        last = last_pool[i % len(last_pool)]
        base = f"{first.lower()}.{last.lower()}.admin"
        email = f"{base}@otterworks.io"
        suffix = 1
        while email in used_emails:
            suffix += 1
            email = f"{base}{suffix}@otterworks.io"
        used_emails.add(email)

        role = roles[i]
        status = statuses[i]
        created_at = ref_now - timedelta(days=rng.uniform(30, HISTORY_DAYS))
        updated_at = created_at
        metadata = Json({
            "department": rng.choice(DEPARTMENTS),
            "team": rng.choice(TEAMS),
            "employee_id": f"EMP-{rng.randint(0, 9999):04d}",
        })

        if status == "active":
            last_login_at = ref_now - timedelta(hours=rng.uniform(1, 336))
            suspended_at, suspended_reason = None, None
        elif status == "suspended":
            last_login_at = ref_now - timedelta(days=rng.uniform(30, 180))
            suspended_at = ref_now - timedelta(days=rng.uniform(1, 29))
            suspended_reason = rng.choice(SUSPENDED_REASONS)
            updated_at = suspended_at
        else:  # deactivated
            last_login_at = None
            suspended_at, suspended_reason = None, None

        rows.append((
            uid, email, f"{first} {last}", role, status,
            f"https://avatars.otterworks.io/admin/{uid}.png", metadata,
            last_login_at, suspended_at, suspended_reason, created_at, updated_at,
        ))
        meta.append({"id": uid, "email": email, "created_at": created_at})
    return columns, rows, meta


def gen_storage_quotas(rng, ref_now, admin_meta):
    columns = ["id", "user_id", "quota_bytes", "used_bytes", "tier", "created_at", "updated_at"]
    rows = []
    for i, a in enumerate(admin_meta):
        tier = rng.choices(_TIER_NAMES, weights=_TIER_W, k=1)[0]
        quota_bytes = TIER_SPECS[tier]
        r = rng.random()
        if r < 0.10:
            pct = rng.uniform(0.0, 0.05)
        elif r < 0.80:
            pct = rng.uniform(0.20, 0.60)
        else:
            pct = rng.uniform(0.80, 0.95)
        used_bytes = int(pct * quota_bytes)
        created_at = a["created_at"]
        span = max(int((ref_now - created_at).total_seconds()), 1)
        updated_at = created_at + timedelta(seconds=rng.randint(0, span))
        rows.append((
            stable_id("storage-quota", i), a["id"], quota_bytes, used_bytes,
            tier, created_at, updated_at,
        ))
    return columns, rows


def _changes_for_action(rng, action):
    if action == "user.role_changed":
        old = rng.choice(["viewer", "editor", "admin", "super_admin"])
        new = rng.choice([r for r in ["viewer", "editor", "admin", "super_admin"] if r != old])
        return {"field": "role", "old": old, "new": new}
    if action == "user.suspended":
        return {"field": "status", "old": "active", "new": "suspended"}
    if action == "quota.upgraded":
        return {"field": "tier", "old": "basic", "new": "pro"}
    if action == "feature_flag.toggled":
        enabled = rng.choice([True, False])
        return {"field": "enabled", "old": not enabled, "new": enabled}
    if action.startswith("system."):
        return {"note": action.replace("system.", "").replace("_", " ")}
    return {"note": action.replace(".", " ")}


def gen_audit_logs(rng, ref_now, admin_meta):
    columns = [
        "id", "actor_id", "actor_email", "action", "resource_type",
        "resource_id", "changes_made", "ip_address", "user_agent",
        "created_at", "updated_at",
    ]
    resource_types = list(RESOURCE_ACTIONS.keys())
    weights = []
    for rt in resource_types:
        if rt in ("AdminUser", "FeatureFlag", "SystemConfig", "Document", "File"):
            weights.append(3)
        elif rt in ("Incident", "Announcement"):
            weights.append(2)
        else:
            weights.append(1)

    rows = []
    for i in range(NUM_AUDIT_LOGS):
        is_system = rng.random() < 0.08
        if is_system:
            actor_id, actor_email = None, None
            action, resource_type = rng.choice(SYSTEM_ACTIONS)
            user_agent, ip_addr = SYSTEM_UA, "127.0.0.1"
            earliest = ref_now - timedelta(days=HISTORY_DAYS)
        else:
            actor = rng.choice(admin_meta)
            actor_id, actor_email = actor["id"], actor["email"]
            resource_type = rng.choices(resource_types, weights=weights, k=1)[0]
            action = rng.choice(RESOURCE_ACTIONS[resource_type])
            user_agent = rng.choice(BROWSER_UAS)
            if rng.random() < 0.80:
                ip_addr = f"10.{rng.randint(0,255)}.{rng.randint(0,255)}.{rng.randint(1,254)}"
            else:
                ip_addr = f"{rng.randint(50,220)}.{rng.randint(0,255)}.{rng.randint(0,255)}.{rng.randint(1,254)}"
            earliest = actor["created_at"] + timedelta(minutes=1)

        # created_at uniformly between earliest and now, guaranteeing temporal order.
        span = max((ref_now - earliest).total_seconds(), 60)
        created_at = earliest + timedelta(seconds=rng.uniform(0, span))
        rows.append((
            stable_id("audit-log", i), actor_id, actor_email, action,
            resource_type, stable_id(f"res-{resource_type.lower()}", rng.randint(0, 4999)),
            Json(_changes_for_action(rng, action)), ip_addr, user_agent,
            created_at, created_at,
        ))
    return columns, rows, template_for_audit()


def template_for_audit():
    return "(%s, %s::uuid, %s, %s, %s, %s::uuid, %s::jsonb, %s, %s, %s, %s)"


def gen_feature_flags(rng, ref_now, admin_meta):
    columns = [
        "id", "name", "description", "enabled", "target_users",
        "target_groups", "rollout_percentage", "expires_at", "created_at", "updated_at",
    ]
    dept_lower = [d.lower().replace(" ", "_") for d in DEPARTMENTS]
    team_lower = [t.lower().replace(" ", "_").replace("/", "_") for t in TEAMS]
    admin_ids = [a["id"] for a in admin_meta]
    rows = []
    for i, (name, description) in enumerate(FEATURE_FLAGS[:NUM_FEATURE_FLAGS]):
        enabled = rng.random() < 0.60
        rollout = rng.choice([10, 20, 25, 30, 50, 75, 80, 90, 100]) if enabled else 0
        target_users = rng.sample(admin_ids, rng.randint(0, min(5, len(admin_ids))))
        target_groups = rng.sample(dept_lower + team_lower, rng.randint(0, 3))
        er = rng.random()
        if er < 0.70:
            expires_at = None
        elif er < 0.90:
            expires_at = ref_now + timedelta(days=rng.randint(7, 120))
        else:
            expires_at = ref_now - timedelta(days=rng.randint(1, 60))
        created_at = ref_now - timedelta(days=rng.randint(0, HISTORY_DAYS), hours=rng.randint(0, 23))
        updated_at = min(created_at + timedelta(days=rng.randint(0, 60)), ref_now)
        rows.append((
            stable_id("feature-flag", i), name, description, enabled,
            Json(target_users), Json(target_groups), rollout, expires_at,
            created_at, updated_at,
        ))
    template = "(%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s)"
    return columns, rows, template


def gen_announcements(rng, ref_now, admin_meta):
    columns = [
        "id", "title", "body", "severity", "status", "target_audience",
        "starts_at", "ends_at", "created_by", "created_at", "updated_at",
    ]
    admin_ids = [a["id"] for a in admin_meta]
    rows = []
    for i, (title, body, severity, status, depts, roles, start_days, end_offset) in enumerate(
        ANNOUNCEMENTS[:NUM_ANNOUNCEMENTS]
    ):
        audience = {}
        if depts:
            audience["departments"] = depts
        if roles:
            audience["roles"] = roles
        starts_at = ref_now - timedelta(days=start_days) if start_days is not None else None
        ends_at = ref_now + timedelta(days=end_offset) if (end_offset is not None and starts_at) else None
        if starts_at is not None:
            created_at = starts_at - timedelta(hours=rng.randint(1, 48))
        else:
            created_at = ref_now - timedelta(days=rng.randint(1, 21))
        updated_at = min(created_at + timedelta(hours=rng.randint(0, 24)), ref_now)
        rows.append((
            stable_id("announcement", i), title, body, severity, status,
            Json(audience), starts_at, ends_at, rng.choice(admin_ids),
            created_at, updated_at,
        ))
    template = "(%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)"
    return columns, rows, template


def gen_incidents(rng, ref_now, admin_meta):
    columns = [
        "id", "title", "description", "severity", "status", "affected_service",
        "devin_session_id", "devin_session_url", "devin_session_status",
        "reporter_id", "resolved_at", "created_at", "updated_at", "closed_at",
    ]
    severities = ["low"] * 30 + ["medium"] * 35 + ["high"] * 25 + ["critical"] * 10
    statuses = ["open"] * 15 + ["investigating"] * 20 + ["resolved"] * 40 + ["closed"] * 25
    devin_statuses = ["completed", "in_progress", "failed"]
    admin_ids = [a["id"] for a in admin_meta]
    rows = []
    for i, (title, description, service) in enumerate(INCIDENT_TEMPLATES[:NUM_INCIDENTS]):
        severity = rng.choice(severities)
        status = rng.choice(statuses)
        created_at = ref_now - timedelta(days=rng.uniform(1, HISTORY_DAYS))
        updated_at = created_at + timedelta(hours=rng.randint(1, 72))
        resolved_at = closed_at = None
        if status in ("resolved", "closed"):
            resolved_at = created_at + timedelta(hours=rng.randint(1, 48))
        if status == "closed":
            closed_at = (resolved_at or created_at) + timedelta(hours=rng.randint(1, 24))
        devin_session_id = devin_session_url = devin_session_status = None
        if rng.random() < 0.30:
            hex_part = stable_id("devin-session", i).replace("-", "")[:12]
            devin_session_id = f"session-{hex_part}"
            devin_session_url = f"https://app.devin.ai/sessions/{devin_session_id}"
            devin_session_status = rng.choice(devin_statuses)
        rows.append((
            stable_id("incident", i), title, description, severity, status, service,
            devin_session_id, devin_session_url, devin_session_status,
            rng.choice(admin_ids), resolved_at, created_at, updated_at, closed_at,
        ))
    return columns, rows


def gen_system_configs(rng, ref_now):
    columns = ["id", "key", "value", "value_type", "description", "is_secret", "created_at", "updated_at"]
    rows = []
    for i, (key, value, value_type, description, is_secret) in enumerate(
        SYSTEM_CONFIGS[:NUM_SYSTEM_CONFIGS]
    ):
        created_at = ref_now - timedelta(days=rng.randint(90, HISTORY_DAYS))
        updated_at = min(created_at + timedelta(hours=rng.randint(0, 1440)), ref_now)
        rows.append((
            stable_id("system-config", i), key, value, value_type, description,
            is_secret, created_at, updated_at,
        ))
    return columns, rows


# ── Orchestration ─────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="OtterWorks golden reference data generator")
    parser.add_argument("--ns", default="golden", help="Namespace (schema = otterworks_<ns>)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Random seed (deterministic)")
    args = parser.parse_args()

    if not re.fullmatch(r"[A-Za-z0-9_]+", args.ns):
        print("ERROR: --ns must contain only letters, digits, and underscores.", file=sys.stderr)
        return 1

    schema = f"otterworks_{args.ns}"
    rng = random.Random(args.seed)
    ref_now = now()

    print(f"\n{'=' * 62}")
    print("  OtterWorks GOLDEN Reference Data Generator")
    print(f"  Namespace: {args.ns}  |  Schema: {schema}  |  Seed: {args.seed}")
    print(f"{'=' * 62}\n")

    # search_path is set via a libpq connection option so the schema identifier
    # never reaches a raw SQL string. The namespace is validated above.
    try:
        conn = psycopg2.connect(options=f"-c search_path={schema}", **DB_CONFIG)
    except psycopg2.OperationalError as e:
        print(f"ERROR: Cannot connect to database: {e}", file=sys.stderr)
        print("Bring up Postgres first (make infra-up).", file=sys.stderr)
        return 1

    conn.autocommit = False
    cur = conn.cursor()
    try:
        pw_hash = bcrypt.hashpw(b"golden-seed-password", bcrypt.gensalt(rounds=4)).decode()

        def run(label, columns, rows, on_conflict="DO NOTHING", template=None, table=None):
            table = table or label
            n = bulk_insert(cur, table, columns, rows, on_conflict=on_conflict, template=template)
            print(f"  {label:<16} -> {n} rows")
            return n

        total = 0

        cols, rows, user_meta = gen_users(rng, ref_now, pw_hash)
        total += run("users", cols, rows, on_conflict="(email) DO NOTHING")

        cols, rows = gen_user_settings(rng, user_meta)
        total += run("user_settings", cols, rows, on_conflict="(user_id) DO NOTHING")

        cols, rows = gen_user_roles(rng, user_meta)
        total += run("user_roles", cols, rows, on_conflict="(user_id, role) DO NOTHING")

        cols, rows = gen_refresh_tokens(rng, ref_now, user_meta)
        total += run("refresh_tokens", cols, rows, on_conflict="(token_id) DO NOTHING")

        cols, rows, admin_meta = gen_admin_users(rng, ref_now)
        total += run("admin_users", cols, rows, on_conflict="(email) DO NOTHING",
                     template="(%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)")

        cols, rows = gen_storage_quotas(rng, ref_now, admin_meta)
        total += run("storage_quotas", cols, rows, on_conflict="(user_id) DO NOTHING")

        cols, rows, tmpl = gen_audit_logs(rng, ref_now, admin_meta)
        total += run("audit_logs", cols, rows, template=tmpl)

        cols, rows, tmpl = gen_feature_flags(rng, ref_now, admin_meta)
        total += run("feature_flags", cols, rows, on_conflict="(name) DO NOTHING", template=tmpl)

        cols, rows, tmpl = gen_announcements(rng, ref_now, admin_meta)
        total += run("announcements", cols, rows, template=tmpl)

        cols, rows = gen_incidents(rng, ref_now, admin_meta)
        total += run("incidents", cols, rows)

        cols, rows = gen_system_configs(rng, ref_now)
        total += run("system_configs", cols, rows, on_conflict="(key) DO NOTHING")

        conn.commit()
        print(f"\nGolden dataset generated: {total} total rows into {schema}.\n")
        return 0
    except Exception as e:
        conn.rollback()
        print(f"\nERROR — rolled back: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
