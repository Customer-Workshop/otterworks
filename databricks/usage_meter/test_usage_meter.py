"""Tests for the usage meter: duplicates, late arrivals, empty input, rejects, reruns.

These run the real statements against throwaway tables inside `ow_tp` (suffix
`_selftest`) and a throwaway landing volume, using the existing serverless SQL
warehouse. Nothing here touches the production meter tables, the Pipeline 1
tables or Lakebase.

    python3 test_usage_meter.py
"""

from __future__ import annotations

import unittest
import uuid
from datetime import datetime

from executor import get_executor
from landing import write_batch
from meter_sql import Namespace
from pipeline import ensure_objects, ingest, meter, normalise

TEST = Namespace(
    raw="ow_tp.bronze.usage_meter_events_raw_selftest",
    events="ow_tp.silver.usage_meter_events_selftest",
    rejects="ow_tp.silver.usage_meter_rejects_selftest",
    meter="ow_tp.gold.usage_meter_period_selftest",
    watermark="ow_tp.gold.usage_meter_watermark_selftest",
    landing="/Volumes/ow_tp/bronze/usage_meter_landing_selftest",
)

TENANT = "selftest-tenant-0001"


def _clear_landing() -> None:
    """Batches from an earlier run would be read again once bronze is dropped."""
    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()
    for entry in w.files.list_directory_contents(TEST.landing):
        if not entry.is_directory:
            w.files.delete(entry.path)


def event(event_id: str, occurred_at: str, units: int, kind_cd: int = 1,
          tenant_id: str = TENANT) -> dict[str, str]:
    return {"event_id": event_id, "tenant_id": tenant_id, "occurred_at": occurred_at,
            "units": str(units), "kind_cd": str(kind_cd)}


