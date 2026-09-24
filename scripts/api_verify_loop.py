#!/usr/bin/env python3
"""API verification loop for the OtterWorks Docker Compose stack.

Polls a configurable set of service endpoints, asserts on HTTP status and JSON
body, and emits a structured pass/fail per endpoint. When an endpoint keeps
failing it captures the affected service's recent container logs and starts a
Devin session (or fires an automation webhook) with the failing endpoint, the
expected-vs-actual values and the log excerpt. It then keeps polling, mirrors
the session's status and PR URL, and reports the endpoint green once the fixed
service has been rebuilt — closing the loop. A per-service attempt counter
mirrors MAX_FIX_ATTEMPTS in .github/workflows/sast-auto-remediate.yml.

This is the host-side counterpart of two admin-service classes: the HTTP
probing follows HealthChecker (app/services/health_checker.rb) and
ChaosProbeService::SERVICE_PROBES (multipart upload, malformed SQS message),
and the poll loop follows ChaosProbeService.start. It runs on the host so it
can call `docker compose logs`, which the admin-service container cannot.

Standard library only. Python 3.9+.

    python3 scripts/api_verify_loop.py --once           # one pass, exit 1 on any failure
    python3 scripts/api_verify_loop.py                  # loop every 5s, trigger Devin on failure
    python3 scripts/api_verify_loop.py --trigger admin  # go through admin-service alerts/ingest
    python3 scripts/api_verify_loop.py --trigger none --json  # dry run, JSON lines only

Environment: DEVIN_API_KEY, DEVIN_ORG_ID (trigger=devin); DEVIN_API_BASE
(default https://api.devin.ai); DEVIN_WEBHOOK_URL, DEVIN_WEBHOOK_SECRET
(trigger=webhook); ALERT_WEBHOOK_SECRET, ADMIN_SERVICE_URL (trigger=admin);
MAX_FIX_ATTEMPTS (default 2); COMPOSE_FILES (default
"docker-compose.infra.yml docker-compose.yml"); GITHUB_REPOSITORY (named in
the prompt, default Cognition-Partner-Workshops/otterworks).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO_ROOT / "scripts" / "api-verify-endpoints.json"
DEFAULT_COMPOSE_FILES = "docker-compose.infra.yml docker-compose.yml"
DEFAULT_REPOSITORY = "Cognition-Partner-Workshops/otterworks"
DEVIN_API_BASE = os.environ.get("DEVIN_API_BASE", "https://api.devin.ai").rstrip("/")
LOG_TAIL_LINES = 200
ERROR_MARKERS = (
    "error",
    "exception",
    "traceback",
    "panic",
    "fatal",
    "500",
    "keyerror",
    "nosuchbucket",
)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    endpoint: str
    service: str
    scenario: str | None
    ok: bool
    status: int | None
    latency_ms: int
    failures: list[str]
    body_excerpt: str

    def to_event(self) -> dict[str, Any]:
        return {
            "ts": now_iso(),
            "event": "check",
            "endpoint": self.endpoint,
            "service": self.service,
            "scenario": self.scenario,
            "result": "pass" if self.ok else "fail",
            "status": self.status,
            "latency_ms": self.latency_ms,
            "failures": self.failures,
        }


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def build_multipart(boundary: str) -> bytes:
    # Same shape as ChaosProbeService.build_multipart_request: one "file" field.
    return (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="probe.txt"\r\n'
        "Content-Type: text/plain\r\n\r\n"
        "api verify probe\r\n"
        f"--{boundary}--\r\n"
    ).encode()


def build_sqs_epoch_message() -> bytes:
    # Same payload as ChaosProbeService.build_sqs_request: integer epoch timestamp,
    # which the notification-service strict-schema chaos parser rejects.
    message = {
        "eventType": "file_shared",
        "fileId": str(uuid.uuid4()),
        "ownerId": str(uuid.uuid4()),
        "sharedWithUserId": str(uuid.uuid4()),
        "timestamp": int(time.time()),
    }
    return urllib.parse.urlencode(
        {"Action": "SendMessage", "MessageBody": json.dumps(message), "Version": "2012-11-05"}
    ).encode()


def http_request(
    url: str, method: str, headers: dict[str, str], body: bytes | None, timeout_s: float
) -> tuple[int | None, bytes, int, str | None]:
    """Return (status, body, latency_ms, error). Non-2xx is a status, not an error."""
    if urllib.parse.urlsplit(url).scheme not in ("http", "https"):
        raise ValueError(f"refusing non-http(s) URL: {url}")
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    started = time.monotonic()
    try:
        # URLs come from the committed endpoints file / env, scheme-checked above.
        # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            data = response.read()
            return response.status, data, int((time.monotonic() - started) * 1000), None
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), int((time.monotonic() - started) * 1000), None
    except Exception as exc:  # URLError, timeout, ConnectionReset
        return None, b"", int((time.monotonic() - started) * 1000), f"{type(exc).__name__}: {exc}"


def json_path(document: Any, path: str) -> tuple[bool, Any]:
    current = document
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return False, None
    return True, current


def parse_prometheus_metric(text: str, name: str) -> float | None:
    total = None
    for line in text.splitlines():
        if line.startswith("#") or not line.startswith(name):
            continue
        rest = line[len(name) :]
        if rest and rest[0] not in "{ ":
            continue
        try:
            total = (total or 0.0) + float(line.rsplit(" ", 1)[-1])
        except ValueError:
            continue
    return total


TYPE_NAMES = {
    "list": list,
    "dict": dict,
    "str": str,
    "int": int,
    "float": (int, float),
    "bool": bool,
}


class Checker:
    def __init__(self, config: dict[str, Any]):
        self.defaults = config.get("defaults", {})
        self.endpoints = config["endpoints"]
        self.metric_baseline: dict[str, float] = {}

    def run_pre(self, endpoint: dict[str, Any]) -> str | None:
        pre = endpoint.get("pre")
        if not pre:
            return None
        if pre["type"] == "sqs_send_epoch_timestamp":
            status, _, _, error = http_request(
                pre["url"],
                "POST",
                {"Content-Type": "application/x-www-form-urlencoded"},
                build_sqs_epoch_message(),
                self.defaults.get("timeout_s", 3),
            )
            if error or status is None or status >= 300:
                return f"pre-action sqs send failed: status={status} error={error}"
            time.sleep(pre.get("settle_ms", 0) / 1000)
            return None
        return f"unknown pre-action type {pre['type']}"

    def check(self, endpoint: dict[str, Any]) -> CheckResult:
        name, service = endpoint["name"], endpoint["service"]
        expect = endpoint.get("expect", {})
        headers = {**self.defaults.get("headers", {}), **endpoint.get("headers", {})}
        timeout_s = endpoint.get("timeout_s", self.defaults.get("timeout_s", 3))
        failures: list[str] = []

        pre_error = self.run_pre(endpoint)
        if pre_error:
            failures.append(pre_error)

        method = endpoint.get("method", "GET").upper()
        body: bytes | None = None
        if method == "MULTIPART_UPLOAD":
            boundary = f"api-verify-{uuid.uuid4().hex[:16]}"
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
            body, method = build_multipart(boundary), "POST"
        elif method == "POST" and "body" in endpoint:
            headers.setdefault("Content-Type", "application/json")
            body = json.dumps(endpoint["body"]).encode()

        status, raw, latency_ms, error = http_request(
            endpoint["url"], method, headers, body, timeout_s
        )
        text = raw.decode("utf-8", errors="replace")
        if error:
            failures.append(f"request failed: {error}")

        if "status" in expect and status != expect["status"]:
            failures.append(f"status: expected {expect['status']}, got {status}")
        if "max_latency_ms" in expect and latency_ms > expect["max_latency_ms"]:
            failures.append(
                f"latency: expected <= {expect['max_latency_ms']}ms, got {latency_ms}ms"
            )

        needs_json = any(k in expect for k in ("json_keys", "json_equals", "json_type"))
        document: Any = None
        if needs_json:
            try:
                document = json.loads(text) if text else None
            except json.JSONDecodeError:
                failures.append(f"body: expected JSON, got {text[:120]!r}")
        if document is not None:
            for key in expect.get("json_keys", []):
                if not json_path(document, key)[0]:
                    failures.append(f"json: missing key {key!r}")
            for path, wanted in expect.get("json_equals", {}).items():
                found, actual = json_path(document, path)
                if not found or actual != wanted:
                    failures.append(f"json.{path}: expected {wanted!r}, got {actual!r}")
            for path, type_name in expect.get("json_type", {}).items():
                found, actual = json_path(document, path)
                if not found or not isinstance(actual, TYPE_NAMES[type_name]):
                    failures.append(
                        f"json.{path}: expected {type_name}, got {type(actual).__name__}"
                    )

        for metric, max_delta in expect.get("metric_delta_max", {}).items():
            value = parse_prometheus_metric(text, metric)
            key = f"{name}:{metric}"
            if value is None:
                failures.append(f"metric {metric}: not found in response")
            elif key in self.metric_baseline:
                delta = value - self.metric_baseline[key]
                if delta > max_delta:
                    failures.append(
                        f"metric {metric}: increased by {delta:g} (max {max_delta}); now {value:g}"
                    )
            if value is not None:
                self.metric_baseline[key] = value

        return CheckResult(
            endpoint=name,
            service=service,
            scenario=endpoint.get("scenario"),
            ok=not failures,
            status=status,
            latency_ms=latency_ms,
            failures=failures,
            body_excerpt=text[:600],
        )

    def run_all(self) -> list[CheckResult]:
        return [self.check(endpoint) for endpoint in self.endpoints]


# ---------------------------------------------------------------------------
# Logs, prompt, Devin
# ---------------------------------------------------------------------------


def compose_command() -> list[str]:
    files = os.environ.get("COMPOSE_FILES", DEFAULT_COMPOSE_FILES).split()
    command = ["docker", "compose"]
    for name in files:
        command += ["-f", name]
    return command


def capture_logs(service: str, tail: int = LOG_TAIL_LINES) -> tuple[str, str]:
    """Return (full_tail, error_lines) for the service's container."""
    try:
        completed = subprocess.run(
            compose_command() + ["logs", "--no-color", "--tail", str(tail), service],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        output = completed.stdout or completed.stderr
    except (OSError, subprocess.TimeoutExpired) as exc:
        output = f"<docker compose logs failed: {exc}>"
    error_lines = [
        line for line in output.splitlines() if any(m in line.lower() for m in ERROR_MARKERS)
    ]
    return output, "\n".join(error_lines[-60:])


def build_prompt(
    service: str,
    results: list[CheckResult],
    full_logs: str,
    error_logs: str,
    attempt: int,
    max_attempts: int,
) -> str:
    repository = os.environ.get("GITHUB_REPOSITORY", DEFAULT_REPOSITORY)
    rebuild = " ".join(compose_command() + ["up", "-d", "--build", service])
    failing = "\n".join(
        f"- {r.endpoint}: HTTP {r.status}, {r.latency_ms}ms\n  expected vs actual: "
        + "; ".join(r.failures)
        + (f"\n  body: {r.body_excerpt[:300]!r}" if r.body_excerpt else "")
        for r in results
    )
    scenarios = sorted({r.scenario for r in results if r.scenario})
    return f"""You are fixing a failing API endpoint in the OtterWorks platform (repository {repository}), a polyglot microservices app running locally on Docker Compose. An API verification loop (scripts/api_verify_loop.py) has been polling the stack and one service is now failing its assertions.

## Affected service
`{service}` (Compose service name; source under services/{service}/)
Chaos scenario keys that could be active: {", ".join(scenarios) or "unknown"}

## Failing endpoint(s), expected vs actual
{failing}

## Recent error lines from `docker compose logs {service}`
```
{error_logs or "<no lines matched error markers; see full tail below>"}
```

<details><summary>Full log tail ({LOG_TAIL_LINES} lines)</summary>

```
{full_logs[-6000:]}
```
</details>

## Your task
1. Read the affected service's code and the logs above. Identify the root cause of the failing assertion — the code path that produces the wrong status/body/latency. If a chaos flag in Redis (`chaos:{service}:<scenario>`) selects the broken code path, treat that path as the bug: make the endpoint behave correctly whether or not the flag is set. Do not remove the flag check itself and do not clear the flag; the flag is how the fault is reproduced.
2. Implement a minimal fix in services/{service}/. Add or adjust a unit test that fails before and passes after.
3. Do not touch other services, do not fix the planted Rails logging bug in services/admin-service/config/environments/production.rb (see AGENTS.md), and do not merge.
4. Open a pull request against main from a new branch. In the PR body include: root cause, the fix, the test you added, and the exact command to rebuild the service locally: `{rebuild}`.

The verification loop will keep polling. Once a human has rebuilt the service from your branch it expects the endpoint(s) above to pass again. This is fix attempt {attempt} of {max_attempts}.
"""


def devin_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {os.environ['DEVIN_API_KEY']}",
        "Content-Type": "application/json",
    }


