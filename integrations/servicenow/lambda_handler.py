"""
AWS Lambda handler for the ServiceNow → Devin webhook receiver.

Deployed behind API Gateway (REST). Receives ServiceNow Business Rule
webhooks and creates Devin AI sessions for automated bug remediation.

Environment variables (set via CloudFormation Parameters → Lambda env):
  DEVIN_API_KEY               - Devin v3 API bearer token
  DEVIN_ORG_ID                - Devin organization ID
  SERVICENOW_WEBHOOK_SECRET   - Shared secret for X-ServiceNow-Secret header
  SERVICENOW_INSTANCE_URL     - e.g. https://koniag...service-now.com
  SERVICENOW_USERNAME         - ServiceNow API user (for callbacks)
  SERVICENOW_PASSWORD         - ServiceNow API password (for callbacks)
"""

import json
import logging
import os
from datetime import datetime, timezone
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

log = logging.getLogger()
log.setLevel(logging.INFO)

DEVIN_API = "https://api.devin.ai"

PRIORITY_MAP = {"1": "critical", "2": "high", "3": "medium", "4": "low", "5": "low"}

SERVICE_ALIASES = {
    "file-service", "document-service", "auth-service", "collab-service",
    "api-gateway", "notification-service", "search-service",
    "analytics-service", "admin-service", "audit-service", "report-service",
}


def _json_response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def _verify_secret(headers):
    expected = os.environ.get("SERVICENOW_WEBHOOK_SECRET", "")
    if not expected:
        return True
    provided = (
        headers.get("X-ServiceNow-Secret", "")
        or headers.get("x-servicenow-secret", "")
        or headers.get("Authorization", "").removeprefix("Bearer ").strip()
        or headers.get("authorization", "").removeprefix("Bearer ").strip()
    )
    return provided == expected


def _resolve_service(cmdb_ci, short_description):
    normalized = cmdb_ci.lower().strip()
    if normalized in SERVICE_ALIASES:
        return normalized
    combined = short_description.lower()
    for svc in SERVICE_ALIASES:
        if svc in combined or svc.replace("-", " ") in combined:
            return svc
    return None


def _build_devin_prompt(snow, affected_service):
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


def _http_request(url, method, headers, body=None, timeout=15):
    data = json.dumps(body).encode() if body else None
    req = urllib_request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib_request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except HTTPError as e:
        return e.code, {"error": e.read().decode()}
    except URLError as e:
        log.error("HTTP request failed: %s", e.reason)
        return 0, {"error": str(e.reason)}


def _create_devin_session(prompt):
    api_key = os.environ.get("DEVIN_API_KEY", "")
    org_id = os.environ.get("DEVIN_ORG_ID", "")
    if not api_key or not org_id:
        log.warning("DEVIN_API_KEY or DEVIN_ORG_ID not set — skipping session creation")
        return None

    url = f"{DEVIN_API}/v3/organizations/{org_id}/sessions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    status, data = _http_request(url, "POST", headers, {"prompt": prompt}, timeout=30)
    if status not in (200, 201):
        log.error("Devin API returned %d: %s", status, data)
        return None

    return {"session_id": data.get("session_id"), "url": data.get("url")}


def _post_servicenow_work_note(sys_id, message):
    instance_url = os.environ.get("SERVICENOW_INSTANCE_URL", "")
    username = os.environ.get("SERVICENOW_USERNAME", "")
    password = os.environ.get("SERVICENOW_PASSWORD", "")
    if not all([instance_url, username, password]):
        log.info("ServiceNow callback credentials not configured — skipping")
        return

    import base64
    url = f"{instance_url.rstrip('/')}/api/now/table/incident/{sys_id}"
    auth = base64.b64encode(f"{username}:{password}".encode()).decode()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Basic {auth}",
    }

    status, data = _http_request(url, "PATCH", headers, {"work_notes": message})
    if status >= 300:
        log.error("ServiceNow callback failed: %d %s", status, data)
    else:
        log.info("Posted work note to ServiceNow %s", sys_id)