class UsageMeterTest(unittest.TestCase):
    """One scenario, run in order: each step builds on the state of the last."""

    ex = None
    prefix = ""

    @classmethod
    def setUpClass(cls) -> None:
        cls.ex = get_executor()
        cls.prefix = uuid.uuid4().hex[:8]
        for table in TEST.all_tables():
            cls.ex.sql(f"DROP TABLE IF EXISTS {table}")
        ensure_objects(cls.ex, TEST)
        _clear_landing()

    def id_for(self, name: str) -> str:
        return f"{self.prefix}-{name}"

    def run_pipeline(self) -> dict[str, dict]:
        return {"ingest": ingest(self.ex, TEST),
                "normalise": normalise(self.ex, TEST),
                "meter": meter(self.ex, TEST)}

    def cell(self, period_start: str, metric: str = "api") -> dict:
        rows = self.ex.sql(
            f"SELECT event_count, units_total, late_event_count, avg_units_per_event "
            f"FROM {TEST.meter} WHERE tenant_id = '{TENANT}' AND metric = '{metric}' "
            f"AND period_start = DATE'{period_start}'")
        return rows[0] if rows else {}

    def digest(self) -> str:
        return str(self.ex.scalar(
            f"SELECT MD5(CONCAT_WS('|', SORT_ARRAY(COLLECT_LIST(CONCAT_WS(':', tenant_id, metric, "
            f"CAST(period_start AS STRING), CAST(event_count AS STRING), "
            f"CAST(units_total AS STRING)))))) FROM {TEST.meter}"))

    def test_01_first_batch_is_metered(self) -> None:
        write_batch([event(self.id_for("e1"), "2026-03-04 09:00:00", 10),
                     event(self.id_for("e2"), "2026-03-05 09:00:00", 20)], ns=TEST)
        stats = self.run_pipeline()
        self.assertEqual(stats["ingest"]["rows_landed"], 2)
        self.assertEqual(self.cell("2026-03-01"), {"event_count": 2, "units_total": 30,
                                                   "late_event_count": 2,
                                                   "avg_units_per_event": 15.0})

    def test_02_duplicate_event_does_not_double_count(self) -> None:
        # e1 arrives again with different units; first arrival must win.
        write_batch([event(self.id_for("e1"), "2026-03-04 09:00:00", 999),
                     event(self.id_for("e3"), "2026-03-06 09:00:00", 5)], ns=TEST)
        self.run_pipeline()
        cell = self.cell("2026-03-01")
        self.assertEqual(cell["event_count"], 3)
        self.assertEqual(cell["units_total"], 35)
        seen, units = self.ex.sql(
            f"SELECT seen_count, units FROM {TEST.events} "
            f"WHERE event_id = '{self.id_for('e1')}'")[0].values()
        self.assertEqual((seen, units), (2, 10))

    def test_03_late_event_lands_in_its_own_period(self) -> None:
        # February was never metered before; a backdated event must create it and
        # must not disturb March.
        write_batch([event(self.id_for("e4"), "2026-02-14 09:00:00", 7)], ns=TEST)
        self.run_pipeline()
        february = self.cell("2026-02-01")
        self.assertEqual((february["event_count"], february["units_total"]), (1, 7))
        self.assertEqual(february["late_event_count"], 1)
        self.assertTrue(self.ex.scalar(
            f"SELECT is_late FROM {TEST.events} WHERE event_id = '{self.id_for('e4')}'"))
        self.assertEqual(self.cell("2026-03-01")["units_total"], 35)

    def test_04_late_event_reopens_a_metered_period(self) -> None:
        write_batch([event(self.id_for("e5"), "2026-03-07 09:00:00", 4)], ns=TEST)
        self.run_pipeline()
        cell = self.cell("2026-03-01")
        self.assertEqual((cell["event_count"], cell["units_total"]), (4, 39))

    def test_05_unmeterable_rows_are_quarantined(self) -> None:
        write_batch([event(self.id_for("bad-tenant"), "2026-03-08 09:00:00", 3, tenant_id=""),
                     event(self.id_for("bad-units"), "2026-03-08 09:00:00", 0),
                     event(self.id_for("bad-kind"), "2026-03-08 09:00:00", 3, kind_cd=99)],
                    ns=TEST)
        self.run_pipeline()
        reasons = {r["reject_reason"] for r in self.ex.sql(
            f"SELECT DISTINCT reject_reason FROM {TEST.rejects}")}
        self.assertEqual(reasons, {"missing tenant attribution", "units must be > 0",
                                   "unknown usage kind"})
        self.assertEqual(self.cell("2026-03-01")["units_total"], 39)

    def test_06_rejected_copy_does_not_backdate_a_valid_event(self) -> None:
        # The bad copy shares the event id, so counting every bronze row with that id
        # would hand the valid event an arrival it never had.
        eid = self.id_for("e6")
        write_batch([event(eid, "2026-03-09 09:00:00", 0)], ns=TEST)
        self.run_pipeline()
        rejected_at = self.ex.scalar(
            f"SELECT MAX(ingested_at) FROM {TEST.rejects} WHERE event_id = '{eid}'")
        write_batch([event(eid, "2026-03-09 09:00:00", 6)], ns=TEST)
        self.run_pipeline()
        seen, first_seen_at = self.ex.sql(
            f"SELECT seen_count, first_seen_at FROM {TEST.events} "
            f"WHERE event_id = '{eid}'")[0].values()
        self.assertEqual(seen, 1)
        self.assertGreater(first_seen_at, rejected_at)
        self.assertEqual(self.cell("2026-03-01")["units_total"], 45)

    def test_07_stale_arrival_metadata_is_corrected(self) -> None:
        # Rows merged before the valid-only rule can hold a backdated first arrival,
        # and correcting `arrivals` alone would leave them that way.
        eid = self.id_for("e1")
        self.ex.sql(f"UPDATE {TEST.events} SET first_seen_at = '2020-01-01 00:00:00', "
                    f"arrival_lag_seconds = -1 WHERE event_id = '{eid}'")
        write_batch([event(eid, "2026-03-04 09:00:00", 10)], ns=TEST)
        self.run_pipeline()
        row = self.ex.sql(
            f"SELECT first_seen_at, arrival_lag_seconds, units FROM {TEST.events} "
            f"WHERE event_id = '{eid}'")[0]
        self.assertGreater(row["first_seen_at"], datetime(2026, 1, 1))
        self.assertEqual(
            row["arrival_lag_seconds"],
            int((row["first_seen_at"] - datetime(2026, 3, 4, 9, 0, 0)).total_seconds()))
        self.assertEqual(row["units"], 10)
        self.assertEqual(self.cell("2026-03-01")["units_total"], 45)

    def test_08_good_and_bad_copy_in_one_file(self) -> None:
        # One load stamps both copies with the same file and ingest time, so the
        # reject must be matched on its payload or the good copy vanishes with it.
        eid = self.id_for("e7")
        write_batch([event(eid, "2026-03-10 09:00:00", 0),
                     event(eid, "2026-03-10 09:00:00", 7)], ns=TEST)
        self.run_pipeline()
        self.assertEqual(
            self.ex.scalar(f"SELECT units FROM {TEST.events} WHERE event_id = '{eid}'"), 7)
        self.assertEqual(
            self.ex.scalar(f"SELECT reject_reason FROM {TEST.rejects} "
                           f"WHERE event_id = '{eid}'"), "units must be > 0")
        self.assertEqual(self.cell("2026-03-01")["units_total"], 52)

    def test_09_empty_input_changes_nothing(self) -> None:
        before = self.digest()
        stats = self.run_pipeline()
        self.assertEqual(stats["ingest"]["rows_landed"], 0)
        self.assertEqual(stats["normalise"]["rows_in"], 0)
        self.assertEqual(stats["meter"]["rows_in"], 0)
        self.assertEqual(stats["meter"]["cells_written"], 0)
        self.assertEqual(self.digest(), before)

    def test_10_rerun_is_idempotent(self) -> None:
        before = self.digest()
        self.run_pipeline()
        self.run_pipeline()
        self.assertEqual(self.digest(), before)
        self.assertEqual(self.ex.scalar(f"SELECT COUNT(*) FROM {TEST.events}"), 7)


if __name__ == "__main__":
    unittest.main(verbosity=2)