def devin_create_session(prompt: str, service: str) -> dict[str, Any]:
    # Mirrors DevinSessionService.create_session: POST /v3/organizations/<org>/sessions.
    # https://docs.devin.ai/api-reference/v3/sessions — body fields prompt, title, tags, repos.
    url = f"{DEVIN_API_BASE}/v3/organizations/{os.environ['DEVIN_ORG_ID']}/sessions"
    payload: dict[str, Any] = {
        "prompt": prompt,
        "title": f"API verify: {service} endpoint failing",
        "tags": ["api-verify-loop", service],
    }
    if os.environ.get("DEVIN_REPOS"):
        payload["repos"] = [r.strip() for r in os.environ["DEVIN_REPOS"].split(",") if r.strip()]
    status, raw, _, error = http_request(
        url, "POST", devin_headers(), json.dumps(payload).encode(), 30
    )
    if error or status is None or status >= 300:
        raise RuntimeError(f"Devin API returned {status}: {error or raw[:300]!r}")
    body = json.loads(raw)
    return {"session_id": body.get("session_id"), "url": body.get("url")}


def devin_get_session(session_id: str) -> dict[str, Any]:
    # Mirrors DevinSessionService.get_session and demo-platform POST /api/devin/poll.
    url = f"{DEVIN_API_BASE}/v3/organizations/{os.environ['DEVIN_ORG_ID']}/sessions/{session_id}"
    status, raw, _, error = http_request(url, "GET", devin_headers(), None, 30)
    if error or status is None or status >= 300:
        return {"status": f"poll-error {status or error}", "url": None, "pr_url": None}
    body = json.loads(raw)
    # v3 GET session returns pull_requests: [{pr_url, pr_state}] and status in
    # {new, claimed, running, exit, error, suspended, resuming}.
    pull_requests = body.get("pull_requests") or []
    pr_url = next(
        (pr.get("pr_url") for pr in pull_requests if isinstance(pr, dict) and pr.get("pr_url")),
        None,
    )
    return {
        "status": body.get("status") or body.get("status_enum"),
        "url": body.get("url"),
        "pr_url": pr_url,
    }


