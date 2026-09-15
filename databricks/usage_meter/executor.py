"""One SQL entry point for the usage meter, wherever the code happens to run.

Inside a Lakeflow task the statements go through the task's Spark session; from a
laptop or CI they go to the existing serverless SQL warehouse over OAuth M2M. No
cluster is ever created, and credentials are read from the environment by name
(`DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET`) and never
logged.
"""

from __future__ import annotations

import os
from typing import Any

WAREHOUSE_ID = "565cd2fd713738c4"


class Executor:
    """Runs a statement and returns its rows as dictionaries."""

    def sql(self, statement: str) -> list[dict[str, Any]]:  # pragma: no cover - interface
        raise NotImplementedError

    def one(self, statement: str) -> dict[str, Any] | None:
        rows = self.sql(statement)
        return rows[0] if rows else None

    def scalar(self, statement: str) -> Any:
        row = self.one(statement)
        return None if row is None else next(iter(row.values()))


class SparkExecutor(Executor):
    def __init__(self, spark: Any) -> None:
        self._spark = spark

    def sql(self, statement: str) -> list[dict[str, Any]]:
        df = self._spark.sql(statement)
        if not df.columns:
            return []
        return [row.asDict() for row in df.collect()]


class WarehouseExecutor(Executor):
    def __init__(self, warehouse_id: str = WAREHOUSE_ID) -> None:
        from databricks import sql as dbsql
        from databricks.sdk.core import Config, oauth_service_principal

        host = os.environ["DATABRICKS_HOST"]
        cfg = Config(host=host,
                     client_id=os.environ["DATABRICKS_CLIENT_ID"],
                     client_secret=os.environ["DATABRICKS_CLIENT_SECRET"])
        self._conn = dbsql.connect(
            server_hostname=host.replace("https://", "").rstrip("/"),
            http_path=f"/sql/1.0/warehouses/{warehouse_id}",
            credentials_provider=lambda: oauth_service_principal(cfg),
        )

    def sql(self, statement: str) -> list[dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute(statement)
            if cur.description is None:
                return []
            names = [c[0] for c in cur.description]
            return [dict(zip(names, row)) for row in cur.fetchall()]


def get_executor() -> Executor:
    """Spark when a session is available (job task), the warehouse otherwise."""
    try:
        from pyspark.sql import SparkSession
    except ImportError:
        return WarehouseExecutor()
    active = SparkSession.getActiveSession()
    if active is not None:
        return SparkExecutor(active)
    try:
        return SparkExecutor(SparkSession.builder.getOrCreate())
    except Exception:
        return WarehouseExecutor()


def run_id() -> str:
    """Job run id when running as a task, a local marker otherwise."""
    return os.environ.get("DATABRICKS_JOB_RUN_ID") or os.environ.get("DB_JOB_RUN_ID") or "local"
