#!/usr/bin/env python3
"""Render the critical-API observability artifacts from the SLO catalog.

The catalog (critical-apis.yaml) is the source of truth. This script renders,
deterministically:

  * observability/prometheus/slo_rules.yml            SLI, error-budget and
                                                      burn-rate alerting rules
  * observability/prometheus/targets/critical-api-probes.json
                                                      blackbox probe targets
  * observability/grafana/dashboards/critical-api-slo.json
                                                      SLO dashboard
  * services/api-gateway/internal/middleware/routes_generated.go
                                                      gateway route label table

Usage:
    python3 observability/slo/generate.py            # write the artifacts
    python3 observability/slo/generate.py --check    # fail if they are stale
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = REPO_ROOT / "observability" / "slo" / "critical-apis.yaml"

BLACKBOX_PATH = REPO_ROOT / "observability" / "blackbox" / "blackbox.yml"

RULES_PATH = REPO_ROOT / "observability" / "prometheus" / "slo_rules.yml"
PROBE_TARGETS_PATH = (
    REPO_ROOT / "observability" / "prometheus" / "targets" / "critical-api-probes.json"
)
DASHBOARD_PATH = (
    REPO_ROOT / "observability" / "grafana" / "dashboards" / "critical-api-slo.json"
)
ROUTES_GO_PATH = (
    REPO_ROOT
    / "services"
    / "api-gateway"
    / "internal"
    / "middleware"
    / "routes_generated.go"
)

# Windows the SLIs are recorded over. Every burn-rate window referenced by the
# catalog must appear here, plus the SLO window used for budget accounting.
SLI_WINDOWS = ["5m", "30m", "1h", "2h", "6h", "1d", "3d", "30d"]

REQUESTS_TOTAL = "api_gateway_http_requests_total"
DURATION_BUCKET = "api_gateway_http_request_duration_seconds_bucket"
DURATION_COUNT = "api_gateway_http_request_duration_seconds_count"

PROBE_JOB = "blackbox-critical-api"

# Blackbox exporter modules, keyed by the status codes a probe accepts.
PROBE_MODULES = {
    (200,): "http_2xx",
}

GENERATED_BY = "observability/slo/generate.py from observability/slo/critical-apis.yaml"

# Blackbox-exporter parses module timeouts as Go durations: fractional amounts
# are allowed, and the units stop at hours.
DURATION_UNIT_SECONDS = {
    "ns": 1e-9,
    "us": 1e-6,
    "\u00b5s": 1e-6,
    "\u03bcs": 1e-6,
    "ms": 0.001,
    "s": 1.0,
    "m": 60.0,
    "h": 3600.0,
}
_DURATION_PART = r"(?:\d+(?:\.\d*)?|\.\d+)(?:ns|us|\u00b5s|\u03bcs|ms|s|m|h)"
DURATION_RE = re.compile(rf"({_DURATION_PART})")
DURATION_UNIT_RE = re.compile(r"([\d.]+)(\D+)")

# admin-service ingests an alert only if it names the affected service in
# affected_service or service; our series identify it as backend.
INGEST_LABEL = {"affected_service": "{{ $labels.backend }}"}


class LiteralStr(str):
    """A string rendered as a YAML literal block, so PromQL stays readable."""


class RuleDumper(yaml.SafeDumper):
    """Dumper that never emits anchors, so the rules stay diff-friendly."""

    def ignore_aliases(self, data: Any) -> bool:
        return True


def _literal_representer(dumper: yaml.Dumper, data: LiteralStr) -> yaml.ScalarNode:
    return dumper.represent_scalar("tag:yaml.org,2002:str", str(data), style="|")


RuleDumper.add_representer(LiteralStr, _literal_representer)


@dataclass(frozen=True)
class BurnRate:
    name: str
    factor: float
    long_window: str
    short_window: str
    severity: str
    budget_consumed: str

    @property
    def alert_suffix(self) -> str:
        return "".join(part.capitalize() for part in self.name.split("_"))


@dataclass(frozen=True)
class Endpoint:
    id: str
    service: str
    owner: str
    method: str
    route: str
    tier: str
    availability: float
    latency_threshold: float
    latency_objective: float
    expect_traffic: bool
    runbook: str

    @property
    def match_labels(self) -> dict[str, str]:
        return {"backend": self.service, "method": self.method, "route": self.route}


class CatalogError(Exception):
    """Raised when the catalog is internally inconsistent."""


def load_catalog(path: Path) -> tuple[dict[str, Any], list[Endpoint], list[BurnRate]]:
    catalog = yaml.safe_load(path.read_text())

    burn_rates = [BurnRate(**entry) for entry in catalog["burn_rates"]]
    buckets = {float(b) for b in catalog["latency_buckets"]}

    endpoints: list[Endpoint] = []
    for entry in catalog["endpoints"]:
        latency = entry["latency"]
        endpoints.append(
            Endpoint(
                id=entry["id"],
                service=entry["service"],
                owner=entry["owner"],
                method=entry["method"],
                route=entry["route"],
                tier=entry["tier"],
                availability=float(entry["availability"]),
                latency_threshold=float(latency["threshold"]),
                latency_objective=float(latency["objective"]),
                expect_traffic=bool(entry.get("expect_traffic", False)),
                runbook=entry["runbook"],
            )
        )

    validate(catalog, endpoints, burn_rates, buckets)
    return catalog, endpoints, burn_rates


def validate(
    catalog: dict[str, Any],
    endpoints: list[Endpoint],
    burn_rates: list[BurnRate],
    buckets: set[float],
) -> None:
    seen_ids: set[str] = set()
    seen_keys: set[tuple[str, str]] = set()
    thresholds_by_route: dict[str, float] = {}

    for endpoint in endpoints:
        if endpoint.id in seen_ids:
            raise CatalogError(f"duplicate endpoint id: {endpoint.id}")
        seen_ids.add(endpoint.id)

        key = (endpoint.method, endpoint.route)
        if key in seen_keys:
            raise CatalogError(f"duplicate endpoint: {endpoint.method} {endpoint.route}")
        seen_keys.add(key)

        if endpoint.latency_threshold not in buckets:
            raise CatalogError(
                f"{endpoint.id}: latency threshold {endpoint.latency_threshold}s is not a "
                "histogram bucket boundary, so the latency SLI cannot be measured"
            )

        # The latency SLI selects a bucket per route, so two methods on the
        # same route template cannot disagree about the threshold.
        previous = thresholds_by_route.setdefault(endpoint.route, endpoint.latency_threshold)
        if previous != endpoint.latency_threshold:
            raise CatalogError(
                f"{endpoint.route}: conflicting latency thresholds "
                f"({previous}s and {endpoint.latency_threshold}s) across methods"
            )

        if not 0 < endpoint.availability < 1:
            raise CatalogError(f"{endpoint.id}: availability must be between 0 and 1")
        if not 0 < endpoint.latency_objective < 1:
            raise CatalogError(f"{endpoint.id}: latency objective must be between 0 and 1")

        runbook = REPO_ROOT / "docs" / "runbooks" / f"{endpoint.runbook}.md"
        if not runbook.exists():
            raise CatalogError(f"{endpoint.id}: runbook {runbook.name} does not exist")


    for burn_rate in burn_rates:
        for window in (burn_rate.long_window, burn_rate.short_window):
            if window not in SLI_WINDOWS:
                raise CatalogError(
                    f"burn rate {burn_rate.name} uses window {window}, which is not recorded"
                )

    for entry in catalog["endpoints"]:
        # An unauthenticated probe of a protected route is answered by the
        # gateway's JWT middleware, never by the backend, so it would report
        # success through a backend outage. Probes belong in health_probes.
        if "probe" in entry:
            raise CatalogError(
                f"{entry['id']}: endpoints cannot define probes; add a credential-free "
                "liveness check to health_probes instead"
            )

    probe_ids: set[str] = set()
    modules_in_use: set[str] = set()
    for probe in catalog.get("health_probes", []):
        if probe["id"] in probe_ids:
            raise CatalogError(f"duplicate health probe id: {probe['id']}")
        probe_ids.add(probe["id"])

        if not probe["url"].endswith("/health"):
            raise CatalogError(
                f"{probe['id']}: health probes must target a /health endpoint, got {probe['url']}"
            )
        modules_in_use.add(_probe_module(probe["id"], probe["expect_status"]))

    # A probe slower than its module's timeout is recorded as a failure, not as
    # a slow success, so the slow-probe warning only fires if it sits strictly
    # below the timeout.
    warn_after = float(catalog["probe"]["max_duration_seconds"])
    for module, timeout in _module_timeouts(modules_in_use).items():
        if warn_after >= timeout:
            raise CatalogError(
                f"probe.max_duration_seconds ({_fmt(warn_after)}s) must be below the "
                f"{module} module timeout ({_fmt(timeout)}s), or a slow probe fails "
                "before it can warn"
            )


def _module_timeouts(modules: set[str]) -> dict[str, float]:
    """Timeout, in seconds, of each named blackbox module."""
    configured = yaml.safe_load(BLACKBOX_PATH.read_text())["modules"]
    timeouts: dict[str, float] = {}
    for module in sorted(modules):
        if module not in configured:
            raise CatalogError(f"blackbox module {module} is not defined in {BLACKBOX_PATH.name}")
        timeouts[module] = _parse_duration(module, configured[module]["timeout"])
    return timeouts


def _parse_duration(context: str, value: object) -> float:
    """Seconds in a blackbox module timeout such as `1500ms`, `5s` or `1m30s`."""
    text = str(value)
    if not re.fullmatch(f"({_DURATION_PART})+", text):
        raise CatalogError(
            f"{context}: module timeout {text!r} is not a duration blackbox can parse"
        )
    seconds = 0.0
    for part in DURATION_RE.findall(text):
        amount, unit = DURATION_UNIT_RE.fullmatch(part).groups()
        seconds += float(amount) * DURATION_UNIT_SECONDS[unit]
    return seconds


def _probe_module(owner_id: str, expect_status: list[int]) -> str:
    key = tuple(sorted(int(code) for code in expect_status))
    if key not in PROBE_MODULES:
        raise CatalogError(
            f"{owner_id}: no blackbox module accepts status codes {list(key)}; "
            f"add one to observability/blackbox/blackbox.yml and to PROBE_MODULES"
        )
    return PROBE_MODULES[key]


def _fmt(value: float) -> str:
    """Format a float the way PromQL and Prometheus bucket labels expect."""
    text = f"{value:g}"
    return text


# ---------------------------------------------------------------------------
# Prometheus rules
# ---------------------------------------------------------------------------


def metadata_rules(endpoints: list[Endpoint], slo_window: str) -> dict[str, Any]:
    """Objectives as series, so the alerting rules can stay endpoint-agnostic.

    Every alert joins against these on (backend, method, route), which is what
    keeps a 14-endpoint catalog from turning into 60 hand-maintained alerts.
    """
    rules: list[dict[str, Any]] = []
    for endpoint in endpoints:
        labels = {
            **endpoint.match_labels,
            "endpoint_id": endpoint.id,
            "tier": endpoint.tier,
            "owner": endpoint.owner,
            "runbook": endpoint.runbook,
            "slo_window": slo_window,
        }
        rules.append(
            {
                "record": "slo:api_endpoint:availability_objective",
                "expr": f"vector({_fmt(endpoint.availability)})",
                "labels": labels,
            }
        )
        rules.append(
            {
                "record": "slo:api_endpoint:latency_objective",
                "expr": f"vector({_fmt(endpoint.latency_objective)})",
                "labels": labels,
            }
        )
        rules.append(
            {
                "record": "slo:api_endpoint:latency_threshold_seconds",
                "expr": f"vector({_fmt(endpoint.latency_threshold)})",
                "labels": labels,
            }
        )
        if endpoint.expect_traffic:
            rules.append(
                {
                    "record": "slo:api_endpoint:expect_traffic",
                    "expr": "vector(1)",
                    "labels": labels,
                }
            )
    return {"name": "otterworks.slo.metadata", "interval": "1m", "rules": rules}


def sli_rules(endpoints: list[Endpoint]) -> dict[str, Any]:
    rules: list[dict[str, Any]] = []

    for window in SLI_WINDOWS:
        rules.append(
            {
                "record": f"slo:api_request:rate{window}",
                "expr": LiteralStr(
                    f"sum by (backend, method, route) (rate({REQUESTS_TOTAL}[{window}]))\n"
                    "and on (backend, method, route)\n"
                    "slo:api_endpoint:availability_objective\n"
                ),
            }
        )

    for window in SLI_WINDOWS:
        rules.append(
            {
                "record": f"slo:api_request_errors:ratio_rate{window}",
                # An endpoint that has never served a 5xx has no matching
                # numerator series, and division would drop it entirely, so its
                # availability and remaining budget would read as "no data"
                # until it first fails. The `or` supplies an explicit zero.
                "expr": LiteralStr(
                    "(\n"
                    "  (\n"
                    f'    sum by (backend, method, route) (rate({REQUESTS_TOTAL}{{status=~"5.."}}[{window}]))\n'
                    "    or\n"
                    f"    0 * sum by (backend, method, route) (rate({REQUESTS_TOTAL}[{window}]))\n"
                    "  )\n"
                    "  /\n"
                    f"  sum by (backend, method, route) (rate({REQUESTS_TOTAL}[{window}]))\n"
                    ")\n"
                    "and on (backend, method, route)\n"
                    "slo:api_endpoint:availability_objective\n"
                ),
            }
        )

    # One branch per distinct threshold, selected by the endpoint's own
    # threshold series. The branches are disjoint, so `or` unions them into a
    # single series per endpoint whatever its threshold is.
    thresholds = sorted({endpoint.latency_threshold for endpoint in endpoints})
    for window in SLI_WINDOWS:
        branches = []
        for threshold in thresholds:
            le = _fmt(threshold)
            branches.append(
                "(\n"
                "  (\n"
                "    1 - (\n"
                f'      sum by (backend, method, route) (rate({DURATION_BUCKET}{{le="{le}"}}[{window}]))\n'
                "      /\n"
                f"      sum by (backend, method, route) (rate({DURATION_COUNT}[{window}]))\n"
                "    )\n"
                "  )\n"
                "  and on (backend, method, route)\n"
                f"  (slo:api_endpoint:latency_threshold_seconds == {le})\n"
                ")"
            )
        rules.append(
            {
                "record": f"slo:api_request_latency:bad_ratio_rate{window}",
                "expr": LiteralStr("\nor\n".join(branches) + "\n"),
            }
        )

    return {"name": "otterworks.slo.sli", "interval": "30s", "rules": rules}


def budget_rules() -> dict[str, Any]:
    return {
        "name": "otterworks.slo.budget",
        "interval": "1m",
        "rules": [
            {
                "record": "slo:api_error_budget:remaining_ratio",
                "expr": LiteralStr(
                    "1 - (\n"
                    "  slo:api_request_errors:ratio_rate30d\n"
                    "  / on (backend, method, route) group_left ()\n"
                    "  (1 - slo:api_endpoint:availability_objective)\n"
                    ")\n"
                ),
            },
            {
                "record": "slo:api_latency_budget:remaining_ratio",
                "expr": LiteralStr(
                    "1 - (\n"
                    "  slo:api_request_latency:bad_ratio_rate30d\n"
                    "  / on (backend, method, route) group_left ()\n"
                    "  (1 - slo:api_endpoint:latency_objective)\n"
                    ")\n"
                ),
            },
        ],
    }


def _burn_expr(sli_metric: str, objective_metric: str, burn_rate: BurnRate) -> LiteralStr:
    threshold = f"({_fmt(burn_rate.factor)} * (1 - {objective_metric}))"
    return LiteralStr(
        "(\n"
        f"  {sli_metric}{burn_rate.long_window}\n"
        "    > on (backend, method, route) group_left (endpoint_id, tier, owner, runbook)\n"
        f"  {threshold}\n"
        ")\n"
        "and on (backend, method, route)\n"
        "(\n"
        f"  {sli_metric}{burn_rate.short_window}\n"
        "    > on (backend, method, route)\n"
        f"  {threshold}\n"
        ")\n"
    )


def burn_rate_alerts(burn_rates: list[BurnRate], slo_window: str) -> dict[str, Any]:
    rules: list[dict[str, Any]] = []

    for burn_rate in burn_rates:
        rules.append(
            {
                "alert": f"CriticalApiErrorBudgetBurn{burn_rate.alert_suffix}",
                "expr": _burn_expr(
                    "slo:api_request_errors:ratio_rate",
                    "slo:api_endpoint:availability_objective",
                    burn_rate,
                ),
                "for": "2m",
                "labels": {
                    **INGEST_LABEL,
                    "severity": burn_rate.severity,
                    "slo": "availability",
                    "burn_rate": burn_rate.name,
                },
                "annotations": {
                    "summary": (
                        "{{ $labels.method }} {{ $labels.route }} is burning its "
                        f"availability error budget ({burn_rate.name})"
                    ),
                    "description": (
                        "{{ $labels.endpoint_id }} ({{ $labels.owner }}) is returning 5xx "
                        f"{_fmt(burn_rate.factor)}x faster than its {slo_window} availability "
                        "objective allows, over the last "
                        f"{burn_rate.long_window} and {burn_rate.short_window}. At this rate it "
                        f"consumes {burn_rate.budget_consumed}."
                    ),
                    "runbook_url": "https://docs.otterworks.dev/runbooks/{{ $labels.runbook }}",
                },
            }
        )

    for burn_rate in burn_rates:
        rules.append(
            {
                "alert": f"CriticalApiLatencyBudgetBurn{burn_rate.alert_suffix}",
                "expr": _burn_expr(
                    "slo:api_request_latency:bad_ratio_rate",
                    "slo:api_endpoint:latency_objective",
                    burn_rate,
                ),
                "for": "5m",
                "labels": {
                    **INGEST_LABEL,
                    "severity": burn_rate.severity,
                    "slo": "latency",
                    "burn_rate": burn_rate.name,
                },
                "annotations": {
                    "summary": (
                        "{{ $labels.method }} {{ $labels.route }} is burning its "
                        f"latency budget ({burn_rate.name})"
                    ),
                    "description": (
                        "{{ $labels.endpoint_id }} ({{ $labels.owner }}) is serving requests "
                        "slower than its latency objective "
                        f"{_fmt(burn_rate.factor)}x faster than the {slo_window} budget allows, "
                        f"over the last {burn_rate.long_window} and {burn_rate.short_window}."
                    ),
                    "runbook_url": "https://docs.otterworks.dev/runbooks/{{ $labels.runbook }}",
                },
            }
        )

    return {"name": "otterworks.slo.burn_rate", "rules": rules}


def traffic_alerts() -> dict[str, Any]:
    return {
        "name": "otterworks.slo.traffic",
        "rules": [
            {
                "alert": "CriticalApiNoTraffic",
                # A silent endpoint produces no error ratio at all, so the burn
                # rate alerts above cannot see it. This is the companion check.
                "expr": LiteralStr(
                    "(slo:api_endpoint:expect_traffic == 1)\n"
                    "unless on (backend, method, route)\n"
                    "(slo:api_request:rate5m > 0)\n"
                ),
                "for": "15m",
                "labels": {**INGEST_LABEL, "severity": "critical", "slo": "availability"},
                "annotations": {
                    "summary": "{{ $labels.method }} {{ $labels.route }} has served no traffic for 15m",
                    "description": (
                        "{{ $labels.endpoint_id }} ({{ $labels.owner }}) normally serves "
                        "continuous traffic. Zero requests usually means the gateway route, "
                        "the client, or the whole service is broken rather than idle."
                    ),
                    "runbook_url": "https://docs.otterworks.dev/runbooks/{{ $labels.runbook }}",
                },
            }
        ],
    }


def probe_alerts(catalog: dict[str, Any]) -> dict[str, Any]:
    probe_latency_budget = float(catalog["probe"]["max_duration_seconds"])
    return {
        "name": "otterworks.slo.probes",
        "rules": [
            {
                "alert": "CriticalApiProbeFailing",
                "expr": LiteralStr(f'probe_success{{job="{PROBE_JOB}"}} == 0\n'),
                "for": "2m",
                "labels": {**INGEST_LABEL, "severity": "critical", "slo": "availability"},
                "annotations": {
                    "summary": "{{ $labels.backend }} is failing its health probe",
                    "description": (
                        "The synthetic health check {{ $labels.probe_id }} against "
                        "{{ $labels.instance }} has failed for 2 minutes, so "
                        "{{ $labels.backend }} is down or unreachable. This fires "
                        "independently of user traffic, so it catches outages during quiet hours."
                    ),
                    "runbook_url": "https://docs.otterworks.dev/runbooks/critical-api-slo",
                },
            },
            {
                "alert": "CriticalApiProbeSlow",
                # probe_duration_seconds is also reported for a probe that
                # failed or timed out, which CriticalApiProbeFailing already
                # covers; without the join one outage pages and warns at once.
                "expr": LiteralStr(
                    f'probe_duration_seconds{{job="{PROBE_JOB}"}} > {_fmt(probe_latency_budget)}\n'
                    "and on (instance)\n"
                    f'(probe_success{{job="{PROBE_JOB}"}} == 1)\n'
                ),
                "for": "10m",
                "labels": {**INGEST_LABEL, "severity": "warning", "slo": "latency"},
                "annotations": {
                    "summary": "{{ $labels.backend }} health probe is slow",
                    "description": (
                        "The synthetic health check {{ $labels.probe_id }} took "
                        "{{ $value | humanizeDuration }}, above the "
                        f"{_fmt(probe_latency_budget)}s probe budget."
                    ),
                    "runbook_url": "https://docs.otterworks.dev/runbooks/critical-api-slo",
                },
            },
        ],
    }


def render_rules(
    catalog: dict[str, Any], endpoints: list[Endpoint], burn_rates: list[BurnRate]
) -> str:
    slo_window = catalog["slo_window"]
    document = {
        "groups": [
            metadata_rules(endpoints, slo_window),
            sli_rules(endpoints),
            budget_rules(),
            burn_rate_alerts(burn_rates, slo_window),
            traffic_alerts(),
            probe_alerts(catalog),
        ]
    }
    body = yaml.dump(
        document, Dumper=RuleDumper, sort_keys=False, width=100, default_flow_style=False
    )
    return (
        f"# Code generated by {GENERATED_BY}\n"
        "# DO NOT EDIT. Run `make slo-generate` after changing the catalog.\n"
        "#\n"
        f"# SLO window: {slo_window}. Objectives are recorded as series so that a single\n"
        "# set of burn-rate alerts covers every endpoint in the catalog.\n"
        f"{body}"
    )


# ---------------------------------------------------------------------------
# Blackbox probe targets
# ---------------------------------------------------------------------------


def render_probe_targets(catalog: dict[str, Any], endpoints: list[Endpoint]) -> str:
    owners_by_service = {endpoint.service: endpoint.owner for endpoint in endpoints}
    entries: list[dict[str, Any]] = []

    for probe in catalog.get("health_probes", []):
        labels = {
            "__param_module": _probe_module(probe["id"], probe["expect_status"]),
            "probe_id": probe["id"],
            "backend": probe["backend"],
            "probe_kind": "health",
        }
        owner = probe.get("owner", owners_by_service.get(probe["backend"]))
        if owner is not None:
            labels["owner"] = owner
        entries.append({"targets": [probe["url"]], "labels": labels})

    return json.dumps(entries, indent=2) + "\n"


# ---------------------------------------------------------------------------
# Grafana dashboard
# ---------------------------------------------------------------------------


def _panel(
    title: str,
    panel_type: str,
    grid: tuple[int, int, int, int],
    targets: list[dict[str, Any]],
    description: str = "",
    field_config: dict[str, Any] | None = None,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    height, width, x, y = grid
    panel: dict[str, Any] = {
        "title": title,
        "type": panel_type,
        "description": description,
        "gridPos": {"h": height, "w": width, "x": x, "y": y},
        "datasource": {"type": "prometheus", "uid": "${datasource}"},
        "targets": targets,
    }
    if field_config is not None:
        panel["fieldConfig"] = field_config
    if options is not None:
        panel["options"] = options
    return panel


def render_dashboard(catalog: dict[str, Any], burn_rates: list[BurnRate]) -> str:
    fast = next(b for b in burn_rates if b.name == "fast")
    legend = "{{ method }} {{ route }}"

    percent_unit = {"defaults": {"unit": "percentunit"}, "overrides": []}

    panels = [
        _panel(
            "Endpoints burning error budget now",
            "stat",
            (4, 6, 0, 0),
            [
                {
                    "expr": (
                        "count(\n"
                        f"  slo:api_request_errors:ratio_rate{fast.long_window}\n"
                        "    > on (backend, method, route) group_left ()\n"
                        f"  ({_fmt(fast.factor)} * (1 - slo:api_endpoint:availability_objective))\n"
                        ") or vector(0)"
                    ),
                    "legendFormat": "endpoints",
                }
            ],
            description=(
                "Critical endpoints currently consuming their error budget at the fast "
                "burn rate. Anything above zero is a page in flight or about to fire."
            ),
            field_config={
                "defaults": {
                    "thresholds": {
                        "mode": "absolute",
                        "steps": [
                            {"color": "green", "value": None},
                            {"color": "red", "value": 1},
                        ],
                    }
                },
                "overrides": [],
            },
        ),
        _panel(
            "Failing synthetic probes",
            "stat",
            (4, 6, 6, 0),
            [
                {
                    "expr": f'count(probe_success{{job="{PROBE_JOB}"}} == 0) or vector(0)',
                    "legendFormat": "probes",
                }
            ],
            description=(
                "Synthetic checks run every 30s regardless of user traffic, so an outage "
                "with no requests still shows up here."
            ),
            field_config={
                "defaults": {
                    "thresholds": {
                        "mode": "absolute",
                        "steps": [
                            {"color": "green", "value": None},
                            {"color": "red", "value": 1},
                        ],
                    }
                },
                "overrides": [],
            },
        ),
        _panel(
            "Error budget remaining (30d)",
            "bargauge",
            (8, 12, 12, 0),
            [
                {
                    "expr": "sort(slo:api_error_budget:remaining_ratio)",
                    "legendFormat": legend,
                    "instant": True,
                }
            ],
            description="Fraction of the 30d availability error budget still unspent.",
            field_config={
                "defaults": {
                    "unit": "percentunit",
                    "min": 0,
                    "max": 1,
                    "thresholds": {
                        "mode": "absolute",
                        "steps": [
                            {"color": "red", "value": None},
                            {"color": "orange", "value": 0.25},
                            {"color": "green", "value": 0.5},
                        ],
                    },
                },
                "overrides": [],
            },
        ),
        _panel(
            "Availability SLI vs objective",
            "timeseries",
            (8, 12, 0, 4),
            [
                {
                    "expr": "1 - slo:api_request_errors:ratio_rate1h",
                    "legendFormat": legend,
                },
                {
                    "expr": "slo:api_endpoint:availability_objective",
                    "legendFormat": "objective " + legend,
                },
            ],
            description="Rolling 1h success ratio per critical endpoint against its objective.",
            field_config=percent_unit,
        ),
        _panel(
            "Latency SLI: requests over budget (1h)",
            "timeseries",
            (8, 12, 12, 8),
            [
                {
                    "expr": "slo:api_request_latency:bad_ratio_rate1h",
                    "legendFormat": legend,
                },
                {
                    "expr": "1 - slo:api_endpoint:latency_objective",
                    "legendFormat": "budget " + legend,
                },
            ],
            description=(
                "Share of requests slower than the endpoint's latency threshold, "
                "compared with the share the objective permits."
            ),
            field_config=percent_unit,
        ),
        _panel(
            f"Availability burn rate ({fast.long_window})",
            "timeseries",
            (8, 12, 0, 12),
            [
                {
                    "expr": (
                        "slo:api_request_errors:ratio_rate1h\n"
                        "  / on (backend, method, route) group_left ()\n"
                        "(1 - slo:api_endpoint:availability_objective)"
                    ),
                    "legendFormat": legend,
                }
            ],
            description=(
                "Budget consumption multiplier. 1x spends the whole 30d budget in exactly "
                f"30d; {_fmt(fast.factor)}x is the fast-burn page threshold."
            ),
        ),
        _panel(
            "Request rate by critical endpoint",
            "timeseries",
            (8, 12, 12, 16),
            [{"expr": "slo:api_request:rate5m", "legendFormat": legend}],
            description="Traffic per endpoint; a drop to zero fires CriticalApiNoTraffic.",
            field_config={"defaults": {"unit": "reqps"}, "overrides": []},
        ),
        _panel(
            "Synthetic probe success",
            "state-timeline",
            (6, 12, 0, 20),
            [
                {
                    "expr": f'probe_success{{job="{PROBE_JOB}"}}',
                    "legendFormat": "{{ probe_id }}",
                }
            ],
            description="Blackbox health probe results per backend service.",
            field_config={
                "defaults": {
                    "mappings": [
                        {"options": {"0": {"text": "FAIL", "color": "red"}}, "type": "value"},
                        {"options": {"1": {"text": "OK", "color": "green"}}, "type": "value"},
                    ]
                },
                "overrides": [],
            },
        ),
        _panel(
            "Synthetic probe duration",
            "timeseries",
            (6, 12, 12, 24),
            [
                {
                    "expr": f'probe_duration_seconds{{job="{PROBE_JOB}"}}',
                    "legendFormat": "{{ probe_id }}",
                }
            ],
            description="End-to-end probe latency through the shared ingress and gateway.",
            field_config={"defaults": {"unit": "s"}, "overrides": []},
        ),
    ]

    dashboard = {
        "id": None,
        "uid": "critical-api-slo",
        "title": "Critical API SLOs",
        "description": (
            "Per-endpoint availability and latency SLOs for the APIs listed in "
            "observability/slo/critical-apis.yaml. Generated by "
            f"{GENERATED_BY.split(' from ')[0]}; do not edit in Grafana."
        ),
        "tags": ["otterworks", "slo", "critical-api"],
        "timezone": "utc",
        "editable": False,
        "graphTooltip": 1,
        "templating": {
            "list": [
                {
                    "name": "datasource",
                    "type": "datasource",
                    "query": "prometheus",
                    "current": {"text": "Prometheus", "value": "Prometheus"},
                }
            ]
        },
        "panels": panels,
        "time": {"from": "now-6h", "to": "now"},
        "refresh": "30s",
    }
    return json.dumps(dashboard, indent=2) + "\n"


# ---------------------------------------------------------------------------
# Gateway route table
# ---------------------------------------------------------------------------


def render_routes_go(endpoints: list[Endpoint]) -> str:
    lines = [
        f"// Code generated by {GENERATED_BY}",
        "// DO NOT EDIT. Run `make slo-generate` after changing the catalog.",
        "",
        "package middleware",
        "",
        "// criticalRoutes are the endpoints under an SLO. Requests matching one of",
        "// these are labelled with the route template so a single failing endpoint is",
        "// visible instead of being averaged into its service prefix. Everything else",
        "// falls back to the prefix label, which keeps metric cardinality bounded.",
        "var criticalRoutes = []routePattern{",
    ]
    for endpoint in sorted(endpoints, key=lambda e: (e.route, e.method)):
        lines.append(
            f'\t{{method: "{endpoint.method}", template: "{endpoint.route}", '
            f'service: "{endpoint.service}"}},'
        )
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------


def render_all(catalog_path: Path = CATALOG_PATH) -> dict[Path, str]:
    """Render every artifact, keyed by the path it is written to."""
    catalog, endpoints, burn_rates = load_catalog(catalog_path)
    return {
        RULES_PATH: render_rules(catalog, endpoints, burn_rates),
        PROBE_TARGETS_PATH: render_probe_targets(catalog, endpoints),
        DASHBOARD_PATH: render_dashboard(catalog, burn_rates),
        ROUTES_GO_PATH: render_routes_go(endpoints),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the generated artifacts are up to date instead of writing them",
    )
    parser.add_argument("--catalog", type=Path, default=CATALOG_PATH)
    args = parser.parse_args(argv)

    try:
        artifacts = render_all(args.catalog)
    except CatalogError as exc:
        print(f"invalid catalog: {exc}", file=sys.stderr)
        return 2

    stale: list[Path] = []
    for path, content in artifacts.items():
        if args.check:
            current = path.read_text() if path.exists() else None
            if current != content:
                stale.append(path)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    if args.check:
        if stale:
            print("generated observability artifacts are stale:", file=sys.stderr)
            for path in stale:
                print(f"  {path.relative_to(REPO_ROOT)}", file=sys.stderr)
            print("run `make slo-generate` and commit the result", file=sys.stderr)
            return 1
        print(f"{len(artifacts)} generated artifacts are up to date")
        return 0

    for path in artifacts:
        print(f"wrote {path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