def webhook_trigger(
    service: str, results: list[CheckResult], prompt: str, error_logs: str, attempt: int
) -> dict[str, Any]:
    # Same envelope as sast-auto-remediate.yml: X-Webhook-Secret + JSON body.
    payload = {
        "source": "api-verify-loop",
        "repository": os.environ.get("GITHUB_REPOSITORY", DEFAULT_REPOSITORY),
        "branch": "main",
        "affected_service": service,
        "failing_endpoints": [
            {
                "endpoint": r.endpoint,
                "status": r.status,
                "latency_ms": r.latency_ms,
                "failures": r.failures,
            }
            for r in results
        ],
        "error_logs": error_logs[-3000:],
        "attempt": attempt,
        "prompt": prompt,
    }
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Secret": os.environ.get("DEVIN_WEBHOOK_SECRET", ""),
    }
    status, raw, _, error = http_request(
        os.environ["DEVIN_WEBHOOK_URL"], "POST", headers, json.dumps(payload).encode(), 30
    )
    if error or status is None or status >= 300:
        raise RuntimeError(f"webhook returned {status}: {error or raw[:300]!r}")
    body = json.loads(raw) if raw else {}
    return {"session_id": body.get("session_id"), "url": body.get("url")}


def admin_alert(
    service: str, results: list[CheckResult], error_logs: str, firing: bool
) -> dict[str, Any]:
    # Grafana-shaped payload for AlertsController#ingest, which creates an Incident and
    # calls DevinSessionService.create_session itself (visible on the admin dashboard).
    base = os.environ.get("ADMIN_SERVICE_URL", "http://localhost:8089").rstrip("/")
    summary = f"API verify: {', '.join(r.endpoint for r in results)} failing on {service}"
    description = "\n".join(
        f"{r.endpoint}: HTTP {r.status} in {r.latency_ms}ms; " + "; ".join(r.failures)
        for r in results
    ) + ("\n\nRecent error logs:\n" + error_logs[-2500:] if error_logs else "")
    payload = {
        "receiver": "api-verify-loop",
        "status": "firing" if firing else "resolved",
        "alerts": [
            {
                "status": "firing" if firing else "resolved",
                "labels": {
                    "alertname": "ApiVerifyAssertionFailed",
                    "severity": "critical",
                    "affected_service": service,
                },
                "annotations": {"summary": summary, "description": description},
                "startsAt": now_iso(),
            }
        ],
    }
    headers = {
        "Content-Type": "application/json",
        "X-Alert-Secret": os.environ.get("ALERT_WEBHOOK_SECRET", "demo-alert-secret"),
    }
    status, raw, _, error = http_request(
        f"{base}/api/v1/admin/alerts/ingest", "POST", headers, json.dumps(payload).encode(), 15
    )
    if error or status is None or status >= 300:
        raise RuntimeError(f"admin-service alerts/ingest returned {status}: {error or raw[:300]!r}")
    body = json.loads(raw) if raw else {}
    incidents = body.get("incidents") or []
    first = incidents[0] if incidents and isinstance(incidents[0], dict) else {}
    return {
        "session_id": None,
        "url": None,
        "incident_id": first.get("incident_id"),
        "skipped": first.get("skipped", False),
    }


