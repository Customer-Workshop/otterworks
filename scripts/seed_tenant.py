#!/usr/bin/env python3
"""Seed a deployed OtterWorks tenant with a deterministic, golden-style dataset.

Unlike ``scripts/seed.py`` (10 users into the admin-service tables of a local
dev DB), this seeds the *per-service* stores that a live tenant's client web app
actually reads, so a freshly deployed tenant looks like a busy product:

  * auth-service   -> Postgres  public.users / user_roles / user_settings
  * admin-service  -> Postgres  admin_users / storage_quotas / feature_flags /
                                 announcements / audit_logs / incidents /
                                 system_configs
  * document-service -> Postgres  documents / document_versions
  * file-service   -> DynamoDB file-metadata table + S3 objects (files/<owner>/<id>)

Everything is deterministic (seeded by the tenant id) and idempotent (stable
UUIDs + ON CONFLICT / put overwrites), so re-running on the same tenant is safe.

Config is read from the environment (the deploy-tenant.sh seed Job sets these):

  PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD   (tenant Postgres DB)
  AWS_REGION S3_BUCKET DYNAMODB_TABLE          (file-service object stores)
  SEED_NS                tenant id, namespaces UUIDs + the demo email domain
  SEED_USERS             number of demo users to create (default 12)
  SEED_DEMO_PASSWORD     shared login password for every seeded user
  SEED_SKIP_FILES        set to "1" to skip the DynamoDB/S3 file seeding

Business rules enforced (see .agents/skills/synthetic-testdata-generation):
  used_bytes <= quota_bytes; audit_logs.created_at >= actor created_at;
  unique emails; valid enum values per table.

NOTE: admin-service crash-loops on the golden app (a deliberate planted bug),
so its Rails migrations never run in a tenant -> its tables are created here with
CREATE TABLE IF NOT EXISTS. This does not touch or "fix" the planted bug.
"""
from __future__ import annotations

import hashlib
import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import psycopg2
from psycopg2.extras import execute_batch

# ── Config ──────────────────────────────────────────────────────────────────
NS = os.environ.get("SEED_NS", "demo").strip().lower() or "demo"
N_USERS = int(os.environ.get("SEED_USERS", "12"))
DEMO_PASSWORD = os.environ.get("SEED_DEMO_PASSWORD", "Passw0rd!23")
SKIP_FILES = os.environ.get("SEED_SKIP_FILES", "") in ("1", "true", "yes")
EMAIL_DOMAIN = f"{NS}.otterworks.dev"

# Deterministic UUID namespace derived from the tenant id, so two tenants never
# collide and re-runs are stable.
UUID_NS = uuid.uuid5(uuid.NAMESPACE_URL, f"otterworks-tenant:{NS}")
RNG = random.Random(int(hashlib.sha256(NS.encode()).hexdigest(), 16) % (2**32))

