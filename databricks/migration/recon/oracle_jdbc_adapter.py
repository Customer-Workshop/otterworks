"""Oracle source adapter for the reconciliation harness, used over JDBC from the Devin CIDRs.

D10-01 (opening 1521 to the Databricks serverless NAT range) was DENIED, so there is no
Lakehouse Federation and `dbx-recon --family oracle` stays refused: its Oracle adapter is
untested and the CLI says so before it reads a single input file. The owner directed the
JDBC route instead, accepting the consequence in writing.

This module is that route, and it is deliberately the smallest possible piece of it: the
harness's own `_SqlAdapterBase` does every comparison, so all tier logic, canonicalisation and
tolerance arithmetic stay the harness's. Only the connector and the Oracle dialect strings
below live here, and they are outside the harness's tested matrix.

Every verdict produced through this adapter is DEGRADED and is not an official harness
verdict. `run_degraded_recon.py` is the only supported entrypoint; it stamps the result.
"""

from __future__ import annotations

import json
import os
from typing import Any

from recon.adapters import SchemaFacts, _SqlAdapterBase, _split_table

ORACLE_NUMERIC_TYPES = ("NUMBER", "FLOAT", "BINARY_FLOAT", "BINARY_DOUBLE")


def _dsn_from_env(name: str) -> dict[str, Any]:
    """Connection parts from the env var NAME (never a literal on the command line).

    The value is the `ow-tp/oracle/ow_billing_ro` secret JSON as AWS Secrets Manager stores it:
    `user`, `password`, `host`, `port`, `service` (note `user`, not `username`).
    """
    raw = os.environ.get(name)
    if not raw:
        raise RuntimeError(f"secret '{name}' not found in environment; pass secrets by name only")
    try:
        parts = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(f"secret '{name}' is not the expected JSON object") from None
    missing = [k for k in ("user", "password", "host", "port", "service") if not parts.get(k)]
    if missing:
        raise RuntimeError(f"secret '{name}' is missing keys: {missing}")
    return parts


class OracleJdbcSourceAdapter(_SqlAdapterBase):
    """Read-only Oracle source over python-oracledb's thin driver.

    Not the harness's tested Oracle path. See the module docstring.
    """

    family = "oracle"
    official = False
    paramstyle = "named"
    max_params = 1000
    # A read-only transaction pins statement-level consistency for its whole duration, which is
    # the consistency window the harness records. Oracle has no session-scoped level to undo, so
    # the reset is a plain COMMIT.
    snapshot_sql = "SET TRANSACTION READ ONLY"
    snapshot_reset_sql = "COMMIT"
    # No per-table write counter is readable by a plain SELECT_CATALOG-less read-only user, so
    # the fallback window rests on the markers alone.
    change_token_sql = None
    # Left off deliberately: Oracle DATE arithmetic yields days as a NUMBER and TIMESTAMP
    # subtraction yields an INTERVAL, neither of which casts to whole microseconds without a
    # rounding choice this adapter has no right to make. Without it the harness streams the
    # ranges instead of digesting them: slower, never wrong.
    datetime_digest_sql = None
    # `literal()` renders `'YYYY-MM-DD HH:MM:SS.ffffff'`; typing the bound keeps the comparison
    # at microsecond precision instead of letting Oracle convert it to the column's type first.
    datetime_bound_sql = "TO_TIMESTAMP({lit}, 'YYYY-MM-DD HH24:MI:SS.FF6')"

    def __init__(self, dsn_secret: str):
        import oracledb  # lazy: optional extra

        parts = _dsn_from_env(dsn_secret)
        conn = oracledb.connect(
            user=parts["user"], password=parts["password"],
            dsn=f"{parts['host']}:{parts['port']}/{parts['service']}")
        super().__init__(conn)

    def _catalog_rows(self, table: str, predicate: str) -> set[str]:
        owner, name = _split_table(table, os.environ.get("OW_TP_ORACLE_SCHEMA", "OW_BILLING"))
        rows = self._rows(
            "SELECT column_name FROM all_tab_columns "
            f"WHERE owner = :1 AND table_name = :2 AND ({predicate})",
            {"1": owner.upper(), "2": name.upper()})
        return {col for (col,) in rows}

    def numeric_columns(self, table: str) -> set[str]:
        types = ", ".join(f"'{t}'" for t in ORACLE_NUMERIC_TYPES)
        return self._catalog_rows(table, f"data_type IN ({types})")

    def whole_number_columns(self, table: str) -> set[str]:
        # Only an exact NUMBER of declared scale 0 is whole. NUMBER with no precision holds
        # fractions, and the binary floats are never exact, so neither may digest a key.
        return self._catalog_rows(
            table, "data_type = 'NUMBER' AND data_scale = 0 AND data_precision IS NOT NULL")

    def schema_facts(self, table: str) -> SchemaFacts:
        raise NotImplementedError(
            "OracleJdbcSourceAdapter reads no constraint metadata: tiers 5-7 are part of the "
            "degraded surface and are reported as unverified, not guessed")
