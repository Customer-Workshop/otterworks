#!/usr/bin/env python3
"""Guard-readable port of mongo-migration 0.3.2 skills/mongo-migration/connectivity_probe.py (family oracle).

Identical checks and output shape; the only difference is that the Oracle statement is a literal so the
org's statement guard can inspect it. Source: one privilege listing (read-only). Target: role scope check,
then insert and delete one document in <target-db>._connectivity_probe. Secrets are read by env-var name only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import sys
import urllib.parse
import uuid

from recon.adapters import parse_oracle_secret
from recon.config import ConfigError

WRITE_WORDS = {"INSERT", "UPDATE", "DELETE", "ALTER", "CREATE", "DROP", "TRUNCATE", "EXECUTE", "CONTROL",
               "ALL", "ALL PRIVILEGES", "SUPER", "GRANT OPTION", "DBA", "SYSDBA", "TAKE OWNERSHIP", "IMPERSONATE"}
MONGO_TARGET_ROLES = {"read", "readWrite"}
NO_FALLBACK = {"privilege_excess", "privilege_missing", "target_not_allowlisted", "secret_malformed"}


def redact(text: str, secrets=()) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "<redacted>").replace(urllib.parse.quote(secret, safe=""), "<redacted>")
    text = re.sub(r"(?i)(//[^/\s:@]+:)[^@\s]+(@)", r"//<redacted>\2", text)
    text = re.sub(r"(?i)(\b(?:password|pwd)\s*=\s*)[^\s,;]+", r"\1<redacted>", text)
    return text.splitlines()[0] if text else ""


class PrivilegeExcess(Exception):
    pass


def classify(exc: BaseException) -> str:
    if isinstance(exc, PrivilegeExcess):
        return "privilege_excess"
    if isinstance(exc, ModuleNotFoundError):
        return "driver_missing"
    text = f"{type(exc).__name__} {exc}".lower()
    if isinstance(exc, TimeoutError) or "timeout" in text or "timed out" in text:
        return "timeout"
    if "name or service not known" in text or "getaddrinfo" in text:
        return "dns"
    if "authentication" in text or "auth failed" in text or "login failed" in text or "access denied" in text:
        return "auth"
    return "connect_failed"


def probe_source(secretName: str, timeout: float):
    value = os.environ.get(secretName)
    if not value:
        return "secret_missing", f"{secretName} is not set", []
    try:
        user, password, dsn = parse_oracle_secret(value)
    except ConfigError as exc:
        return "secret_malformed", f"{secretName}: {exc}", []
    try:
        import oracledb
        conn = oracledb.connect(user=user, password=password, dsn=dsn, tcp_connect_timeout=timeout)
        try:
            cur = conn.cursor()
            cur.execute("SELECT privilege FROM session_privs")
            privs = sorted(p.upper() for (p,) in cur.fetchall())
        finally:
            conn.close()
        excess = [p for p in privs if p != "CREATE SESSION" and (p in WRITE_WORDS or p.split()[0] in WRITE_WORDS)]
        if excess:
            raise PrivilegeExcess("over-scoped principal: " + ", ".join(excess))
        return None, "", privs
    except Exception as exc:  # noqa: BLE001
        return classify(exc), redact(str(exc), (value, password)), []


def probe_target(secretName: str, targetDb: str, timeout: float, allowed: pathlib.Path):
    value = os.environ.get(secretName)
    if not value:
        return "secret_missing", f"{secretName} is not set", []
    if not value.startswith(("mongodb://", "mongodb+srv://")):
        return "secret_malformed", f"{secretName}: not a mongodb:// or mongodb+srv:// URI", []
    try:
        allowedDbs = json.loads(allowed.read_text()).get("databases", [])
    except (OSError, json.JSONDecodeError):
        allowedDbs = []
    if targetDb not in allowedDbs:
        return "target_not_allowlisted", f"{targetDb!r} is not in {allowed}", []
    try:
        from pymongo import MongoClient
        client = MongoClient(value, serverSelectionTimeoutMS=int(timeout * 1000))
        try:
            db = client[targetDb]
            roles = db.command("connectionStatus").get("authInfo", {}).get("authenticatedUserRoles", [])
            roleNames = [f"{r['role']}@{r['db']}" for r in roles]
            excess = [f"{r['role']}@{r['db']}" for r in roles if r["db"] != targetDb or r["role"] not in MONGO_TARGET_ROLES]
            if excess:
                raise PrivilegeExcess("over-scoped principal: " + ", ".join(excess))
            probeId = f"probe-{uuid.uuid4()}"
            coll = db["_connectivity_probe"]
            try:
                coll.insert_one({"_id": probeId})
            finally:
                coll.delete_one({"_id": probeId})
        finally:
            client.close()
        return None, "", roleNames
    except Exception as exc:  # noqa: BLE001
        return classify(exc), redact(str(exc), (value,)), []


def side(policy: str, online: str, offline: str, result) -> dict:
    reason, detail, evidence = result
    if reason is None:
        return {"access": online, "reason": "probe_ok", "blocked": False, "detail": "", "evidence": evidence}
    fallback = policy == "auto" and reason not in NO_FALLBACK
    return {"access": offline if fallback else online, "reason": reason, "blocked": not fallback,
            "detail": detail, "evidence": evidence}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", choices=("auto", "online"), default="auto")
    ap.add_argument("--source-dsn-secret", required=True)
    ap.add_argument("--target-uri-secret", required=True)
    ap.add_argument("--target-db", required=True)
    ap.add_argument("--timeout", type=float, default=10.0)
    ap.add_argument("--allowed-targets", type=pathlib.Path, default=pathlib.Path(".migration/allowed_targets.json"))
    ap.add_argument("--out", type=pathlib.Path, default=pathlib.Path(".migration/08_connectivity.json"))
    a = ap.parse_args()
    source = side(a.policy, "live", "ddl_only", probe_source(a.source_dsn_secret, a.timeout))
    target = side(a.policy, "migration_cluster", "local",
                  probe_target(a.target_uri_secret, a.target_db, a.timeout, a.allowed_targets))
    result = {"policy": a.policy, "family": "oracle", "source_access": source["access"],
              "target_access": target["access"], "source_secret": a.source_dsn_secret,
              "target_secret": a.target_uri_secret, "target_db": a.target_db,
              "source": source, "target": target, "blocked": source["blocked"] or target["blocked"],
              "probe_tool": ".migration/tools/connectivity_probe_oracle.py (port of mongo-migration 0.3.2 connectivity_probe.py)",
              "probed_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    a.out.write_text(json.dumps(result, indent=2) + "\n")
    for name in ("source", "target"):
        r = result[name]
        print(f"{name}: {r['access']} ({r['reason']}{': ' + r['detail'] if r['detail'] else ''}) evidence={r['evidence']}")
    return 1 if result["blocked"] else 0


if __name__ == "__main__":
    sys.exit(main())
