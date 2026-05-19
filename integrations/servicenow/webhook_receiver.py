#!/usr/bin/env python3
"""
Standalone ServiceNow → Devin webhook receiver.

Receives inbound webhooks from a ServiceNow Business Rule and creates
a Devin AI session to auto-remediate the reported bug.

This script can run independently of the full admin-service Rails app,
making it easy to demo or deploy as a lightweight Lambda / Cloud Run function.

Environment variables:
  DEVIN_API_KEY               - Devin v3 API bearer token (required)
  DEVIN_ORG_ID                - Devin organization ID (required)
  SERVICENOW_WEBHOOK_SECRET   - Shared secret for X-ServiceNow-Secret header (optional)
  SERVICENOW_INSTANCE_URL     - e.g. https://dev12345.service-now.com (optional, for callbacks)
  SERVICENOW_USERNAME          - ServiceNow API user (optional, for callbacks)
  SERVICENOW_PASSWORD          - ServiceNow API password (optional, for callbacks)
  PORT                         - Listen port (default 8095)

Usage:
  pip install flask requests
  python webhook_receiver.py
"""

import logging
import os
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("servicenow-webhook")

DEVIN_API = "https://api.devin.ai"

PRIORITY_MAP = {"1": "critical", "2": "high", "3": "medium", "4": "low", "5": "low"}

SERVICE_ALIASES = {
    "file-service", "document-service", "auth-service", "collab-service",
    "api-gateway", "notification-service", "search-service",
    "analytics-service", "admin-service", "audit-service", "report-service",
}


def verify_secret():
    expected = os.environ.get("SERVICENOW_WEBHOOK_SECRET")
    if not expected:
        return True
    provided = (
        request.headers.get("X-ServiceNow-Secret")
        or request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    )
    return provided == expected


def resolve_service(cmdb_ci: str, short_description: str) -> str | None:
    normalized = cmdb_ci.lower().strip()
    if normalized in SERVICE_ALIASES:
        return normalized
    combined = short_description.lower()
    for svc in SERVICE_ALIASES:
        if svc in combined or svc.replace("-", " ") in combined:
            return svc
    return None


def build_devin_prompt(snow: dict, affected_service: str | None) -> str:
    return f"""You are investigating a bug reported via ServiceNow in the OtterWorks platform,
a collaborative file storage and document editing system built as a polyglot
microservices architecture.

## ServiceNow Ticket
- **Number**: {snow.get('number', 'N/A')}
- **Priority**: {snow.get('priority', 'N/A')}
- **Category**: {snow.get('category', 'N/A')}
- **Short Description**: {snow.get('short_description', 'N/A')}
- **Description**: {snow.get('description', 'N/A')}
- **CI / Affected Service**: {affected_service or snow.get('cmdb_ci', 'Unknown')}
- **Assignment Group**: {snow.get('assignment_group', 'N/A')}
- **Caller**: {snow.get('caller_id', 'N/A')}

## OtterWorks Architecture
The platform has 11 microservices:
- API Gateway (Go/Chi, port 8080) — routing, rate limiting, JWT validation
- Auth Service (Java/Spring Boot, port 8081) — authentication, RBAC
- File Service (Rust/Actix-Web, port 8082) — file upload/download, S3
- Document Service (Python/FastAPI, port 8083) — document CRUD, versioning
- Collaboration Service (Node.js/Socket.io, port 8084) — real-time editing
- Notification Service (Kotlin/Ktor, port 8086) — event-driven notifications
- Search Service (Python/Flask, port 8087) — MeiliSearch full-text search
- Analytics Service (Scala/Akka HTTP, port 8088) — usage analytics
- Admin Service (Ruby/Rails, port 8089) — admin operations
- Audit Service (C#/ASP.NET, port 8090) — audit trail
- Report Service (Java/Spring Boot, port 8091) — report generation

Services communicate via REST (through API Gateway) and async SNS/SQS events.

## Your Task
Investigate this bug, identify the root cause, and implement a fix.
Start by examining the affected service's code and logs.
After implementing a fix, open a PR with a clear description referencing
ServiceNow ticket {snow.get('number', 'N/A')}.
"""


