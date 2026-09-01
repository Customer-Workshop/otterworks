"""Synthetic-estate tests: a small Oracle-shaped estate with an embed mapping, seeded with
one mismatch per class, proving each tier catches its class and the engine gates on Tier 1.
"""

import copy
import json
from pathlib import Path

from recon.config import (CanonRule, CollectionMapping, EmbedMapping, FieldMapping,
                          MappingSpec, Tolerances, load_canon_rules, load_mapping_spec,
                          load_tolerances)
from recon.engine import run_recon
from tests.fakes import FakeSource, FakeTarget

RULES = [CanonRule("rstrip_spaces", "*"), CanonRule("empty_string_is_null", "*"),
         CanonRule("null_missing_equiv", "*"), CanonRule("identity", "*")]

SPEC = MappingSpec(version="map-v1", collections=[CollectionMapping(
    collection="orders", root_table="ORDERS",
    key_source=["ORDER_ID"], key_target="order_id",
    fields=[
        FieldMapping("ORDER_ID", "order_id", "NUMBER(18,0)", "long"),
        FieldMapping("CUST_NAME", "customer.name", "CHAR(20)", "string",
                     rules=["rstrip_spaces", "empty_string_is_null", "null_missing_equiv"]),
        FieldMapping("TOTAL", "total", "NUMBER(10,2)", "Decimal128"),
    ],
    embeds=[EmbedMapping(array_path="items", child_table="ORDER_ITEMS")],
)])

TOL = Tolerances(version="tol-v1", full_diff_row_threshold=100, sample_size=10)


def make_green():
    source = FakeSource({
        "ORDERS": [
            {"ORDER_ID": 1, "CUST_NAME": "Ada   ", "TOTAL": 10.5},
            {"ORDER_ID": 2, "CUST_NAME": "", "TOTAL": 20.0},
        ],
        "ORDER_ITEMS": [{"ORDER_ID": 1, "SKU": "a"}, {"ORDER_ID": 1, "SKU": "b"},
                        {"ORDER_ID": 2, "SKU": "c"}],
    })
    target = FakeTarget({
        "orders": [
            {"order_id": 1, "customer": {"name": "Ada"}, "total": 10.5,
             "items": [{"sku": "a"}, {"sku": "b"}]},
            {"order_id": 2, "customer": {}, "total": 20.0, "items": [{"sku": "c"}]},
        ],
    })
    return source, target


def run(source, target, mode="live"):
    return run_recon("orders-batch-1", mode, SPEC, TOL, RULES, source, target)


def test_green_estate_passes():
    result = run(*make_green())
    assert result["verdict"] == "PASS"
    assert [t["tier"] for t in result["tiers"]] == [1, 2, 3]
    assert result["mapping_version"] == "map-v1" and result["tolerance_version"] == "tol-v1"


def test_tier1_root_count_and_gate():
    source, target = make_green()
    target.collections["orders"] = target.collections["orders"][:1]
    result = run(source, target)
    assert result["verdict"] == "FAIL"
    assert len(result["tiers"]) == 1  # nothing else ran: Tier 1 gates
    assert any(f["check"] == "root_count" for f in result["tiers"][0]["findings"])


def test_tier1_embed_cardinality():
    source, target = make_green()
    target.collections["orders"][0]["items"].pop()
    result = run(source, target)
    checks = {f["check"] for f in result["tiers"][0]["findings"]}
    assert checks == {"embed_cardinality"}


def test_tier2_aggregate_mismatch():
    source, target = make_green()
    target.collections["orders"][0]["total"] = 999.0  # sum/min/max drift
    result = run(source, target)
    t2 = result["tiers"][1]
    assert not t2["passed"]
    assert any(f["check"].startswith("aggregate_") for f in t2["findings"])


def test_tier3_field_diff_reports_rule_evidence():
    source, target = make_green()
    target.collections["orders"][0]["customer"]["name"] = "Bob"
    result = run(source, target)
    t3 = result["tiers"][2]
    diffs = [f for f in t3["findings"] if f["check"] == "field_diff"]
    assert diffs and "rstrip_spaces" in diffs[0]["rules_applied"]


def test_tier3_missing_doc():
    source, target = make_green()
    source.tables["ORDERS"].append({"ORDER_ID": 3, "CUST_NAME": "Eve", "TOTAL": 1.0})
    source.tables["ORDER_ITEMS"].append({"ORDER_ID": 3, "SKU": "d"})
    result = run(source, target)
    assert result["verdict"] == "FAIL"  # tier 1 catches count; force tier 3 view too
    # add matching counts but wrong key to reach tier 3
    source, target = make_green()
    source.tables["ORDERS"][1] = {"ORDER_ID": 99, "CUST_NAME": "", "TOTAL": 20.0}
    result = run(source, target)
    t3 = result["tiers"][2]
    assert {f["check"] for f in t3["findings"]} >= {"missing_doc", "extra_doc"}


def test_tier3_sampling_above_threshold():
    source, target = make_green()
    tol = Tolerances(version="tol-v1", full_diff_row_threshold=1, sample_size=1)
    result = run_recon("u", "live", SPEC, tol, RULES, source, target)
    stats = result["tiers"][2]["stats"]["orders"]
    assert stats["mode"] == "stratified_sample" and 0 < stats["coverage"] <= 1


