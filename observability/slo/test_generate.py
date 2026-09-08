"""Tests for the critical-API SLO generator.

Run with: uv run --with pyyaml==6.0.2 --with pytest observability/slo/test_generate.py
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent))

import generate  # noqa: E402


@pytest.fixture(scope="module")
def catalog_bundle():
    return generate.load_catalog(generate.CATALOG_PATH)


def test_catalog_is_valid(catalog_bundle):
    catalog, endpoints, burn_rates = catalog_bundle
    assert endpoints, "catalog must define at least one critical endpoint"
    assert burn_rates, "catalog must define burn rates"
    assert catalog["slo_window"].endswith("d")


def test_generated_artifacts_match_catalog():
    """`make slo-check` is what CI runs; this keeps the failure local and fast."""
    stale = [
        path.name
        for path, rendered in generate.render_all().items()
        if not path.exists() or path.read_text() != rendered
    ]
    assert not stale, "generated artifacts are stale; run `make slo-generate`"


def test_every_endpoint_has_sli_and_objective_series(catalog_bundle):
    _, endpoints, _ = catalog_bundle
    rules = yaml.safe_load(generate.render_rules(*catalog_bundle))
    objectives = [
        rule
        for group in rules["groups"]
        for rule in group["rules"]
        if rule.get("record") == "slo:api_endpoint:availability_objective"
    ]
    assert {rule["labels"]["endpoint_id"] for rule in objectives} == {e.id for e in endpoints}
    for rule in objectives:
        labels = rule["labels"]
        assert {"backend", "method", "route", "runbook", "tier", "owner"} <= labels.keys()


def test_burn_rate_alerts_cover_every_window(catalog_bundle):
    _, _, burn_rates = catalog_bundle
    rules = yaml.safe_load(generate.render_rules(*catalog_bundle))
    alerts = {
        rule["alert"]: rule
        for group in rules["groups"]
        for rule in group["rules"]
        if "alert" in rule
    }
    for burn in burn_rates:
        for kind in ("Error", "Latency"):
            name = f"CriticalApi{kind}BudgetBurn{burn.alert_suffix}"
            assert name in alerts, f"missing {name}"
            alert = alerts[name]
            assert alert["labels"]["severity"] == burn.severity
            assert burn.long_window in alert["expr"]
            assert burn.short_window in alert["expr"]
            assert "runbook_url" in alert["annotations"]


def test_no_traffic_alert_only_covers_endpoints_expecting_traffic(catalog_bundle):
    rules = yaml.safe_load(generate.render_rules(*catalog_bundle))
    alerts = [
        rule
        for group in rules["groups"]
        for rule in group["rules"]
        if rule.get("alert") == "CriticalApiNoTraffic"
    ]
    assert len(alerts) == 1
    assert "slo:api_endpoint:expect_traffic" in alerts[0]["expr"]


def test_every_backend_owning_an_endpoint_has_a_health_probe(catalog_bundle):
    catalog, endpoints, _ = catalog_bundle
    targets = yaml.safe_load(generate.render_probe_targets(catalog, endpoints))
    probed_backends = {t["labels"]["backend"] for t in targets}
    assert {e.service for e in endpoints} <= probed_backends
    for target in targets:
        assert target["labels"]["__param_module"] in generate.PROBE_MODULES.values()
        # A credential-free probe of a protected route is answered by the
        # gateway's JWT middleware, so probes must hit /health directly.
        assert target["targets"][0].endswith("/health")


def test_error_ratio_is_zero_for_endpoints_with_no_error_series(catalog_bundle):
    """Otherwise a healthy endpoint reads as "no data" until it first 5xxes."""
    rules = yaml.safe_load(generate.render_rules(*catalog_bundle))
    ratios = [
        rule
        for group in rules["groups"]
        for rule in group["rules"]
        if str(rule.get("record", "")).startswith("slo:api_request_errors:ratio_rate")
    ]
    assert ratios
    for rule in ratios:
        assert "or\n    0 * sum by (backend, method, route)" in rule["expr"]


def test_slow_probe_warning_must_be_below_the_module_timeout(tmp_path):
    data = _catalog_dict()
    timeouts = generate._module_timeouts({"http_2xx"})
    data["probe"]["max_duration_seconds"] = timeouts["http_2xx"]
    with pytest.raises(generate.CatalogError, match="module timeout"):
        _write_and_load(tmp_path, data)


@pytest.mark.parametrize(
    ("duration", "seconds"),
    [
        ("1500ms", 1.5),
        ("5s", 5.0),
        ("2m", 120.0),
        ("1h", 3600.0),
        ("1m30s", 90.0),
        ("1.5s", 1.5),
        (".5s", 0.5),
        ("500us", 0.0005),
        ("1ns", 1e-9),
    ],
)
def test_module_timeouts_accept_every_go_duration_unit(duration, seconds):
    assert generate._parse_duration("http_2xx", duration) == seconds


@pytest.mark.parametrize("duration", ["5 seconds", "5", "1d", "2w"])
def test_module_timeouts_blackbox_cannot_parse_are_rejected(duration):
    with pytest.raises(generate.CatalogError, match="module timeout"):
        generate._parse_duration("http_2xx", duration)


def test_slow_probe_alert_ignores_failed_probes(catalog_bundle):
    """A timed-out probe is a failure, and CriticalApiProbeFailing owns it."""
    rules = yaml.safe_load(generate.render_rules(*catalog_bundle))
    slow = next(
        rule
        for group in rules["groups"]
        for rule in group["rules"]
        if rule.get("alert") == "CriticalApiProbeSlow"
    )
    assert "and on (instance)" in slow["expr"]
    assert "probe_success" in slow["expr"]


def test_every_alert_names_the_service_the_webhook_keys_on(catalog_bundle):
    """admin-service drops an alert that has neither affected_service nor service."""
    rules = yaml.safe_load(generate.render_rules(*catalog_bundle))
    alerts = [
        rule for group in rules["groups"] for rule in group["rules"] if "alert" in rule
    ]
    assert alerts
    for alert in alerts:
        assert alert["labels"]["affected_service"] == "{{ $labels.backend }}"


def test_endpoint_level_probes_are_rejected(tmp_path):
    data = _catalog_dict()
    data["endpoints"][0]["probe"] = {"path": "/api/v1/documents", "expect_status": [200, 401]}
    with pytest.raises(generate.CatalogError, match="health_probes"):
        _write_and_load(tmp_path, data)


def test_health_probes_must_target_health_endpoints(tmp_path):
    data = _catalog_dict()
    data["health_probes"][0]["url"] = "http://api-gateway:8080/api/v1/documents"
    with pytest.raises(generate.CatalogError, match="/health"):
        _write_and_load(tmp_path, data)


def test_gateway_route_table_is_derived_from_the_catalog(catalog_bundle):
    _, endpoints, _ = catalog_bundle
    rendered = generate.render_routes_go(endpoints)
    for endpoint in endpoints:
        assert f'template: "{endpoint.route}"' in rendered
        assert f'method: "{endpoint.method}"' in rendered


def _catalog_dict() -> dict:
    return yaml.safe_load(generate.CATALOG_PATH.read_text())


def _write_and_load(tmp_path: Path, data: dict):
    path = tmp_path / "catalog.yaml"
    path.write_text(yaml.safe_dump(data))
    return generate.load_catalog(path)


def test_latency_threshold_must_be_a_histogram_bucket(tmp_path):
    data = _catalog_dict()
    data["endpoints"][0]["latency"]["threshold"] = 0.37
    with pytest.raises(generate.CatalogError, match="histogram bucket"):
        _write_and_load(tmp_path, data)


def test_duplicate_endpoints_are_rejected(tmp_path):
    data = _catalog_dict()
    duplicate = copy.deepcopy(data["endpoints"][0])
    duplicate["id"] = f"{duplicate['id']}_copy"
    data["endpoints"].append(duplicate)
    with pytest.raises(generate.CatalogError, match="duplicate endpoint"):
        _write_and_load(tmp_path, data)


def test_conflicting_latency_thresholds_on_one_route_are_rejected(tmp_path):
    data = _catalog_dict()
    first = data["endpoints"][0]
    clone = copy.deepcopy(first)
    clone["id"] = f"{first['id']}_other_method"
    clone["method"] = "PATCH"
    clone["latency"]["threshold"] = 5
    data["endpoints"].append(clone)
    with pytest.raises(generate.CatalogError, match="conflicting latency thresholds"):
        _write_and_load(tmp_path, data)


def test_missing_runbook_is_rejected(tmp_path):
    data = _catalog_dict()
    data["endpoints"][0]["runbook"] = "does-not-exist"
    with pytest.raises(generate.CatalogError, match="runbook"):
        _write_and_load(tmp_path, data)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