def create_devin_session(prompt: str) -> dict | None:
    api_key = os.environ.get("DEVIN_API_KEY")
    org_id = os.environ.get("DEVIN_ORG_ID")
    if not api_key or not org_id:
        log.warning("DEVIN_API_KEY or DEVIN_ORG_ID not set — skipping session creation")
        return None

    url = f"{DEVIN_API}/v3/organizations/{org_id}/sessions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {"prompt": prompt}

    resp = requests.post(url, headers=headers, json=body, timeout=30)
    if resp.status_code not in (200, 201):
        log.error("Devin API returned %d: %s", resp.status_code, resp.text)
        return None

    data = resp.json()
    return {"session_id": data.get("session_id"), "url": data.get("url")}


def post_servicenow_work_note(sys_id: str, message: str):
    instance_url = os.environ.get("SERVICENOW_INSTANCE_URL")
    username = os.environ.get("SERVICENOW_USERNAME")
    password = os.environ.get("SERVICENOW_PASSWORD")
    if not all([instance_url, username, password]):
        log.info("ServiceNow callback credentials not configured — skipping work note")
        return

    url = f"{instance_url.rstrip('/')}/api/now/table/incident/{sys_id}"
    resp = requests.patch(
        url,
        json={"work_notes": message},
        auth=(username, password),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        timeout=15,
    )
    if resp.ok:
        log.info("Posted work note to ServiceNow %s", sys_id)
    else:
        log.error("ServiceNow callback failed: %d %s", resp.status_code, resp.text)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "servicenow-webhook-receiver"})


@app.route("/api/v1/admin/servicenow/ingest", methods=["POST"])
def ingest():
    if not verify_secret():
        return jsonify({"error": "Unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    snow = payload.get("incident", {})

    sys_id = snow.get("sys_id", "")
    number = snow.get("number", "")
    if not sys_id:
        return jsonify({"error": "Missing sys_id"}), 400

    affected_service = resolve_service(
        snow.get("cmdb_ci", ""), snow.get("short_description", "")
    )
    prompt = build_devin_prompt(snow, affected_service)

    log.info("Received ServiceNow incident %s (sys_id=%s)", number, sys_id)

    session = create_devin_session(prompt)

    if session:
        log.info(
            "Devin session created for %s: %s", number, session.get("url", "N/A")
        )
        post_servicenow_work_note(
            sys_id,
            f"Devin AI remediation session started.\nSession: {session.get('url', 'N/A')}",
        )

    return jsonify({
        "received": True,
        "servicenow_number": number,
        "devin_session": session is not None,
        "devin_session_url": session.get("url") if session else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }), 201


@app.route("/api/v1/admin/servicenow/resolve", methods=["POST"])
def resolve():
    if not verify_secret():
        return jsonify({"error": "Unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    sys_id = payload.get("sys_id", "")
    if not sys_id:
        return jsonify({"error": "Missing sys_id"}), 400

    pr_url = payload.get("pr_url", "")
    summary = payload.get("summary", "Resolved via Devin AI automated remediation")
    session_url = payload.get("session_url", "")

    work_note = f"Devin AI Remediation Complete\nPR: {pr_url}\nSummary: {summary}"
    if session_url:
        work_note += f"\nSession: {session_url}"

    instance_url = os.environ.get("SERVICENOW_INSTANCE_URL")
    username = os.environ.get("SERVICENOW_USERNAME")
    password = os.environ.get("SERVICENOW_PASSWORD")

    if all([instance_url, username, password]):
        url = f"{instance_url.rstrip('/')}/api/now/table/incident/{sys_id}"
        resp = requests.patch(
            url,
            json={
                "work_notes": work_note,
                "state": "6",
                "close_code": "Solved (Permanently)",
                "close_notes": f"Auto-resolved by Devin AI. PR: {pr_url}",
            },
            auth=(username, password),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=15,
        )
        if not resp.ok:
            log.error("ServiceNow resolve callback failed: %d %s", resp.status_code, resp.text)
            return jsonify({"error": "ServiceNow update failed"}), 502
    else:
        log.info("ServiceNow credentials not configured — skipping resolve callback")

    return jsonify({"resolved": True, "sys_id": sys_id})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8095"))
    log.info("Starting ServiceNow webhook receiver on port %d", port)
    app.run(host="0.0.0.0", port=port)
