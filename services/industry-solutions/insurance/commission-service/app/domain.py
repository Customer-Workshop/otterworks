"""Commission Pay business rules.

This module is the single home of the rules that used to live in the Oracle
package body ``COMMISSION_PKG``. Rule numbers (``R1`` … ``R38``) refer to
``services/industry-solutions/insurance/RULE_LEDGER.md``; the package body is now
a thin delegate that marshals its arguments here and re-raises whatever this
module decides.

Nothing in here touches the database directly: persistence is a
``CommissionRepository`` port, which keeps the rules testable and keeps SQL out
of the rule statements.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Protocol

from app.numbers import divide, multiply, round_cents, to_char

MAX_RATE_PCT = Decimal(50)
MAX_SPLIT_PCT = Decimal(100)
SPLIT_TOTAL = Decimal(100)
MONTHS_PER_YEAR = Decimal(12)
PERCENT = Decimal(100)


class CommissionError(Exception):
    """An ``ORA-20xxx`` application error, code and message preserved."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class SplitInput:
    agent_id: int
    split_pct: Decimal | None


@dataclass(frozen=True)
class RateRow:
    rate_id: int
    agent_id: int | None
    rate_pct: Decimal
    effective_from: datetime


@dataclass(frozen=True)
class PolicyRow:
    policy_id: int
    product_code: str
    annual_premium: Decimal
    status: str


@dataclass(frozen=True)
class SplitRow:
    agent_id: int
    split_pct: Decimal


class CommissionRepository(Protocol):
    def product_exists(self, product_code: str) -> bool: ...

    def agent_status(self, agent_id: int) -> str | None: ...

    def amend_open_rate(
        self,
        product_code: str,
        agent_id: int | None,
        rate_pct: Decimal,
        effective_from: datetime,
        actor: str,
    ) -> int | None: ...

    def close_earlier_open_rate(
        self,
        product_code: str,
        agent_id: int | None,
        effective_from: datetime,
        effective_to: datetime,
    ) -> int: ...

    def insert_rate(
        self,
        product_code: str,
        agent_id: int | None,
        rate_pct: Decimal,
        effective_from: datetime,
        actor: str,
    ) -> int: ...

    def close_open_rate(
        self, product_code: str, agent_id: int | None, effective_to: datetime
    ) -> int: ...

    def candidate_rates(
        self, product_code: str, agent_id: int | None, as_of: datetime
    ) -> list[RateRow]: ...

    def rate_pct(self, rate_id: int) -> Decimal: ...

    def find_policy(self, policy_id: int) -> PolicyRow | None: ...

    def delete_splits(self, policy_id: int) -> None: ...

    def insert_split(self, policy_id: int, agent_id: int, split_pct: Decimal) -> None: ...

    def policy_splits(self, policy_id: int) -> list[SplitRow]: ...

    def delete_ledger(self, policy_id: int, period_month: str) -> None: ...

    def insert_ledger(
        self,
        policy_id: int,
        agent_id: int,
        period_month: str,
        rate_id: int,
        split_pct: Decimal,
        base_premium: Decimal,
        commission_amt: Decimal,
    ) -> None: ...

    def log_action(
        self,
        action: str,
        product_code: str | None,
        agent_id: int | None,
        policy_id: int | None,
        detail: str,
        actor: str,
    ) -> None: ...


def _assert_product(repo: CommissionRepository, product_code: str) -> None:
    # R2: the product must exist.
    if not repo.product_exists(product_code):
        raise CommissionError(-20004, f"Unknown product: {product_code}")


def _assert_active_agent(repo: CommissionRepository, agent_id: int) -> None:
    # R3 / R17: the agent must exist.
    status = repo.agent_status(agent_id)
    if status is None:
        raise CommissionError(-20002, f"Unknown agent: {agent_id}")
    # R4 / R17: and be ACTIVE.
    if status != "ACTIVE":
        raise CommissionError(-20003, f"Agent {agent_id} is {status}")


def upsert_commission_rate(
    repo: CommissionRepository,
    product_code: str,
    agent_id: int | None,
    rate_pct: Decimal | None,
    effective_from: datetime,
    actor: str,
) -> int:
    """Create or supersede a commission rate; returns the rate id."""
    # R1: the rate must be non-NULL and in (0, 50].
    if rate_pct is None or rate_pct <= 0 or rate_pct > MAX_RATE_PCT:
        raise CommissionError(-20001, f"Rate must be in (0, 50]: {to_char(rate_pct)}")
    _assert_product(repo, product_code)
    if agent_id is not None:
        _assert_active_agent(repo, agent_id)

    # R5: a same-day open rate is amended in place rather than superseded.
    rate_id = repo.amend_open_rate(product_code, agent_id, rate_pct, effective_from, actor)

    if rate_id is None:
        # R6: close the open rate that starts earlier, the day before the new one.
        repo.close_earlier_open_rate(
            product_code, agent_id, effective_from, effective_from - timedelta(days=1)
        )
        # R7: and open the new one.
        rate_id = repo.insert_rate(product_code, agent_id, rate_pct, effective_from, actor)

    # R8: audit.
    repo.log_action(
        "RATE_UPSERT",
        product_code,
        agent_id,
        None,
        f"rate_id={rate_id} pct={to_char(rate_pct)} from={effective_from.strftime('%Y-%m-%d')}",
        actor,
    )
    return rate_id


