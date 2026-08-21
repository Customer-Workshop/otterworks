"""Oracle persistence for the extracted rules.

Only data access lives here: every statement is a plain read or write against the
existing ``COMMISSION_PAY`` tables, with no rule logic (no ordering precedence, no
validation, no rounding) — those belong to ``app.domain``. The schema is
unchanged; this service is another client of the same tables the package wrote to.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import oracledb

from app.domain import PolicyRow, RateRow, SplitRow
from app.numbers import number

# The package used NVL(agent_id, -1) to make "the product default" a comparable
# scope key; agent ids are positive, so -1 can never collide with a real one.
DEFAULT_SCOPE = -1


def _scope(agent_id: int | None) -> int:
    return DEFAULT_SCOPE if agent_id is None else agent_id


class OracleCommissionRepository:
    def __init__(self, connection: oracledb.Connection) -> None:
        self.connection = connection

    def _cursor(self) -> oracledb.Cursor:
        cursor = self.connection.cursor()
        # Oracle NUMBER must arrive as an exact decimal, never as a float.
        cursor.outputtypehandler = decimal_output_handler
        return cursor

    def product_exists(self, product_code: str) -> bool:
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM products WHERE product_code = :product_code",
                product_code=product_code,
            )
            return cursor.fetchone()[0] > 0

    def agent_status(self, agent_id: int) -> str | None:
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT status FROM agents WHERE agent_id = :agent_id", agent_id=agent_id
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def amend_open_rate(
        self,
        product_code: str,
        agent_id: int | None,
        rate_pct: Decimal,
        effective_from: datetime,
        actor: str,
    ) -> int | None:
        with self._cursor() as cursor:
            returned = cursor.var(int, arraysize=1)
            cursor.execute(
                """
                UPDATE commission_rates
                   SET rate_pct = :rate_pct,
                       created_by = :actor
                 WHERE product_code = :product_code
                   AND NVL(agent_id, -1) = :agent_scope
                   AND effective_to IS NULL
                   AND effective_from = :effective_from
                RETURNING rate_id INTO :rate_id
                """,
                rate_pct=rate_pct,
                actor=actor,
                product_code=product_code,
                agent_scope=_scope(agent_id),
                effective_from=effective_from,
                rate_id=returned,
            )
            values = returned.getvalue()
            return int(values[0]) if values else None

    def close_earlier_open_rate(
        self,
        product_code: str,
        agent_id: int | None,
        effective_from: datetime,
        effective_to: datetime,
    ) -> int:
        with self._cursor() as cursor:
            cursor.execute(
                """
                UPDATE commission_rates
                   SET effective_to = :effective_to
                 WHERE product_code = :product_code
                   AND NVL(agent_id, -1) = :agent_scope
                   AND effective_to IS NULL
                   AND effective_from < :effective_from
                """,
                effective_to=effective_to,
                product_code=product_code,
                agent_scope=_scope(agent_id),
                effective_from=effective_from,
            )
            return cursor.rowcount

    def insert_rate(
        self,
        product_code: str,
        agent_id: int | None,
        rate_pct: Decimal,
        effective_from: datetime,
        actor: str,
    ) -> int:
        with self._cursor() as cursor:
            returned = cursor.var(int, arraysize=1)
            cursor.setinputsizes(agent_id=oracledb.DB_TYPE_NUMBER)
            cursor.execute(
                """
                INSERT INTO commission_rates
                    (product_code, agent_id, rate_pct, effective_from, effective_to, created_by)
                VALUES
                    (:product_code, :agent_id, :rate_pct, :effective_from, NULL, :actor)
                RETURNING rate_id INTO :rate_id
                """,
                product_code=product_code,
                agent_id=agent_id,
                rate_pct=rate_pct,
                effective_from=effective_from,
                actor=actor,
                rate_id=returned,
            )
            return int(returned.getvalue()[0])

    def close_open_rate(
        self, product_code: str, agent_id: int | None, effective_to: datetime
    ) -> int:
        with self._cursor() as cursor:
            cursor.execute(
                """
                UPDATE commission_rates
                   SET effective_to = :effective_to
                 WHERE product_code = :product_code
                   AND NVL(agent_id, -1) = :agent_scope
                   AND effective_to IS NULL
                """,
                effective_to=effective_to,
                product_code=product_code,
                agent_scope=_scope(agent_id),
            )
            return cursor.rowcount

    def candidate_rates(
        self, product_code: str, agent_id: int | None, as_of: datetime
    ) -> list[RateRow]:
        with self._cursor() as cursor:
            cursor.setinputsizes(agent_id=oracledb.DB_TYPE_NUMBER)
            cursor.execute(
                """
                SELECT rate_id, agent_id, rate_pct, effective_from
                  FROM commission_rates
                 WHERE product_code = :product_code
                   AND (agent_id = :agent_id OR agent_id IS NULL)
                   AND effective_from <= :as_of
                   AND (effective_to IS NULL OR effective_to >= :as_of)
                """,
                product_code=product_code,
                agent_id=agent_id,
                as_of=as_of,
            )
            return [
                RateRow(
                    rate_id=int(row[0]),
                    agent_id=int(row[1]) if row[1] is not None else None,
                    rate_pct=number(row[2]),
                    effective_from=row[3],
                )
                for row in cursor
            ]

    def rate_pct(self, rate_id: int) -> Decimal:
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT rate_pct FROM commission_rates WHERE rate_id = :rate_id", rate_id=rate_id
            )
            return number(cursor.fetchone()[0])

    def find_policy(self, policy_id: int) -> PolicyRow | None:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT policy_id, product_code, annual_premium, status
                  FROM policies WHERE policy_id = :policy_id
                """,
                policy_id=policy_id,
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return PolicyRow(
                policy_id=int(row[0]),
                product_code=row[1],
                annual_premium=number(row[2]),
                status=row[3],
            )

    def delete_splits(self, policy_id: int) -> None:
        with self._cursor() as cursor:
            cursor.execute(
                "DELETE FROM commission_splits WHERE policy_id = :policy_id", policy_id=policy_id
            )

    def insert_split(self, policy_id: int, agent_id: int, split_pct: Decimal) -> None:
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO commission_splits (policy_id, agent_id, split_pct)
                VALUES (:policy_id, :agent_id, :split_pct)
                """,
                policy_id=policy_id,
                agent_id=agent_id,
                split_pct=split_pct,
            )

    def policy_splits(self, policy_id: int) -> list[SplitRow]:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT agent_id, split_pct FROM commission_splits WHERE policy_id = :policy_id
                """,
                policy_id=policy_id,
            )
            return [SplitRow(agent_id=int(row[0]), split_pct=number(row[1])) for row in cursor]

    def delete_ledger(self, policy_id: int, period_month: str) -> None:
        with self._cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM commission_ledger
                 WHERE policy_id = :policy_id AND period_month = :period_month
                """,
                policy_id=policy_id,
                period_month=period_month,
            )

    def insert_ledger(
        self,
        policy_id: int,
        agent_id: int,
        period_month: str,
        rate_id: int,
        split_pct: Decimal,
        base_premium: Decimal,
        commission_amt: Decimal,
    ) -> None:
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO commission_ledger
                    (policy_id, agent_id, period_month, rate_id, split_pct,
                     base_premium, commission_amt)
                VALUES
                    (:policy_id, :agent_id, :period_month, :rate_id, :split_pct,
                     :base_premium, :commission_amt)
                """,
                policy_id=policy_id,
                agent_id=agent_id,
                period_month=period_month,
                rate_id=rate_id,
                split_pct=split_pct,
                base_premium=base_premium,
                commission_amt=commission_amt,
            )

    def log_action(
        self,
        action: str,
        product_code: str | None,
        agent_id: int | None,
        policy_id: int | None,
        detail: str,
        actor: str,
    ) -> None:
        with self._cursor() as cursor:
            cursor.setinputsizes(
                product_code=oracledb.DB_TYPE_VARCHAR,
                agent_id=oracledb.DB_TYPE_NUMBER,
                policy_id=oracledb.DB_TYPE_NUMBER,
            )
            cursor.execute(
                """
                INSERT INTO rate_audit_log
                    (action, product_code, agent_id, policy_id, detail, actor)
                VALUES (:action, :product_code, :agent_id, :policy_id, :detail, :actor)
                """,
                action=action,
                product_code=product_code,
                agent_id=agent_id,
                policy_id=policy_id,
                detail=detail,
                actor=actor,
            )


def decimal_output_handler(cursor: oracledb.Cursor, metadata: oracledb.FetchInfo):
    if metadata.type_code is oracledb.DB_TYPE_NUMBER:
        return cursor.var(Decimal, arraysize=cursor.arraysize)
    return None
