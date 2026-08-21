"""Parity with ``db/tests/run_tests.sql``, case for case.

Every case in the Oracle suite is replayed here with the same inputs against the
same fixture database, driven through the extracted service instead of through
the package: same call, same arguments, same assertions on the resulting rows,
plus the ledger and audit side effects the SQL suite does not look at.

Each case runs inside ``unit_of_work``, which is what the HTTP layer uses, so the
commit-on-success / rollback-on-error behaviour of the old package body is part
of what is being compared. Cases run in file order, mirroring the order of the
Oracle suite, because that suite is a sequence too.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from app import domain
from app.db import unit_of_work
from app.domain import CommissionError, SplitInput

ACTOR = "parity"

pytestmark = pytest.mark.usefixtures("connection")


@pytest.mark.case("T1")
def test_t1_rate_upsert_supersedes_prior_open_rate(query) -> None:
    with unit_of_work() as repo:
        rate_id = domain.upsert_commission_rate(
            repo, "AUTO-STD", None, Decimal("8.50"), datetime(2026, 1, 1), ACTOR
        )

    ((effective_to,),) = query(
        """
        SELECT effective_to FROM commission_rates
         WHERE product_code = 'AUTO-STD' AND agent_id IS NULL AND rate_id <> :rate_id
           AND effective_from = DATE '2024-01-01'
        """,
        rate_id=rate_id,
    )
    assert effective_to == datetime(2025, 12, 31)

    ((action, detail),) = query(
        """
        SELECT action, detail FROM rate_audit_log
         WHERE audit_id = (SELECT MAX(audit_id) FROM rate_audit_log WHERE actor = :actor)
        """,
        actor=ACTOR,
    )
    assert (action, detail) == ("RATE_UPSERT", f"rate_id={rate_id} pct=8.5 from=2026-01-01")


@pytest.mark.case("T1b")
def test_t1b_same_day_upsert_amends_in_place(query) -> None:
    with unit_of_work() as repo:
        domain.upsert_commission_rate(
            repo, "AUTO-STD", None, Decimal("8.75"), datetime(2026, 1, 1), ACTOR
        )

    ((open_rows, max_pct),) = query(
        """
        SELECT COUNT(*), MAX(rate_pct) FROM commission_rates
         WHERE product_code = 'AUTO-STD' AND agent_id IS NULL AND effective_to IS NULL
        """
    )
    assert (open_rows, max_pct) == (1, Decimal("8.75"))


@pytest.mark.case("T2")
@pytest.mark.rule("R9")
def test_t2_invalid_rate_rejected(query) -> None:
    with pytest.raises(CommissionError) as error, unit_of_work() as repo:
        domain.upsert_commission_rate(
            repo, "AUTO-STD", None, Decimal("55"), datetime(2026, 2, 1), ACTOR
        )
    assert error.value.code == -20001

    ((rows,),) = query(
        """
        SELECT COUNT(*) FROM commission_rates
         WHERE product_code = 'AUTO-STD' AND effective_from = DATE '2026-02-01'
        """
    )
    assert rows == 0


@pytest.mark.case("T3")
def test_t3_suspended_agent_rate_rejected(query) -> None:
    with pytest.raises(CommissionError) as error, unit_of_work() as repo:
        domain.upsert_commission_rate(
            repo, "AUTO-STD", 4, Decimal("9"), datetime(2026, 2, 1), ACTOR
        )
    assert error.value.code == -20003

    ((rows,),) = query("SELECT COUNT(*) FROM commission_rates WHERE agent_id = 4")
    assert rows == 0


@pytest.mark.case("T4")
@pytest.mark.rule("R21")
def test_t4_splits_over_100_rejected(query) -> None:
    before = query("SELECT agent_id, split_pct FROM commission_splits WHERE policy_id = 3")
    with pytest.raises(CommissionError) as error, unit_of_work() as repo:
        domain.set_commission_splits(
            repo,
            3,
            [SplitInput(1, Decimal("70")), SplitInput(2, Decimal("40"))],
            ACTOR,
        )
    assert error.value.code == -20006
    # The rejected allocation is not partially applied.
    assert query("SELECT agent_id, split_pct FROM commission_splits WHERE policy_id = 3") == before


@pytest.mark.case("T5")
def test_t5_duplicate_split_agent_rejected() -> None:
    with pytest.raises(CommissionError) as error, unit_of_work() as repo:
        domain.set_commission_splits(
            repo,
            3,
            [SplitInput(1, Decimal("50")), SplitInput(1, Decimal("50"))],
            ACTOR,
        )
    assert error.value.code == -20006


@pytest.mark.case("T6")
def test_t6_two_way_split_stored(query) -> None:
    with unit_of_work() as repo:
        domain.set_commission_splits(
            repo,
            3,
            [SplitInput(2, Decimal("65")), SplitInput(3, Decimal("35"))],
            ACTOR,
        )

    ((rows, total),) = query(
        "SELECT COUNT(*), SUM(split_pct) FROM commission_splits WHERE policy_id = 3"
    )
    assert (rows, total) == (2, Decimal("100"))

    ((action, policy_id, detail),) = query(
        """
        SELECT action, policy_id, detail FROM rate_audit_log
         WHERE audit_id = (SELECT MAX(audit_id) FROM rate_audit_log WHERE actor = :actor)
        """,
        actor=ACTOR,
    )
    assert (action, policy_id, detail) == ("SPLIT_SET", 3, "2 agents")


@pytest.mark.case("T7")
def test_t7_agent_override_beats_default(query) -> None:
    with unit_of_work() as repo:
        rate_id = domain.resolve_rate(repo, "AUTO-STD", 1, datetime(2025, 6, 15))
    ((pct,),) = query(
        "SELECT rate_pct FROM commission_rates WHERE rate_id = :rate_id", rate_id=rate_id
    )
    assert pct == Decimal("9.50")


@pytest.mark.case("T7b")
def test_t7b_default_used_when_no_override(query) -> None:
    with unit_of_work() as repo:
        rate_id = domain.resolve_rate(repo, "AUTO-STD", 2, datetime(2025, 6, 15))
    ((pct,),) = query(
        "SELECT rate_pct FROM commission_rates WHERE rate_id = :rate_id", rate_id=rate_id
    )
    assert pct == Decimal("8.00")


@pytest.mark.case("T8")
def test_t8_three_way_split_commission_math(query) -> None:
    with unit_of_work() as repo:
        rows = domain.calculate_policy_commission(repo, 4, "2025-06", ACTOR)
    assert rows == 3

    ledger = query(
        """
        SELECT agent_id, commission_amt, split_pct, base_premium
          FROM commission_ledger
         WHERE policy_id = 4 AND period_month = '2025-06'
         ORDER BY agent_id
        """
    )
    # premium 9600/12 = 800. Agent 1 at its 9.50 override: 800*9.5%*50% = 38.00.
    # Agents 2 and 3 at the 8.00 default: 19.20 and 12.80.
    assert ledger == [
        (1, Decimal("38.00"), Decimal("50.00"), Decimal("9600.00")),
        (2, Decimal("19.20"), Decimal("30.00"), Decimal("9600.00")),
        (3, Decimal("12.80"), Decimal("20.00"), Decimal("9600.00")),
    ]
    for _agent, amount, _split, _premium in ledger:
        assert isinstance(amount, Decimal)

    ((action, detail),) = query(
        """
        SELECT action, detail FROM rate_audit_log
         WHERE audit_id = (SELECT MAX(audit_id) FROM rate_audit_log WHERE actor = :actor)
        """,
        actor=ACTOR,
    )
    assert (action, detail) == ("COMMISSION_CALC", "2025-06 rows=3")


@pytest.mark.case("T9")
def test_t9_recalculation_is_idempotent(query) -> None:
    before = query(
        """
        SELECT agent_id, commission_amt FROM commission_ledger
         WHERE policy_id = 4 AND period_month = '2025-06' ORDER BY agent_id
        """
    )
    with unit_of_work() as repo:
        domain.calculate_policy_commission(repo, 4, "2025-06", ACTOR)
    after = query(
        """
        SELECT agent_id, commission_amt FROM commission_ledger
         WHERE policy_id = 4 AND period_month = '2025-06' ORDER BY agent_id
        """
    )
    assert len(after) == 3
    assert after == before


@pytest.mark.case("T10")
def test_t10_lapsed_policy_rejected() -> None:
    with pytest.raises(CommissionError) as error, unit_of_work() as repo:
        domain.calculate_policy_commission(repo, 5, "2025-06", ACTOR)
    assert error.value.code == -20008


@pytest.mark.case("T11")
@pytest.mark.rule("R21")
def test_t11_empty_split_rejected(query) -> None:
    before = query("SELECT agent_id, split_pct FROM commission_splits WHERE policy_id = 3")
    with pytest.raises(CommissionError) as error, unit_of_work() as repo:
        domain.set_commission_splits(repo, 3, [], ACTOR)
    assert error.value.code == -20006
    assert query("SELECT agent_id, split_pct FROM commission_splits WHERE policy_id = 3") == before


@pytest.mark.case("T12")
def test_t12_audit_trail_written(query) -> None:
    ((rows,),) = query("SELECT COUNT(*) FROM rate_audit_log WHERE actor = :actor", actor=ACTOR)
    assert rows >= 4


@pytest.mark.rule("R33")
@pytest.mark.rule("R35")
def test_calculation_without_splits_rolls_back_the_ledger_it_deleted(
    query, connection
) -> None:
    """The no-split guard fires after the delete, so the rollback has to undo it.

    The Oracle suite never walks this path; it is the one place where the
    package's ROLLBACK is load-bearing rather than incidental.
    """
    with unit_of_work() as repo:
        domain.calculate_policy_commission(repo, 1, "2025-06", ACTOR)
    before = query(
        """
        SELECT agent_id, commission_amt FROM commission_ledger
         WHERE policy_id = 1 AND period_month = '2025-06' ORDER BY agent_id
        """
    )
    assert before

    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM commission_splits WHERE policy_id = 1")
    connection.commit()

    with pytest.raises(CommissionError) as error, unit_of_work() as repo:
        domain.calculate_policy_commission(repo, 1, "2025-06", ACTOR)
    assert error.value.code == -20006

    after = query(
        """
        SELECT agent_id, commission_amt FROM commission_ledger
         WHERE policy_id = 1 AND period_month = '2025-06' ORDER BY agent_id
        """
    )
    assert after == before
