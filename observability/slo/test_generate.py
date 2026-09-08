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


def test_probe_targets_only_include_probed_endpoints(catalog_bundle):
    catalog, endpoints, _ = catalog_bundle
    targets = yaml.safe_load(generate.render_probe_targets(catalog, endpoints))
    probed = {e.id for e in endpoints if e.probe}
    endpoint_targets = {
        t["labels"]["probe_id"] for t in targets if t["labels"]["probe_kind"] == "endpoint"
    }
    assert endpoint_targets == probed
    for target in targets:
        assert target["labels"]["__param_module"] in generate.PROBE_MODULES.values()


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
