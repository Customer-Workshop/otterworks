"""Offline guards for the customers loader's preflight and counter seeding.

These cover the two ways the load can destroy data rather than merely get it wrong: clearing
the target for an empty source, and re-seeding the Atlas counter below numbers it has already
issued. Both run against fakes — no Oracle, no Atlas.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from customers_load import (
    assert_designated_cluster,
    assert_source_slice,
    load,
    seed_counter,
)

# Resolved from the repo root so the suite runs from anywhere.
CONVENTIONS = Path(__file__).resolve().parents[2] / ".migration" / "01_conventions.md"

MAPPED = {"CUST_ID", "CUST_NO", "CUR_BAL_AMT"}
CATALOG = [("CUST_ID",), ("CUST_NO",), ("CUR_BAL_AMT",), ("LEGACY_FAX_NO",)]


class FakeCursor:
    """Answers the three preflight queries in the order the loader issues them."""

    def __init__(self, root_count, retired_counts):
        self._root_count = root_count
        self._retired_counts = retired_counts
        self._rows = []
        self._result = None

    def execute(self, sql, **_):
        if sql.startswith("SELECT COUNT(*)"):
            self._result = (self._root_count,)
        elif "all_tab_columns" in sql:
            self._rows = list(CATALOG)
        elif "all_sequences" in sql:
            self._result = (125000,)
        else:
            self._result = self._retired_counts

    def fetchone(self):
        return self._result

    def __iter__(self):
        return iter(self._rows)


class FakeCounters:
    """Just enough of a collection to exercise `$max` + `$setOnInsert` upsert semantics."""

    def __init__(self, existing=None):
        self.doc = existing

    def find_one_and_update(self, filt, update, upsert=False, return_document=None):
        if self.doc is None:
            self.doc = dict(filt)
            self.doc.update(update["$setOnInsert"])
            self.doc["seq"] = update["$max"]["seq"]
        else:
            self.doc["seq"] = max(self.doc["seq"], update["$max"]["seq"])
        return self.doc


def test_preflight_accepts_a_populated_batch_with_retired_columns_still_null():
    assert assert_source_slice(FakeCursor(25000, (0,)), 85559852, MAPPED) == 25000


def test_preflight_refuses_an_empty_batch_before_touching_the_target():
    with pytest.raises(SystemExit, match="no rows for CONVERSION_BATCH_NO"):
        assert_source_slice(FakeCursor(0, (0,)), 85559852, MAPPED)


def test_preflight_refuses_a_retired_column_that_now_holds_data():
    with pytest.raises(SystemExit, match="LEGACY_FAX_NO"):
        assert_source_slice(FakeCursor(25000, (7,)), 85559852, MAPPED)


@pytest.mark.parametrize("target_db,quarantine_db", [
    ("ow_tp_billing_demo", "ow_tp_demo_quarantine"),
    ("ow_tp_demo", "ow_tp_mongodb_demo_quarantine"),
])
def test_a_database_outside_the_conventions_record_is_refused(target_db, quarantine_db):
    with pytest.raises(SystemExit, match="not the database designated"):
        load("demo", "OW_BILLING_SOURCE_DSN", "MONGODB_ATLAS_URI", target_db, quarantine_db,
             conventions_path=CONVENTIONS)


def test_a_uri_secret_the_conventions_record_does_not_name_is_refused():
    with pytest.raises(SystemExit, match="not the secret NAME designated"):
        assert_designated_cluster(CONVENTIONS, "SOME_OTHER_URI")


def test_a_connection_string_for_another_cluster_is_refused(monkeypatch):
    monkeypatch.setenv("MONGODB_ATLAS_URI", "mongodb+srv://u:p@someone-else.abcde.mongodb.net/")
    with pytest.raises(SystemExit, match="other than the designated"):
        assert_designated_cluster(CONVENTIONS, "MONGODB_ATLAS_URI")


def test_the_designated_cluster_is_accepted(monkeypatch):
    monkeypatch.setenv("MONGODB_ATLAS_URI",
                       "mongodb+srv://u:p@otterworks-demo.cgbijgv.mongodb.net/?retryWrites=true")
    assert_designated_cluster(CONVENTIONS, "MONGODB_ATLAS_URI")


@pytest.mark.parametrize("ns", ["", "demo/../prod", "Demo Namespace", "d" * 33])
def test_a_malformed_namespace_is_rejected_before_anything_is_opened(ns):
    with pytest.raises(SystemExit, match="not of the form"):
        load(ns, "OW_BILLING_SOURCE_DSN", "MONGODB_ATLAS_URI", "ow_tp_demo",
             "ow_tp_demo_quarantine", conventions_path=CONVENTIONS)


def test_counter_seeds_from_the_sequence_on_a_first_run():
    counters = FakeCounters()
    assert seed_counter({"counters": counters}, FakeCursor(1, ()), "demo") == 125000
    assert counters.doc["ns"] == "demo"


def test_counter_is_not_lowered_by_a_reload_after_atlas_issued_numbers():
    counters = FakeCounters({"_id": "demo:customers.cust_seq_no", "ns": "demo",
                             "unit": "customers", "seq": 125042})
    assert seed_counter({"counters": counters}, FakeCursor(1, ()), "demo") == 125042