# ---------------------------------------------------------------------------
# Loop
# ---------------------------------------------------------------------------


@dataclass
class ServiceState:
    consecutive_failures: int = 0
    consecutive_passes: int = 0
    attempts: int = 0
    open_incident: bool = False
    escalated: bool = False
    session_id: str | None = None
    session_url: str | None = None
    session_status: str | None = None
    pr_url: str | None = None
    last_failures: list[str] = field(default_factory=list)


class Emitter:
    def __init__(self, as_json: bool, report: Path | None):
        self.as_json = as_json
        self.report = report

    def emit(self, event: dict[str, Any]) -> None:
        line = json.dumps(event, ensure_ascii=False)
        if self.report:
            with self.report.open("a") as handle:
                handle.write(line + "\n")
        if self.as_json:
            print(line, flush=True)
            return
        kind = event["event"]
        if kind == "check":
            mark = "PASS" if event["result"] == "pass" else "FAIL"
            detail = "" if event["result"] == "pass" else "  " + "; ".join(event["failures"])
            print(
                f"{event['ts']} {mark:4} {event['endpoint']:<28} {event['service']:<22} "
                f"HTTP {event['status']!s:<4} {event['latency_ms']:>5}ms{detail}",
                flush=True,
            )
        else:
            extras = {k: v for k, v in event.items() if k not in ("ts", "event")}
            print(
                f"{event['ts']} {kind.upper():<10} "
                + " ".join(f"{k}={v}" for k, v in extras.items()),
                flush=True,
            )