def test_tier4_parity():
    source, target = make_green()
    ops = [{"name": "top_customers", "collection": "orders", "rules": ["rstrip_spaces"]}]
    good = lambda op: [{"name": "Ada   "}]
    bad = lambda op: [{"name": "Zed"}]
    result = run_recon("u", "live", SPEC, TOL, RULES, source, target,
                       ops=ops, run_source=good, run_target=lambda op: [{"name": "Ada"}])
    assert result["verdict"] == "PASS" and len(result["tiers"]) == 4
    result = run_recon("u", "live", SPEC, TOL, RULES, source, target,
                       ops=ops, run_source=good, run_target=bad)
    assert result["tiers"][3]["findings"][0]["check"] == "parity_mismatch"


def test_continuous_mode_samples_tier3_and_skips_tier4():
    source, target = make_green()
    ops = [{"name": "x"}]
    result = run_recon("u", "continuous", SPEC, TOL, RULES, source, target,
                       ops=ops, run_source=lambda o: [], run_target=lambda o: [])
    assert [t["tier"] for t in result["tiers"]] == [1, 2, 3]
    assert result["tiers"][2]["stats"]["orders"]["mode"] == "stratified_sample"


def test_determinism():
    r1 = run(*make_green())
    r2 = run(*make_green())
    r1.pop("generated_at"); r2.pop("generated_at")
    assert r1 == r2


def test_config_loaders_and_report(tmp_path: Path):
    (tmp_path / "map.json").write_text(json.dumps({
        "version": "m1", "collections": [{
            "collection": "c", "root_table": "T",
            "key": {"source": ["ID"], "target": "id"},
            "fields": [{"source": "ID", "target": "id"}]}]}))
    (tmp_path / "tol.json").write_text(json.dumps({"version": "t1"}))
    (tmp_path / "rules.json").write_text(json.dumps([{"rule": "identity", "applies_to": "*"}]))
    spec = load_mapping_spec(tmp_path / "map.json")
    tol = load_tolerances(tmp_path / "tol.json")
    rules = load_canon_rules(tmp_path / "rules.json")
    source = FakeSource({"T": [{"ID": 1}]})
    target = FakeTarget({"c": [{"id": 1}]})
    result = run_recon("u", "snapshot", spec, tol, rules, source, target,
                       out_dir=tmp_path / "out")
    assert result["verdict"] == "PASS"
    assert (tmp_path / "out/result.json").exists()
    report = (tmp_path / "out/report.md").read_text()
    assert "snapshot" in report and "scoped to the snapshot watermark" in report


def test_unversioned_inputs_rejected(tmp_path: Path):
    import pytest
    from recon.config import ConfigError
    (tmp_path / "map.json").write_text(json.dumps({"collections": []}))
    with pytest.raises(ConfigError):
        load_mapping_spec(tmp_path / "map.json")


def test_missing_comparison_key_rejected(tmp_path: Path):
    import pytest
    from recon.config import ConfigError
    (tmp_path / "map.json").write_text(json.dumps({
        "version": "m1", "collections": [{"collection": "c", "root_table": "T", "fields": []}]}))
    with pytest.raises(ConfigError):
        load_mapping_spec(tmp_path / "map.json")

def test_tier2_skips_sum_when_source_has_no_numeric_sum():
    """A string column: SQL SUM() is NULL, MongoDB's $sum is 0 over the same values.

    Comparing them states nothing about the load, so Tier 2 must not raise a finding —
    the field's values are proved by Tier 3's keyed diff instead.
    """
    source, target = make_green()

    class MongoShapedTarget(FakeTarget):
        def field_aggregates(self, collection, field_path):
            agg = super().field_aggregates(collection, field_path)
            if agg["sum"] is None:
                agg["sum"] = 0  # what $sum answers over non-numeric input
            return agg

    result = run(source, MongoShapedTarget(target.collections))
    t2 = result["tiers"][1]
    assert t2["passed"], t2["findings"]
    assert "orders.customer.name" in t2["stats"]["sum_not_comparable"]
    assert result["verdict"] == "PASS"


def test_tier2_skips_sum_for_a_numeric_looking_string_column():
    """A string column of digits (a zip, an account number): SQL SUM() implicitly converts
    and answers a number, MongoDB's $sum answers 0 because the values are strings.

    The two sides state different facts about identical data, so Tier 2 must not raise a
    finding on a `string` field's sum — Tier 3's keyed diff proves the values instead.
    """
    source, target = make_green()
    for row, doc in zip(source.tables["ORDERS"], target.collections["orders"]):
        row["CUST_NAME"] = "90210"
        doc["customer"]["name"] = "90210"

    class MongoShapedTarget(FakeTarget):
        def field_aggregates(self, collection, field_path):
            agg = super().field_aggregates(collection, field_path)
            if field_path == "customer.name":
                agg["sum"] = 0  # $sum over strings
            return agg

    class OracleShapedSource(FakeSource):
        def field_aggregates(self, table, column, where=None):
            agg = super().field_aggregates(table, column, where)
            if column == "CUST_NAME":
                agg["sum"] = 180420  # SUM() after implicit string->number conversion
            return agg

    result = run(OracleShapedSource(source.tables), MongoShapedTarget(target.collections))
    t2 = result["tiers"][1]
    assert t2["passed"], t2["findings"]
    assert "orders.customer.name" in t2["stats"]["sum_not_comparable"]
    assert result["verdict"] == "PASS"