DDL_STATEMENTS = """
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    avatar_url VARCHAR(500),
    email_verified BOOLEAN NOT NULL DEFAULT false,
    mfa_enabled BOOLEAN NOT NULL DEFAULT false,
    mfa_secret VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMP WITH TIME ZONE
);
CREATE TABLE IF NOT EXISTS user_roles (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL,
    PRIMARY KEY (user_id, role)
);
CREATE TABLE IF NOT EXISTS user_settings (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    notification_email BOOLEAN NOT NULL DEFAULT true,
    notification_in_app BOOLEAN NOT NULL DEFAULT true,
    notification_desktop BOOLEAN NOT NULL DEFAULT false,
    theme VARCHAR(10) NOT NULL DEFAULT 'system',
    language VARCHAR(10) NOT NULL DEFAULT 'en'
);
CREATE TABLE IF NOT EXISTS admin_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL UNIQUE,
    display_name VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'viewer',
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    avatar_url VARCHAR(500),
    metadata JSONB DEFAULT '{}',
    last_login_at TIMESTAMP WITH TIME ZONE,
    suspended_at TIMESTAMP WITH TIME ZONE,
    suspended_reason VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS storage_quotas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE REFERENCES admin_users(id) ON DELETE CASCADE,
    quota_bytes BIGINT NOT NULL DEFAULT 5368709120,
    used_bytes BIGINT NOT NULL DEFAULT 0,
    tier VARCHAR(50) NOT NULL DEFAULT 'free',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id UUID,
    actor_email VARCHAR(255),
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100) NOT NULL,
    resource_id UUID,
    changes_made JSONB DEFAULT '{}',
    ip_address VARCHAR(45),
    user_agent VARCHAR(500),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS feature_flags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL UNIQUE,
    description VARCHAR(255),
    enabled BOOLEAN NOT NULL DEFAULT false,
    target_users JSONB DEFAULT '[]',
    target_groups JSONB DEFAULT '[]',
    rollout_percentage INTEGER NOT NULL DEFAULT 0,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS announcements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    severity VARCHAR(50) NOT NULL DEFAULT 'info',
    status VARCHAR(50) NOT NULL DEFAULT 'draft',
    target_audience JSONB DEFAULT '{}',
    starts_at TIMESTAMP WITH TIME ZONE,
    ends_at TIMESTAMP WITH TIME ZONE,
    created_by UUID,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS incidents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    severity VARCHAR(50) NOT NULL DEFAULT 'medium',
    status VARCHAR(50) NOT NULL DEFAULT 'open',
    affected_service VARCHAR(100),
    devin_session_id VARCHAR(255),
    devin_session_url VARCHAR(500),
    devin_session_status VARCHAR(50),
    reporter_id UUID,
    resolved_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    closed_at TIMESTAMP WITH TIME ZONE
);
CREATE TABLE IF NOT EXISTS system_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key VARCHAR(255) NOT NULL UNIQUE,
    value TEXT NOT NULL,
    value_type VARCHAR(50) NOT NULL DEFAULT 'string',
    description VARCHAR(255),
    is_secret BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(500) NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    content_type VARCHAR(50) NOT NULL DEFAULT 'text/markdown',
    owner_id UUID NOT NULL,
    folder_id UUID,
    is_deleted BOOLEAN NOT NULL DEFAULT false,
    is_template BOOLEAN NOT NULL DEFAULT false,
    word_count INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_documents_owner_id ON documents(owner_id);
CREATE TABLE IF NOT EXISTS document_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    title VARCHAR(500) NOT NULL,
    content TEXT NOT NULL,
    created_by UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
"""

FIRST_NAMES = [
    "Alice", "Bob", "Carol", "David", "Emily", "Frank", "Grace", "Henry",
    "Irene", "James", "Karen", "Leo", "Mia", "Noah", "Olivia", "Peter",
    "Quinn", "Rachel", "Sam", "Tina", "Uma", "Victor", "Wendy", "Xavier",
]
LAST_NAMES = [
    "Johnson", "Martinez", "Chen", "Kim", "Davis", "Wilson", "Lee",
    "Thompson", "Garcia", "Park", "Nguyen", "Patel", "Brown", "Rossi",
    "Muller", "Silva", "Khan", "Lopez", "Adams", "Baker",
]
DEPARTMENTS = ["Engineering", "Marketing", "Design", "Sales", "Product",
               "Operations", "Finance", "Legal", "Data Science", "Support"]