class Loop:
    def __init__(self, args: argparse.Namespace, checker: Checker, emitter: Emitter):
        self.args = args
        self.checker = checker
        self.emitter = emitter
        self.state: dict[str, ServiceState] = {}
        self.last_results: list[CheckResult] = []
        self.max_attempts = int(os.environ.get("MAX_FIX_ATTEMPTS", args.max_attempts))

    def state_for(self, service: str) -> ServiceState:
        return self.state.setdefault(service, ServiceState())

    def trigger(self, service: str, results: list[CheckResult]) -> None:
        state = self.state_for(service)
        if state.attempts >= self.max_attempts:
            if not state.escalated:
                state.escalated = True
                self.emitter.emit(
                    {
                        "ts": now_iso(),
                        "event": "escalated",
                        "service": service,
                        "attempts": state.attempts,
                        "max_attempts": self.max_attempts,
                        "message": "fix attempts exhausted; needs a human",
                    }
                )
            return
        state.attempts += 1
        full_logs, error_logs = capture_logs(service)
        prompt = build_prompt(
            service, results, full_logs, error_logs, state.attempts, self.max_attempts
        )
        self.emitter.emit(
            {
                "ts": now_iso(),
                "event": "logs_captured",
                "service": service,
                "lines": len(full_logs.splitlines()),
                "error_lines": len(error_logs.splitlines()),
            }
        )
        if self.args.prompt_dir:
            path = Path(self.args.prompt_dir) / f"{service}-attempt{state.attempts}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(prompt)
        try:
            if self.args.trigger == "devin":
                created = devin_create_session(prompt, service)
            elif self.args.trigger == "webhook":
                created = webhook_trigger(service, results, prompt, error_logs, state.attempts)
            elif self.args.trigger == "admin":
                created = admin_alert(service, results, error_logs, firing=True)
            else:
                created = {"session_id": None, "url": None, "dry_run": True}
        except Exception as exc:
            state.attempts -= 1
            self.emitter.emit(
                {"ts": now_iso(), "event": "trigger_failed", "service": service, "error": str(exc)}
            )
            return
        state.open_incident = True
        state.session_id = created.get("session_id")
        state.session_url = created.get("url")
        self.emitter.emit(
            {
                "ts": now_iso(),
                "event": "devin_triggered",
                "service": service,
                "mode": self.args.trigger,
                "attempt": state.attempts,
                "max_attempts": self.max_attempts,
                **created,
            }
        )

    def poll_session(self, service: str) -> None:
        state = self.state_for(service)
        if not (state.session_id and self.args.trigger == "devin"):
            return
        info = devin_get_session(state.session_id)
        changed = info["status"] != state.session_status or (
            info["pr_url"] and info["pr_url"] != state.pr_url
        )
        state.session_status, state.pr_url = info["status"], info["pr_url"] or state.pr_url
        if changed:
            event = {
                "ts": now_iso(),
                "event": "session",
                "service": service,
                "status": state.session_status,
                "url": state.session_url or info["url"],
            }
            if state.pr_url:
                event["pr_url"] = state.pr_url
                event["rebuild"] = " ".join(compose_command() + ["up", "-d", "--build", service])
            self.emitter.emit(event)

    def resolve(self, service: str) -> None:
        state = self.state_for(service)
        if self.args.trigger == "admin":
            try:
                admin_alert(service, [], "", firing=False)
            except Exception as exc:
                self.emitter.emit(
                    {
                        "ts": now_iso(),
                        "event": "resolve_failed",
                        "service": service,
                        "error": str(exc),
                    }
                )
        self.emitter.emit(
            {
                "ts": now_iso(),
                "event": "recovered",
                "service": service,
                "attempts": state.attempts,
                "pr_url": state.pr_url,
                "message": "endpoint(s) green again; loop closed",
            }
        )
        state.open_incident = False

    def pass_once(self) -> bool:
        results = self.checker.run_all()
        self.last_results = results
        by_service: dict[str, list[CheckResult]] = {}
        for result in results:
            self.emitter.emit(result.to_event())
            by_service.setdefault(result.service, []).append(result)

        for service, service_results in by_service.items():
            state = self.state_for(service)
            failing = [r for r in service_results if not r.ok]
            if failing:
                state.consecutive_failures += 1
                state.consecutive_passes = 0
                state.last_failures = [f for r in failing for f in r.failures]
                if (
                    not state.open_incident
                    and state.consecutive_failures >= self.args.fail_threshold
                ):
                    self.trigger(service, failing)
            else:
                state.consecutive_passes += 1
                state.consecutive_failures = 0
                if state.open_incident and state.consecutive_passes >= self.args.recover_threshold:
                    self.resolve(service)
            if state.open_incident:
                self.poll_session(service)
        return all(r.ok for r in results)

    def run(self) -> int:
        if self.args.once:
            all_green = self.pass_once()
            failed = [r.endpoint for r in self.last_results if not r.ok]
            self.emitter.emit(
                {
                    "ts": now_iso(),
                    "event": "summary",
                    "pass": len(self.last_results) - len(failed),
                    "fail": len(failed),
                    "failed": failed,
                }
            )
            return 0 if all_green else 1
        polls = 0
        while True:
            polls += 1
            all_green = self.pass_once()
            if (
                self.args.until_green
                and all_green
                and any(s.attempts for s in self.state.values())
                and not any(s.open_incident for s in self.state.values())
            ):
                self.emitter.emit(
                    {"ts": now_iso(), "event": "done", "message": "all endpoints green after fix"}
                )
                return 0
            if self.args.max_polls and polls >= self.args.max_polls:
                self.emitter.emit(
                    {"ts": now_iso(), "event": "done", "message": f"max polls ({polls}) reached"}
                )
                return 0 if all_green else 1
            time.sleep(self.args.interval)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--once", action="store_true", help="single pass; exit 1 if any endpoint fails"
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="seconds between polls (ChaosProbeService uses 5)",
    )
    parser.add_argument(
        "--trigger",
        choices=["devin", "admin", "webhook", "none"],
        default="devin",
        help="how to start Devin on failure: Devin API, admin-service alerts/ingest, "
        "automation webhook, or dry run",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=2,
        help="fix sessions per service (env MAX_FIX_ATTEMPTS wins)",
    )
    parser.add_argument(
        "--fail-threshold", type=int, default=2, help="consecutive failing polls before triggering"
    )
    parser.add_argument(
        "--recover-threshold",
        type=int,
        default=2,
        help="consecutive passing polls before reporting recovery",
    )
    parser.add_argument(
        "--until-green", action="store_true", help="exit 0 once a triggered service is green again"
    )
    parser.add_argument("--max-polls", type=int, default=0, help="stop after N polls (0 = forever)")
    parser.add_argument("--json", action="store_true", help="emit JSON lines instead of text")
    parser.add_argument("--report", type=Path, help="append every event as JSON lines to this file")
    parser.add_argument(
        "--prompt-dir", type=Path, help="also write each generated Devin prompt to this directory"
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="limit to endpoints with this name or service (repeatable)",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    config = json.loads(args.config.read_text())
    if args.only:
        config["endpoints"] = [
            e for e in config["endpoints"] if e["name"] in args.only or e["service"] in args.only
        ]
    if (
        args.trigger == "devin"
        and not args.once
        and not (os.environ.get("DEVIN_API_KEY") and os.environ.get("DEVIN_ORG_ID"))
    ):
        print(
            "DEVIN_API_KEY and DEVIN_ORG_ID are required for --trigger devin "
            "(use --trigger none for a dry run)",
            file=sys.stderr,
        )
        return 2
    if args.trigger == "webhook" and not os.environ.get("DEVIN_WEBHOOK_URL"):
        print("DEVIN_WEBHOOK_URL is required for --trigger webhook", file=sys.stderr)
        return 2
    emitter = Emitter(args.json, args.report)
    try:
        return Loop(args, Checker(config), emitter).run()
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