def end_commission_rate(
    repo: CommissionRepository,
    product_code: str,
    agent_id: int | None,
    effective_to: datetime,
    actor: str,
) -> None:
    """Close the open rate for a (product, agent) scope."""
    # R10: close the open rate for the scope.
    closed = repo.close_open_rate(product_code, agent_id, effective_to)
    # R11: there has to be one.
    if closed == 0:
        scope = str(agent_id) if agent_id is not None else "default"
        raise CommissionError(-20007, f"No open rate for {product_code}/{scope}")
    # R12: audit.
    repo.log_action(
        "RATE_END",
        product_code,
        agent_id,
        None,
        f"to={effective_to.strftime('%Y-%m-%d')}",
        actor,
    )


def set_commission_splits(
    repo: CommissionRepository,
    policy_id: int,
    splits: list[SplitInput],
    actor: str,
) -> int:
    """Replace a policy's split allocation; returns the number of allocations."""
    # R13: the policy must exist.
    if repo.find_policy(policy_id) is None:
        raise CommissionError(-20005, f"Unknown policy: {policy_id}")

    # R14: at least one allocation.
    if not splits:
        raise CommissionError(-20006, "At least one split allocation is required")

    # R15: no duplicate agents.
    if len({split.agent_id for split in splits}) != len(splits):
        raise CommissionError(-20006, "Duplicate agent in split allocation")

    total = Decimal(0)
    for split in splits:
        # R16: each percentage in (0, 100], checked in collection order …
        if split.split_pct is None or split.split_pct <= 0 or split.split_pct > MAX_SPLIT_PCT:
            raise CommissionError(-20006, f"Split pct must be in (0, 100]: agent {split.agent_id}")
        # R17: … then that agent must be active.
        _assert_active_agent(repo, split.agent_id)
        total += split.split_pct

    # R18: the percentages must total exactly 100.
    if total != SPLIT_TOTAL:
        raise CommissionError(-20006, f"Split percentages must total 100.00, got {to_char(total)}")

    # R19: wholesale replacement, in collection order.
    repo.delete_splits(policy_id)
    for split in splits:
        repo.insert_split(policy_id, split.agent_id, split.split_pct)

    # R20: audit.
    repo.log_action("SPLIT_SET", None, None, policy_id, f"{len(splits)} agents", actor)
    return len(splits)


def resolve_rate(
    repo: CommissionRepository,
    product_code: str,
    agent_id: int | None,
    as_of: datetime,
) -> int:
    """The rate in force for (product, agent, date)."""
    # R22: candidates are the product default and the agent's own rate whose
    # effective window contains as_of.
    candidates = repo.candidate_rates(product_code, agent_id, as_of)
    if not candidates:
        scope = str(agent_id) if agent_id is not None else "default"
        raise CommissionError(
            -20007,
            f"No rate in force for {product_code}/agent {scope} on {as_of.strftime('%Y-%m-%d')}",
        )
    # R23: agent-specific beats the default (NULLS LAST), then latest start wins.
    winner = min(
        candidates,
        key=lambda row: (row.agent_id is None, -row.effective_from.toordinal()),
    )
    return winner.rate_id


def period_as_of(period_month: str) -> datetime:
    """R27: rates are resolved as of the last day of the period month."""
    try:
        first = datetime.strptime(period_month, "%Y-%m")
    except ValueError as error:
        raise CommissionError(
            -20000, f"Not a valid period month (YYYY-MM): {period_month}"
        ) from error
    last_day = calendar.monthrange(first.year, first.month)[1]
    return first.replace(day=last_day)


def calculate_policy_commission(
    repo: CommissionRepository,
    policy_id: int,
    period_month: str,
    actor: str,
) -> int:
    """Write the policy's monthly commission ledger; returns the row count."""
    # R25: the policy must exist.
    policy = repo.find_policy(policy_id)
    if policy is None:
        raise CommissionError(-20005, f"Unknown policy: {policy_id}")
    # R26: and be in force.
    if policy.status != "IN_FORCE":
        raise CommissionError(-20008, f"Policy {policy_id} is {policy.status}")

    as_of = period_as_of(period_month)

    # R28: recalculating a period replaces its rows.
    repo.delete_ledger(policy_id, period_month)

    # R29: highest share first, then agent id.
    splits = sorted(repo.policy_splits(policy_id), key=lambda row: (-row.split_pct, row.agent_id))

    rows = 0
    for split in splits:
        rate_id = resolve_rate(repo, policy.product_code, split.agent_id, as_of)
        pct = repo.rate_pct(rate_id)

        # R30: monthly premium x rate x share, rounded to cents for this agent's
        # row only. R31: no remainder redistribution — each row rounds alone.
        monthly = divide(policy.annual_premium, MONTHS_PER_YEAR)
        amount = round_cents(
            multiply(multiply(monthly, divide(pct, PERCENT)), divide(split.split_pct, PERCENT))
        )

        # R32: the row records the resolved rate, the share, and the annual premium.
        repo.insert_ledger(
            policy_id,
            split.agent_id,
            period_month,
            rate_id,
            split.split_pct,
            policy.annual_premium,
            amount,
        )
        rows += 1

    # R33: a policy with no allocation cannot be calculated.
    if rows == 0:
        raise CommissionError(-20006, f"Policy {policy_id} has no split allocation")

    # R34: audit.
    repo.log_action(
        "COMMISSION_CALC",
        policy.product_code,
        None,
        policy_id,
        f"{period_month} rows={rows}",
        actor,
    )
    return rows


__all__ = [
    "CommissionError",
    "CommissionRepository",
    "PolicyRow",
    "RateRow",
    "SplitInput",
    "SplitRow",
    "calculate_policy_commission",
    "end_commission_rate",
    "period_as_of",
    "resolve_rate",
    "set_commission_splits",
    "upsert_commission_rate",
]