# tier -> quota bytes (mirrors scripts/seed.py tiers)
TIERS = {
    "free": 5 * 1024**3,
    "basic": 50 * 1024**3,
    "pro": 200 * 1024**3,
    "enterprise": 1024 * 1024**3,
}
ADMIN_ROLES = ["viewer", "editor", "admin", "super_admin"]
DOC_TITLES = [
    "Q{q} Product Roadmap", "Onboarding Guide", "Design System Notes",
    "Incident Postmortem", "API Contract Draft", "Weekly Sync Notes",
    "Marketing Launch Plan", "Security Review Checklist", "Budget Proposal",
    "Architecture Decision Record",
]
FILE_TEMPLATES = [
    ("Quarterly-Report.pdf", "application/pdf"),
    ("team-photo.png", "image/png"),
    ("budget.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ("design-mockup.fig", "application/octet-stream"),
    ("meeting-notes.md", "text/markdown"),
    ("demo-video.mp4", "video/mp4"),
    ("logo.svg", "image/svg+xml"),
    ("contract.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
]


def duid(*parts: object) -> str:
    return str(uuid.uuid5(UUID_NS, ":".join(str(p) for p in parts)))


def now() -> datetime:
    return datetime.now(timezone.utc)


def build_users() -> list[dict]:
    users = []
    for i in range(N_USERS):
        fn = FIRST_NAMES[i % len(FIRST_NAMES)]
        ln = LAST_NAMES[(i * 3) % len(LAST_NAMES)]
        created = now() - timedelta(days=RNG.randint(5, 540))
        tier = RNG.choices(list(TIERS), weights=[3, 4, 5, 2])[0]
        quota = TIERS[tier]
        # Make ~1 in 4 users sit at/above 90% usage so the storage-quota
        # warning banner (OTD-6) has realistic data to trigger on.
        if i % 4 == 0:
            used = int(quota * RNG.uniform(0.90, 0.99))
        else:
            used = int(quota * RNG.uniform(0.05, 0.75))
        users.append({
            "id": duid("user", i),
            "email": f"{fn.lower()}.{ln.lower()}{i}@{EMAIL_DOMAIN}",
            "display_name": f"{fn} {ln}",
            "app_role": RNG.choices(["USER", "EDITOR", "ADMIN", "OWNER"],
                                    weights=[6, 4, 2, 1])[0],
            "admin_role": RNG.choices(ADMIN_ROLES, weights=[6, 4, 2, 1])[0],
            "status": RNG.choices(["active", "suspended", "deactivated"],
                                  weights=[9, 1, 1])[0],
            "department": DEPARTMENTS[i % len(DEPARTMENTS)],
            "tier": tier,
            "quota_bytes": quota,
            "used_bytes": min(used, quota),  # business rule: used <= quota
            "created_at": created,
            "last_login_at": now() - timedelta(hours=RNG.randint(1, 720)),
        })
    return users


def seed_postgres(conn, users: list[dict]) -> dict:
    counts: dict[str, int] = {}
    pw_hash = bcrypt.hashpw(DEMO_PASSWORD.encode(), bcrypt.gensalt(rounds=10)).decode()
    with conn.cursor() as cur:
        cur.execute(DDL_STATEMENTS)

        # auth: users / roles / settings
        execute_batch(cur, """
            INSERT INTO users (id, email, password_hash, display_name,
                               email_verified, created_at, updated_at, last_login_at)
            VALUES (%(id)s, %(email)s, %(pw)s, %(display_name)s, true,
                    %(created_at)s, %(created_at)s, %(last_login_at)s)
            ON CONFLICT (id) DO UPDATE SET
                password_hash = EXCLUDED.password_hash,
                display_name  = EXCLUDED.display_name,
                last_login_at = EXCLUDED.last_login_at
        """, [{**u, "pw": pw_hash} for u in users])
        counts["users"] = len(users)

        roles = [{"uid": u["id"], "role": u["app_role"]} for u in users]
        roles += [{"uid": u["id"], "role": "USER"} for u in users
                  if u["app_role"] != "USER"]
        execute_batch(cur, """
            INSERT INTO user_roles (user_id, role) VALUES (%(uid)s, %(role)s)
            ON CONFLICT (user_id, role) DO NOTHING
        """, roles)
        counts["user_roles"] = len(roles)

        execute_batch(cur, """
            INSERT INTO user_settings (user_id, theme, language)
            VALUES (%(uid)s, %(theme)s, 'en')
            ON CONFLICT (user_id) DO NOTHING
        """, [{"uid": u["id"], "theme": RNG.choice(["system", "light", "dark"])}
              for u in users])
        counts["user_settings"] = len(users)

        # Reset the migration-seeded admin so the documented login works.
        cur.execute("""
            UPDATE users SET password_hash = %s, email_verified = true
            WHERE email = 'admin@otterworks.dev'
        """, (bcrypt.hashpw(b"Admin123!", bcrypt.gensalt(rounds=10)).decode(),))

        # admin: admin_users mirror the app users (shared ids for traceability)
        execute_batch(cur, """
            INSERT INTO admin_users (id, email, display_name, role, status,
                                     last_login_at, created_at, updated_at)
            VALUES (%(id)s, %(email)s, %(display_name)s, %(admin_role)s,
                    %(status)s, %(last_login_at)s, %(created_at)s, %(created_at)s)
            ON CONFLICT (id) DO NOTHING
        """, users)
        counts["admin_users"] = len(users)

        execute_batch(cur, """
            INSERT INTO storage_quotas (id, user_id, quota_bytes, used_bytes,
                                        tier, created_at, updated_at)
            VALUES (%(qid)s, %(uid)s, %(quota)s, %(used)s, %(tier)s, %(ca)s, %(ca)s)
            ON CONFLICT (user_id) DO UPDATE SET
                quota_bytes = EXCLUDED.quota_bytes,
                used_bytes  = EXCLUDED.used_bytes,
                tier        = EXCLUDED.tier
        """, [{"qid": duid("quota", u["id"]), "uid": u["id"],
               "quota": u["quota_bytes"], "used": u["used_bytes"],
               "tier": u["tier"], "ca": u["created_at"]} for u in users])
        counts["storage_quotas"] = len(users)

        # feature flags
        flags = [
            ("beta_export_pipeline", "Async export pipeline for large reports", False, 0),
            ("ai_document_summary", "AI-powered document summary on upload", True, 25),
            ("advanced_search_filters", "Extended MeiliSearch facet filters", True, 80),
            ("realtime_collab_v2", "New CRDT-based realtime collaboration", False, 10),
            ("dark_mode_default", "Default new users to dark theme", True, 100),
        ]
        execute_batch(cur, """
            INSERT INTO feature_flags (id, name, description, enabled, rollout_percentage)
            VALUES (%(id)s, %(name)s, %(desc)s, %(en)s, %(pct)s)
            ON CONFLICT (name) DO NOTHING
        """, [{"id": duid("flag", n), "name": n, "desc": d, "en": e, "pct": p}
              for (n, d, e, p) in flags])
        counts["feature_flags"] = len(flags)

        # announcements
        anns = [
            ("Scheduled maintenance this weekend",
             "The platform will be unavailable 02:00-04:00 UTC Saturday for DB upgrades.",
             "warning", "active"),
            ("New AI document summary in beta",
             "AI-powered document summaries are rolling out to 25% of users.",
             "info", "active"),
            ("Storage quota review",
             "Several accounts are approaching their storage quota. Review the Storage page.",
             "warning", "draft"),
            ("Security patch applied",
             "A routine security patch was applied across all services.",
             "info", "expired"),
        ]
        execute_batch(cur, """
            INSERT INTO announcements (id, title, body, severity, status, starts_at)
            VALUES (%(id)s, %(t)s, %(b)s, %(sev)s, %(st)s, %(sa)s)
            ON CONFLICT (id) DO NOTHING
        """, [{"id": duid("ann", t), "t": t, "b": b, "sev": s, "st": st,
               "sa": now() - timedelta(days=RNG.randint(0, 20))}
              for (t, b, s, st) in anns])
        counts["announcements"] = len(anns)

        # audit logs (actor_id from admin_users; created_at >= actor.created_at)
        actions = ["user.login", "user.update", "file.upload", "file.delete",
                   "document.create", "quota.update", "flag.toggle", "role.change"]
        audit = []
        for k in range(min(200, N_USERS * 15)):
            u = users[k % len(users)]
            ca = u["created_at"] + timedelta(
                seconds=RNG.randint(60, max(120, int((now() - u["created_at"]).total_seconds()))))
            audit.append({
                "id": duid("audit", k), "aid": u["id"], "aemail": u["email"],
                "action": RNG.choice(actions), "rtype": RNG.choice(
                    ["user", "file", "document", "quota", "flag"]),
                "ip": f"10.{RNG.randint(0,255)}.{RNG.randint(0,255)}.{RNG.randint(1,254)}",
                "ca": ca,
            })
        execute_batch(cur, """
            INSERT INTO audit_logs (id, actor_id, actor_email, action, resource_type,
                                    ip_address, user_agent, created_at, updated_at)
            VALUES (%(id)s, %(aid)s, %(aemail)s, %(action)s, %(rtype)s, %(ip)s,
                    'Mozilla/5.0 (seed-tenant)', %(ca)s, %(ca)s)
            ON CONFLICT (id) DO NOTHING
        """, audit)
        counts["audit_logs"] = len(audit)

        # incidents
        incs = [
            ("Elevated 5xx on file-service", "Spike in upload errors after deploy.",
             "high", "resolved", "file-service"),
            ("Search latency degradation", "MeiliSearch p95 latency above SLO.",
             "medium", "investigating", "search-service"),
            ("Auth token refresh failures", "Intermittent refresh token rejections.",
             "critical", "open", "auth-service"),
        ]
        execute_batch(cur, """
            INSERT INTO incidents (id, title, description, severity, status,
                                   affected_service, created_at, updated_at)
            VALUES (%(id)s, %(t)s, %(d)s, %(sev)s, %(st)s, %(svc)s, %(ca)s, %(ca)s)
            ON CONFLICT (id) DO NOTHING
        """, [{"id": duid("inc", t), "t": t, "d": d, "sev": s, "st": st,
               "svc": svc, "ca": now() - timedelta(days=RNG.randint(1, 60))}
              for (t, d, s, st, svc) in incs])
        counts["incidents"] = len(incs)

        # system configs
        cfgs = [
            ("max_upload_mb", "500", "integer", "Maximum single upload size in MB"),
            ("default_quota_tier", "free", "string", "Tier assigned to new users"),
            ("maintenance_mode", "false", "boolean", "Global maintenance switch"),
            ("session_timeout_minutes", "60", "integer", "Idle session timeout"),
        ]
        execute_batch(cur, """
            INSERT INTO system_configs (id, key, value, value_type, description)
            VALUES (%(id)s, %(k)s, %(v)s, %(vt)s, %(d)s)
            ON CONFLICT (key) DO NOTHING
        """, [{"id": duid("cfg", k), "k": k, "v": v, "vt": vt, "d": d}
              for (k, v, vt, d) in cfgs])
        counts["system_configs"] = len(cfgs)

        # documents (+ one prior version each)
        docs, versions = [], []
        for u in users:
            for j in range(RNG.randint(2, 6)):
                did = duid("doc", u["id"], j)
                title = DOC_TITLES[(j + hash(u["id"]) % len(DOC_TITLES)) % len(DOC_TITLES)]
                title = title.format(q=RNG.randint(1, 4))
                body = (f"# {title}\n\nOwned by {u['display_name']} "
                        f"({u['department']}).\n\n" + "Lorem ipsum dolor sit amet. " * RNG.randint(20, 120))
                wc = len(body.split())
                ca = u["created_at"] + timedelta(days=RNG.randint(0, 30))
                docs.append({"id": did, "title": title, "content": body,
                             "owner": u["id"], "wc": wc, "ver": 2, "ca": ca})
                versions.append({"id": duid("docver", did), "doc": did,
                                 "title": title, "content": body[: len(body) // 2],
                                 "by": u["id"], "ca": ca})
        # NB: document-service's alembic-created table has no server-side
        # defaults (SQLAlchemy defaults are app-side), so set every NOT NULL
        # column explicitly rather than relying on DB defaults.
        execute_batch(cur, """
            INSERT INTO documents (id, title, content, content_type, owner_id,
                                   is_deleted, is_template, word_count, version,
                                   created_at, updated_at)
            VALUES (%(id)s, %(title)s, %(content)s, 'text/markdown', %(owner)s,
                    false, false, %(wc)s, %(ver)s, %(ca)s, %(ca)s)
            ON CONFLICT (id) DO NOTHING
        """, docs)
        counts["documents"] = len(docs)
        execute_batch(cur, """
            INSERT INTO document_versions (id, document_id, version_number, title,
                                           content, created_by, created_at)
            VALUES (%(id)s, %(doc)s, 1, %(title)s, %(content)s, %(by)s, %(ca)s)
            ON CONFLICT (id) DO NOTHING
        """, versions)
        counts["document_versions"] = len(versions)

    conn.commit()
    return counts


def seed_files(users: list[dict]) -> dict:
    """Seed file-service metadata (DynamoDB) + objects (S3), owner-partitioned."""
    import boto3

    region = os.environ["AWS_REGION"]
    table_name = os.environ["DYNAMODB_TABLE"]
    bucket = os.environ["S3_BUCKET"]
    ddb = boto3.resource("dynamodb", region_name=region)
    table = ddb.Table(table_name)
    s3 = boto3.client("s3", region_name=region)

    n_files = 0
    for u in users:
        for j in range(RNG.randint(2, 6)):
            fid = duid("file", u["id"], j)
            name, mime = FILE_TEMPLATES[(j + n_files) % len(FILE_TEMPLATES)]
            s3_key = f"files/{u['id']}/{fid}"
            body = (f"OtterWorks demo file '{name}' for {u['display_name']}\n"
                    f"tenant={NS} file_id={fid}\n").encode()
            size = max(len(body), RNG.randint(2_048, 25_000_000))
            created = (u["created_at"] + timedelta(days=RNG.randint(0, 40))).isoformat()
            s3.put_object(Bucket=bucket, Key=s3_key, Body=body, ContentType=mime)
            table.put_item(Item={
                "id": fid,
                "name": name,
                "mime_type": mime,
                "size_bytes": size,
                "s3_key": s3_key,
                "owner_id": u["id"],
                "version": 1,
                "is_trashed": False,
                "created_at": created,
                "updated_at": created,
            })
            n_files += 1
    return {"files (dynamodb+s3)": n_files}


def main() -> None:
    print(f"[seed-tenant] tenant='{NS}' users={N_USERS} domain={EMAIL_DOMAIN}")
    users = build_users()
    try:
        conn = psycopg2.connect(
            host=os.environ["PGHOST"], port=os.environ.get("PGPORT", "5432"),
            dbname=os.environ["PGDATABASE"], user=os.environ["PGUSER"],
            password=os.environ["PGPASSWORD"], sslmode="prefer", connect_timeout=15,
        )
    except Exception as e:  # noqa: BLE001
        print(f"[seed-tenant] ERROR: cannot connect to Postgres — {e}", file=sys.stderr)
        sys.exit(1)
    try:
        counts = seed_postgres(conn, users)
    finally:
        conn.close()

    if SKIP_FILES:
        print("[seed-tenant] SEED_SKIP_FILES set — skipping DynamoDB/S3 file seeding")
    else:
        try:
            counts.update(seed_files(users))
        except Exception as e:  # noqa: BLE001
            print(f"[seed-tenant] WARNING: file seeding skipped — {e}", file=sys.stderr)

    print("[seed-tenant] done. Rows written:")
    for k, v in counts.items():
        print(f"    {k:24} {v}")
    print("[seed-tenant] demo login: any seeded user OR admin@otterworks.dev / Admin123!")
    print(f"[seed-tenant] seeded-user password: {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
