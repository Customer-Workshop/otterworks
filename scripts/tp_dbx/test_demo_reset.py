#!/usr/bin/env python3
"""Unit tests for demo_reset.plan — stdlib fakes only, no network."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import demo_reset  # noqa: E402

OPTS = demo_reset.Opts()


def inv(**kw):
    base = {"jobs": [], "pipelines": [], "dashboards": [],
            "schemas": [["ow_tp.bronze"], ["ow_tp.silver"], ["ow_tp.gold"], ["ow_tp.ops"]],
            "lakebase_branches": []}
    base.update(kw)
    return base


def kinds(plan, kind):
    return [(i.kind, i.name) for i in plan.items if i.kind == kind]


class PlanTest(unittest.TestCase):
    def test_showcase_recon_job_excluded(self):
        p = demo_reset.plan(inv(jobs=[
            {"job_id": 1, "settings": {"name": "ow_tp_billing_history_recon_demo"}},
            {"job_id": 2, "settings": {"name": "ow_tp_p1_nightly_dunning"}},
        ]), OPTS)
        self.assertEqual(kinds(p, "job"), [("job", "ow_tp_p1_nightly_dunning")])

    def test_billing_history_dashboard_excluded(self):
        p = demo_reset.plan(inv(dashboards=[
            {"dashboard_id": "a", "display_name": "ow_tp_billing_history_demo"},
            {"dashboard_id": "b", "display_name": "ow_tp Finance Gold"},
            {"dashboard_id": "c", "display_name": "navista_demo_consolidation"},
        ]), OPTS)
        self.assertEqual(kinds(p, "dashboard"), [("dashboard", "ow_tp Finance Gold")])

    def test_pipeline_dev_prefix_stripped(self):
        p = demo_reset.plan(inv(pipelines=[
            {"pipeline_id": "p1", "name": "[dev dhrov_spa] ow_tp_p2_custbill_ingest_parse"},
            {"pipeline_id": "p2", "name": "pond_otterorders_sales"},
        ]), OPTS)
        self.assertEqual(kinds(p, "pipeline"), [("pipeline", "[dev dhrov_spa] ow_tp_p2_custbill_ingest_parse")])

    def test_default_branch_matching_prefix_fails_loudly(self):
        p = demo_reset.plan(inv(lakebase_branches=[
            {"branch_id": "mig-prod", "status": {"default": True, "is_protected": False}},
            {"branch_id": "mig-p1-w0", "status": {"default": False, "is_protected": False}},
        ]), OPTS)
        self.assertEqual(kinds(p, "lakebase_branch"), [("lakebase_branch", "mig-p1-w0")])
        self.assertEqual(len(p.errors), 1)
        self.assertIn("mig-prod", p.errors[0])

    def test_protected_and_production_never_planned(self):
        p = demo_reset.plan(inv(lakebase_branches=[
            {"branch_id": "production", "status": {"default": True, "is_protected": False}},
            {"branch_id": "mig-locked", "status": {"default": False, "is_protected": True}},
            {"branch_id": "mig-ok", "status": {"default": False, "is_protected": False}},
            {"branch_id": "other-branch", "status": {"default": False, "is_protected": False}},
        ]), OPTS)
        self.assertEqual(kinds(p, "lakebase_branch"), [("lakebase_branch", "mig-ok")])
        # 'production' fails the prefix match entirely; only mig-locked errors loudly
        self.assertEqual(len(p.errors), 1)
        self.assertIn("mig-locked", p.errors[0])

    def test_children_before_parents(self):
        p = demo_reset.plan(inv(lakebase_branches=[
            {"branch_id": "mig-w0", "status": {"default": False},
             "source_branch": "projects/x/branches/production"},
            {"branch_id": "mig-w1", "status": {"default": False},
             "source_branch": "projects/x/branches/mig-w0"},
            {"branch_id": "mig-w2", "status": {"default": False},
             "source_branch": "projects/x/branches/mig-w1"},
        ]), OPTS)
        self.assertEqual([i.name for i in p.items if i.kind == "lakebase_branch"],
                         ["mig-w2", "mig-w1", "mig-w0"])

    def test_branch_order_fallback_reverse_create_time(self):
        p = demo_reset.plan(inv(lakebase_branches=[
            {"branch_id": "mig-old", "create_time": "2026-09-15T05:00:00Z",
             "status": {"default": False}},
            {"branch_id": "mig-new", "create_time": "2026-09-15T06:00:00Z",
             "status": {"default": False}},
        ]), OPTS)
        self.assertEqual([i.name for i in p.items if i.kind == "lakebase_branch"],
                         ["mig-new", "mig-old"])

    def test_run_scoped_schemas_planned_shared_never(self):
        p = demo_reset.plan(inv(schemas=[
            ["ow_tp.mig_x_bronze"], ["ow_tp.mig_x_gold"],
            ["ow_tp.bronze"], ["ow_tp.silver"],
            ["ow_tp.airbyte_demo"], ["ow_tp.information_schema"], ["ow_tp.default"],
        ]), OPTS)
        self.assertEqual([i.name for i in p.items],
                         ["ow_tp.mig_x_bronze", "ow_tp.mig_x_gold"])
        self.assertTrue(all(i.action.startswith("DROP SCHEMA") for i in p.items))

    def test_run_schemas_helper_short_names_and_verify_filter(self):
        # rows as short names (SHOW SCHEMAS shape) and full names both work;
        # the same helper drives inventory matching and verify() survivors
        rows = [["mig_r1_bronze"], ["bronze"], ["information_schema"],
                ["mig_r1_gold"], ["default"], ["migOTHERx"]]  # migOTHERx: no underscore boundary still matches prefix 'mig_'
        got = demo_reset._run_schemas(rows, OPTS)
        self.assertEqual(got, ["ow_tp.mig_r1_bronze", "ow_tp.mig_r1_gold"])
        # rows already fully qualified and scoped to another catalog are dropped
        got = demo_reset._run_schemas([["other_cat.mig_x"]], OPTS)
        self.assertEqual(got, [])


if __name__ == "__main__":
    unittest.main()