def _resolve_servicenow_incident(sys_id, pr_url, summary, session_url):
    instance_url = os.environ.get("SERVICENOW_INSTANCE_URL", "")
    username = os.environ.get("SERVICENOW_USERNAME", "")
    password = os.environ.get("SERVICENOW_PASSWORD", "")
    if not all([instance_url, username, password]):
        log.info("ServiceNow callback credentials not configured — skipping resolve")
        return

    import base64
    url = f"{instance_url.rstrip('/')}/api/now/table/incident/{sys_id}"
    auth = base64.b64encode(f"{username}:{password}".encode()).decode()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Basic {auth}",
    }

    work_note = f"Devin AI Remediation Complete\nPR: {pr_url}\nSummary: {summary}"
    if session_url:
        work_note += f"\nSession: {session_url}"

    body = {
        "work_notes": work_note,
        "state": "6",
        "close_code": "Solved (Permanently)",
        "close_notes": f"Auto-resolved by Devin AI. PR: {pr_url}",
    }

    status, data = _http_request(url, "PATCH", headers, body)
    if status >= 300:
        log.error("ServiceNow resolve callback failed: %d %s", status, data)


def handler(event, context):
    """Main Lambda entry point for API Gateway proxy integration."""
    path = event.get("path", "") or event.get("rawPath", "")
    method = event.get("httpMethod", "") or event.get("requestContext", {}).get("http", {}).get("method", "")
    headers = event.get("headers") or {}
    body_str = event.get("body", "") or ""

    if event.get("isBase64Encoded") and body_str:
        import base64
        body_str = base64.b64decode(body_str).decode()

    # Health check
    if path.endswith("/health") and method == "GET":
        return _json_response(200, {
            "status": "ok",
            "service": "servicenow-webhook-lambda",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    # Ingest endpoint
    if path.endswith("/servicenow/ingest") and method == "POST":
        if not _verify_secret(headers):
            return _json_response(401, {"error": "Unauthorized"})

        try:
            payload = json.loads(body_str) if body_str else {}
        except json.JSONDecodeError:
            return _json_response(400, {"error": "Invalid JSON"})

        snow = payload.get("incident", {})
        sys_id = snow.get("sys_id", "")
        number = snow.get("number", "")

        if not sys_id:
            return _json_response(400, {"error": "Missing sys_id"})

        affected_service = _resolve_service(
            snow.get("cmdb_ci", ""), snow.get("short_description", "")
        )
        prompt = _build_devin_prompt(snow, affected_service)

        log.info("Received ServiceNow incident %s (sys_id=%s)", number, sys_id)

        session = _create_devin_session(prompt)

        if session:
            log.info("Devin session created for %s: %s", number, session.get("url", "N/A"))
            _post_servicenow_work_note(
                sys_id,
                f"Devin AI remediation session started.\nSession: {session.get('url', 'N/A')}",
            )

        return _json_response(201, {
            "received": True,
            "servicenow_number": number,
            "devin_session": session is not None,
            "devin_session_url": session.get("url") if session else None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    # Resolve endpoint
    if path.endswith("/servicenow/resolve") and method == "POST":
        if not _verify_secret(headers):
            return _json_response(401, {"error": "Unauthorized"})

        try:
            payload = json.loads(body_str) if body_str else {}
        except json.JSONDecodeError:
            return _json_response(400, {"error": "Invalid JSON"})

        sys_id = payload.get("sys_id", "")
        if not sys_id:
            return _json_response(400, {"error": "Missing sys_id"})

        _resolve_servicenow_incident(
            sys_id,
            pr_url=payload.get("pr_url", ""),
            summary=payload.get("summary", "Resolved via Devin AI automated remediation"),
            session_url=payload.get("session_url", ""),
        )

        return _json_response(200, {"resolved": True, "sys_id": sys_id})

    return _json_response(404, {"error": "Not found", "path": path})
