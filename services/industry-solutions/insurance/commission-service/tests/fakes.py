"""An in-memory stand-in for the Oracle tables.

Lets the rule tests state a rule and its expected outcome without a database in
the loop. It stores what the tables store and nothing more: no ordering, no
validation, no rounding — if a rule were implemented here the tests would be
grading the fake instead of ``app.domain``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from app.domain import PolicyRow, RateRow, SplitRow


@dataclass
class StoredRate:
    rate_id: int
    product_code: str
    agent_id: int | None
    rate_pct: Decimal
    effective_from: datetime
    effective_to: datetime | None
    created_by: str


@dataclass
class LedgerRow:
    policy_id: int
    agent_id: int
    period_month: str
    rate_id: int
    split_pct: Decimal
    base_premium: Decimal
    commission_amt: Decimal


@dataclass
class AuditRow:
    action: str
    product_code: str | None
    agent_id: int | None
    policy_id: int | None
    detail: str
    actor: str


@dataclass
class FakeRepository:
    products: set[str] = field(default_factory=set)
    agents: dict[int, str] = field(default_factory=dict)
    policies: dict[int, PolicyRow] = field(default_factory=dict)
    rates: list[StoredRate] = field(default_factory=list)
    splits: list[tuple[int, int, Decimal]] = field(default_factory=list)
    ledger: list[LedgerRow] = field(default_factory=list)
    audit: list[AuditRow] = field(default_factory=list)
    next_rate_id: int = 100

    def product_exists(self, product_code: str) -> bool:
        return product_code in self.products

    def agent_status(self, agent_id: int) -> str | None:
        return self.agents.get(agent_id)

    def _scope(self, rate: StoredRate, product_code: str, agent_id: int | None) -> bool:
        return rate.product_code == product_code and rate.agent_id == agent_id

    def amend_open_rate(
        self,
        product_code: str,
        agent_id: int | None,
        rate_pct: Decimal,
        effective_from: datetime,
        actor: str,
    ) -> int | None:
        for rate in self.rates:
            if (
                self._scope(rate, product_code, agent_id)
                and rate.effective_to is None
                and rate.effective_from == effective_from
            ):
                rate.rate_pct = rate_pct
                rate.created_by = actor
                return rate.rate_id
        return None

    def close_earlier_open_rate(
        self,
        product_code: str,
        agent_id: int | None,
        effective_from: datetime,
        effective_to: datetime,
    ) -> int:
        closed = 0
        for rate in self.rates:
            if (
                self._scope(rate, product_code, agent_id)
                and rate.effective_to is None
                and rate.effective_from < effective_from
            ):
                rate.effective_to = effective_to
                closed += 1
        return closed

    def insert_rate(
        self,
        product_code: str,
        agent_id: int | None,
        rate_pct: Decimal,
        effective_from: datetime,
        actor: str,
    ) -> int:
        self.next_rate_id += 1
        self.rates.append(
            StoredRate(
                rate_id=self.next_rate_id,
                product_code=product_code,
                agent_id=agent_id,
                rate_pct=rate_pct,
                effective_from=effective_from,
                effective_to=None,
                created_by=actor,
            )
        )
        return self.next_rate_id

    def close_open_rate(
        self, product_code: str, agent_id: int | None, effective_to: datetime
    ) -> int:
        closed = 0
        for rate in self.rates:
            if self._scope(rate, product_code, agent_id) and rate.effective_to is None:
                rate.effective_to = effective_to
                closed += 1
        return closed

    def candidate_rates(
        self, product_code: str, agent_id: int | None, as_of: datetime
    ) -> list[RateRow]:
        return [
            RateRow(
                rate_id=rate.rate_id,
                agent_id=rate.agent_id,
                rate_pct=rate.rate_pct,
                effective_from=rate.effective_from,
            )
            for rate in self.rates
            if rate.product_code == product_code
            and rate.agent_id in (agent_id, None)
            and rate.effective_from <= as_of
            and (rate.effective_to is None or rate.effective_to >= as_of)
        ]

    def rate_pct(self, rate_id: int) -> Decimal:
        return next(rate.rate_pct for rate in self.rates if rate.rate_id == rate_id)

    def find_policy(self, policy_id: int) -> PolicyRow | None:
        return self.policies.get(policy_id)

    def delete_splits(self, policy_id: int) -> None:
        self.splits = [split for split in self.splits if split[0] != policy_id]

    def insert_split(self, policy_id: int, agent_id: int, split_pct: Decimal) -> None:
        self.splits.append((policy_id, agent_id, split_pct))

    def policy_splits(self, policy_id: int) -> list[SplitRow]:
        return [
            SplitRow(agent_id=agent_id, split_pct=split_pct)
            for stored_policy, agent_id, split_pct in self.splits
            if stored_policy == policy_id
        ]

    def delete_ledger(self, policy_id: int, period_month: str) -> None:
        self.ledger = [
            row
            for row in self.ledger
            if not (row.policy_id == policy_id and row.period_month == period_month)
        ]

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
        self.ledger.append(
            LedgerRow(
                policy_id=policy_id,
                agent_id=agent_id,
                period_month=period_month,
                rate_id=rate_id,
                split_pct=split_pct,
                base_premium=base_premium,
                commission_amt=commission_amt,
            )
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
        self.audit.append(
            AuditRow(
                action=action,
                product_code=product_code,
                agent_id=agent_id,
                policy_id=policy_id,
                detail=detail,
                actor=actor,
            )
        )


def seeded() -> FakeRepository:
    """The fixture's seed data (db/oltp/02_seed.sql), in memory."""
    repo = FakeRepository(
        products={"AUTO-STD", "HOME-PLUS", "TERM-20"},
        agents={1: "ACTIVE", 2: "ACTIVE", 3: "ACTIVE", 4: "SUSPENDED"},
        policies={
            1: PolicyRow(1, "AUTO-STD", Decimal("1800.00"), "IN_FORCE"),
            2: PolicyRow(2, "HOME-PLUS", Decimal("2400.00"), "IN_FORCE"),
            3: PolicyRow(3, "TERM-20", Decimal("1200.00"), "IN_FORCE"),
            4: PolicyRow(4, "AUTO-STD", Decimal("9600.00"), "IN_FORCE"),
            5: PolicyRow(5, "HOME-PLUS", Decimal("2000.00"), "LAPSED"),
        },
    )
    repo.rates = [
        StoredRate(1, "AUTO-STD", None, Decimal("8.00"), datetime(2024, 1, 1), None, "seed"),
        StoredRate(2, "HOME-PLUS", None, Decimal("10.00"), datetime(2024, 1, 1), None, "seed"),
        StoredRate(3, "TERM-20", None, Decimal("15.00"), datetime(2024, 1, 1), None, "seed"),
        StoredRate(4, "AUTO-STD", 1, Decimal("9.50"), datetime(2024, 6, 1), None, "seed"),
    ]
    repo.splits = [
        (1, 1, Decimal("100.00")),
        (2, 1, Decimal("60.00")),
        (2, 2, Decimal("40.00")),
        (4, 1, Decimal("50.00")),
        (4, 2, Decimal("30.00")),
        (4, 3, Decimal("20.00")),
    ]
    return repo
