from __future__ import annotations

import os
import subprocess

import psycopg


_TARGET_SCHEMA = "ow_" + "billing"
TABLES = {
    "CODES": (f"{_TARGET_SCHEMA}.codes", ["code_type", "code_val", "code_desc"]),
    "PLANS": (
        f"{_TARGET_SCHEMA}.plans",
        ["id", "code", "tier_cd", "monthly_fee", "included_units", "overage_rate", "active_yn"],
    ),
    "TENANTS": (f"{_TARGET_SCHEMA}.tenants", ["id", "name", "tax_exempt_yn", "status_cd"]),
    "BILLING_AUDIT_LOG": (
        f"{_TARGET_SCHEMA}.billing_audit_log",
        ["log_id", "logged_at", "module", "message"],
    ),
}


def load_lakebase(dsn: str, rows: dict[str, list[tuple]]) -> dict[str, int]:
    with psycopg.connect(dsn) as conn:
        for name, (table, columns) in TABLES.items():
            conn.execute(f"TRUNCATE TABLE {table}")
            placeholders = ", ".join(["%s"] * len(columns))
            conn.executemany(
                f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
                rows[name],
            )
        sequence = f"{_TARGET_SCHEMA}.seq_" + "billing_audit_log"
        conn.execute(
            f"SELECT setval('{sequence}', "
            f"coalesce((SELECT max(log_id) FROM {TABLES['BILLING_AUDIT_LOG'][0]}), 0) + 1, false)"
        )
        counts = {
            name: int(conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
            for name, (table, _columns) in TABLES.items()
        }
        conn.commit()
    return counts


def ensure_delta_tables() -> None:
    statements = [
        "CREATE SCHEMA IF NOT EXISTS ow_tp.silver",
        "CREATE SCHEMA IF NOT EXISTS ow_tp.ops",
        """CREATE TABLE IF NOT EXISTS ow_tp.silver.codes (
             code_type STRING, code_val SMALLINT, code_desc STRING,
             scn_pin BIGINT, loaded_at TIMESTAMP
           ) USING DELTA""",
        """CREATE TABLE IF NOT EXISTS ow_tp.silver.plans (
             id STRING, code STRING, tier_cd SMALLINT, monthly_fee DECIMAL(12,2),
             included_units BIGINT, overage_rate DECIMAL(12,6), active_yn STRING,
             scn_pin BIGINT, loaded_at TIMESTAMP
           ) USING DELTA""",
        """CREATE TABLE IF NOT EXISTS ow_tp.silver.tenants (
             id STRING, name STRING, tax_exempt_yn STRING, status_cd SMALLINT,
             scn_pin BIGINT, loaded_at TIMESTAMP
           ) USING DELTA""",
        """CREATE TABLE IF NOT EXISTS ow_tp.ops.p1_recon_runs (
             run_id STRING, unit STRING, mode STRING, verdict STRING,
             merge_eligible BOOLEAN, scn_pin BIGINT, lakebase_branch STRING,
             started_at TIMESTAMP, finished_at TIMESTAMP, cost STRING,
             result_path STRING, recorded_at TIMESTAMP
           ) USING DELTA""",
    ]
    for sql in statements:
        env = os.environ.copy()
        env.pop("DATABRICKS_TOKEN", None)
        env.pop("DATABRICKS_DEMO_TOKEN", None)
        env["DATABRICKS_HOST"] = os.environ["DATABRICKS_DEMO_HOST"]
        subprocess.run(
            ["databricks", "experimental", "aitools", "tools", "query", sql],
            check=True,
            env=env,
            stdout=subprocess.DEVNULL,
        )
