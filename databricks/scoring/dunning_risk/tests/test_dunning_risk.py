"""Tests for the dunning-risk scoring layer.

These read the SQL as text and check the properties the design claims. They need no
warehouse and no credentials, so they run in CI and on a laptop:

    python3 -m pytest databricks/scoring/dunning_risk/tests

The one they exist for is test_every_rule_is_applied_and_every_applied_rule_exists. The whole
explainability argument rests on the printed rule table being the applied rule table; that
holds only while the rule_ids in 03_rules.sql and the CASE arms in 04/06 stay in step, and
nothing in SQL enforces it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"
LAKEBASE_DDL = (Path(__file__).resolve().parents[3]
                / "migration" / "lakebase" / "ow_tp_dunning_risk_score.sql")

RULES_SQL = (SQL_DIR / "03_rules.sql").read_text()
SCORE_INVOICE_SQL = (SQL_DIR / "04_score_invoice.sql").read_text()
SCORE_ACCOUNT_SQL = (SQL_DIR / "05_score_account.sql").read_text()
BACKTEST_SQL = (SQL_DIR / "06_backtest.sql").read_text()

# ('AGE_84_PLUS', 'invoice age', ... , 30, '...')
RULE_ROW = re.compile(
    r"\(\s*\d+,\s*'(?P<rule_id>[A-Z0-9_]+)',\s*'(?P<signal>[^']+)',\s*\n?"
    r"\s*'(?P<feature>[^']+)',\s*\n?\s*'(?P<condition>(?:[^']|'')*)',\s*(?P<points>-?\d+),",
    re.MULTILINE,
)

BANDS = [("LOW", 0, 19), ("MEDIUM", 20, 39), ("HIGH", 40, 59), ("CRITICAL", 60, 100)]


def code(path: Path) -> str:
    """The SQL with its comments removed.

    These files carry long rationale comments that name the very things the checks below
    forbid ("never a float", "does not touch dunning_attempts"). Scanning the raw text would
    fail on the explanation of the rule rather than on a breach of it.
    """
    return "\n".join(line.split("--")[0] for line in path.read_text().splitlines())


@pytest.fixture(scope="module")
def rules() -> dict[str, dict]:
    found = {m["rule_id"]: {"signal": m["signal"], "feature": m["feature"],
                            "condition": m["condition"], "points": int(m["points"])}
             for m in RULE_ROW.finditer(RULES_SQL)}
    assert found, "no rules parsed out of 03_rules.sql"
    return found


def test_rule_table_is_the_complete_model(rules):
    assert set(rules) == {
        "AGE_84_PLUS", "AGE_56_83", "AGE_28_55", "AGE_14_27",
        "PRIOR_OVERDUE_HIGH", "PRIOR_OVERDUE_MED",
        "SIZE_3X_NORM", "SIZE_1_5X_NORM",
        "EXPOSURE_OVER_LIMIT", "EXPOSURE_HALF_LIMIT",
        "CREDIT_HOLD", "VIP_SUPPRESS", "DUNNING_EXEMPT",
    }


def test_every_rule_is_applied_and_every_applied_rule_exists(rules):
    """The printed model and the applied model cannot be allowed to drift apart."""
    applied = set(re.findall(r"THEN '([A-Z0-9_]+)' END", SCORE_INVOICE_SQL))
    assert applied == set(rules)

    # the backtest deliberately drops the aging rules (days-since-issue is the outcome, not
    # a predictor) and the exempt suppressor, and nothing else
    backtested = set(re.findall(r"THEN '([A-Z0-9_]+)' END", BACKTEST_SQL))
    excluded = {r for r, v in rules.items() if v["signal"] == "invoice age"}
    assert backtested == set(rules) - excluded - {"DUNNING_EXEMPT"}


def test_maximum_reachable_score_is_the_top_of_the_top_band(rules):
    """One best-scoring rule per signal, suppressors excluded."""
    by_signal: dict[str, list[int]] = {}
    for rule_id, rule in rules.items():
        if rule["signal"] == "suppressor":
            continue
        by_signal.setdefault(rule["signal"], []).append(rule["points"])
    assert sum(max(points) for points in by_signal.values()) == BANDS[-1][2]


def test_aging_bands_are_multiples_of_the_one_legacy_interval(rules):
    """pkg_dunning.sp_suspend_overdue is the only interval the legacy estate declares."""
    lower_bounds = sorted(
        int(re.search(r"age_days (?:>=|BETWEEN) (\d+)", rules[r]["condition"]).group(1))
        for r in rules if rules[r]["signal"] == "invoice age"
    )
    assert lower_bounds == [14, 28, 56, 84]
    assert all(bound % 14 == 0 for bound in lower_bounds)


def test_aging_bands_do_not_overlap_or_leave_a_gap(rules):
    ranges = []
    for rule_id, rule in rules.items():
        if rule["signal"] != "invoice age":
            continue
        between = re.search(r"age_days BETWEEN (\d+) AND (\d+)", rule["condition"])
        if between:
            ranges.append((int(between.group(1)), int(between.group(2))))
        else:
            ranges.append((int(re.search(r">= (\d+)", rule["condition"]).group(1)), None))
    ranges.sort()
    for (_, high), (next_low, _) in zip(ranges, ranges[1:]):
        assert high is not None and next_low == high + 1


def test_suppressors_never_add_points(rules):
    for rule_id, rule in rules.items():
        if rule["signal"] == "suppressor":
            assert rule["points"] <= 0, rule_id


def test_bands_partition_the_whole_score_range():
    assert BANDS[0][1] == 0 and BANDS[-1][2] == 100
    for (_, _, high), (_, next_low, _) in zip(BANDS, BANDS[1:]):
        assert next_low == high + 1
    for name, low, _ in BANDS[1:]:
        assert f">= {low} THEN '{name}'" in SCORE_INVOICE_SQL


def test_score_is_clamped_into_the_band_range():
    assert "greatest(0, least(100," in SCORE_INVOICE_SQL
    assert "greatest(0, least(100," in BACKTEST_SQL


def test_exempt_accounts_are_forced_to_zero_and_their_own_band():
    assert "array_contains(f.reason_codes, 'DUNNING_EXEMPT') THEN 0" in SCORE_INVOICE_SQL
    assert "array_contains(f.reason_codes, 'DUNNING_EXEMPT') THEN 'EXEMPT'" in SCORE_INVOICE_SQL
    assert "any_exempt = 1       THEN 'EXEMPT'" in SCORE_ACCOUNT_SQL


def test_accounts_with_no_open_invoice_are_distinguishable_from_unscored():
    assert "'NO_OPEN_ITEMS'" in SCORE_ACCOUNT_SQL


@pytest.mark.parametrize("path", sorted(SQL_DIR.glob("*.sql")))
def test_sql_only_writes_inside_the_ow_tp_namespace(path: Path):
    created = re.findall(r"CREATE OR REPLACE TABLE\s+(\S+)", path.read_text())
    assert created, path.name
    for table in created:
        assert table.startswith("ow_tp.silver.dunning_risk_") \
            or table.startswith("ow_tp.gold.dunning_risk_"), table


@pytest.mark.parametrize("path", sorted(SQL_DIR.glob("*.sql")))
def test_sql_never_mutates_a_table_it_does_not_own(path: Path):
    """No drop, alter, insert, update or delete against anything, shared or otherwise."""
    text = code(path).upper()
    for verb in ("DROP TABLE", "ALTER TABLE", "INSERT INTO", "UPDATE ", "DELETE FROM"):
        assert verb not in text, f"{path.name} contains {verb.strip()}"


@pytest.mark.parametrize("path", sorted(SQL_DIR.glob("*.sql")))
def test_sql_takes_no_collections_action(path: Path):
    """The score is an input. Nothing here schedules, sends, skips or suspends."""
    text = code(path)
    for table in ("dunning_attempts", "notifications", "subscriptions", "tenants"):
        assert f"billing.{table}" not in text, f"{path.name} touches {table}"


@pytest.mark.parametrize("path", sorted(SQL_DIR.glob("*.sql")))
def test_money_is_never_a_float(path: Path):
    text = code(path).upper()
    for bad in ("AS FLOAT", "AS DOUBLE", "AS REAL"):
        assert bad not in text, f"{path.name} casts to {bad}"


def test_lakebase_ddl_is_rerunnable():
    text = code(LAKEBASE_DDL)
    assert re.findall(r"CREATE TABLE\s+(?!IF NOT EXISTS)", text) == []
    assert re.findall(r"CREATE INDEX\s+(?!IF NOT EXISTS)", text) == []
    for verb in ("DROP TABLE", "TRUNCATE"):
        assert verb not in text.upper(), f"the DDL must create structure only, not touch rows"


def test_lakebase_timestamps_are_zoneless():
    """Oracle DATE carries a time part and Oracle TIMESTAMP is zoneless (pipeline 1)."""
    text = code(LAKEBASE_DDL).lower()
    assert "timestamptz" not in text
    assert "with time zone" not in text
    assert "timestamp" in text


def test_lakebase_money_is_numeric():
    text = code(LAKEBASE_DDL).lower()
    for bad in (" float", " double precision", " real,"):
        assert bad not in text, f"the DDL uses {bad.strip()} for a value column"
    assert "numeric(14, 2)" in text


def test_lakebase_score_range_is_enforced_by_a_constraint():
    text = code(LAKEBASE_DDL)
    assert "CHECK (risk_score BETWEEN 0 AND 100)" in text
    assert "risk_band IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL', 'EXEMPT')" in text


def test_publish_reads_whole_results_from_one_pinned_snapshot():
    text = code(Path(__file__).resolve().parents[1] / "sync_to_lakebase.py")
    # a result over one chunk must be walked to the end and checked against the manifest,
    # or the queue publishes as a silent prefix
    assert "next_chunk_internal_link" in text
    assert "total_row_count" in text
    # and all three tables must come from the versions seen at one instant
    assert "VERSION AS OF" in text
    assert "_table_versions" in text


@pytest.mark.parametrize(
    "path",
    sorted(SQL_DIR.glob("*.sql"))
    + [LAKEBASE_DDL,
       Path(__file__).resolve().parents[1] / "sync_to_lakebase.py",
       Path(__file__).resolve().parents[1] / "deploy_job.py"],
)
def test_no_credential_values_are_committed(path: Path):
    text = path.read_text()
    assert "dapi" not in text
    assert not re.search(r"(password|secret|token)\s*=\s*['\"][^'\"]{8,}", text, re.I)


def test_job_is_deployed_paused_with_retries_and_dependencies():
    from importlib import util

    spec = util.spec_from_file_location(
        "deploy_job", Path(__file__).resolve().parents[1] / "deploy_job.py")
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)

    settings = module.job_settings({k: f"<{k}>" for k, _, _, _ in module.TASKS})
    assert settings["schedule"]["pause_status"] == "PAUSED"
    assert settings["name"] == "ow_tp_dunning_risk"

    tasks = {t["task_key"]: t for t in settings["tasks"]}
    assert tasks["score_invoice"]["depends_on"] == [{"task_key": "features_invoice"},
                                                    {"task_key": "rules"}]
    assert tasks["score_account"]["depends_on"] == [{"task_key": "features_account"},
                                                    {"task_key": "score_invoice"}]
    for task in tasks.values():
        assert task["max_retries"] == 2
        assert task["min_retry_interval_millis"] == 60_000
        # no new clusters: every task runs on the existing serverless warehouse
        assert task["sql_task"]["warehouse_id"] == "565cd2fd713738c4"
        assert "new_cluster" not in task and "job_cluster_key" not in task


def test_every_sql_file_is_a_job_task():
    from importlib import util

    spec = util.spec_from_file_location(
        "deploy_job", Path(__file__).resolve().parents[1] / "deploy_job.py")
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert {f for _, f, _, _ in module.TASKS} == {p.name for p in SQL_DIR.glob("*.sql")}
