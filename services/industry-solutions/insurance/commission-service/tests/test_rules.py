"""Rule-level tests for the extracted Commission Pay rules.

One test per rule in ``RULE_LEDGER.md``, run against the in-memory repository so
that rules the Oracle suite never exercised (unknown product, unknown agent,
``end_commission_rate``, cancelled policies, remainder handling, Oracle number
formatting) are covered here — those are the rows the ledger flags as risky.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from app import domain
from app.domain import CommissionError, PolicyRow, SplitInput
from app.numbers import to_char
from tests.fakes import StoredRate, seeded


def split(agent_id: int, pct: str) -> SplitInput:
    return SplitInput(agent_id=agent_id, split_pct=Decimal(pct))


@pytest.mark.rule("R1")
@pytest.mark.parametrize("rate", [None, "0", "-1", "50.01", "55"])
def test_rate_must_be_within_zero_to_fifty(rate: str | None) -> None:
    repo = seeded()
    with pytest.raises(CommissionError) as error:
        domain.upsert_commission_rate(
            repo,
            "AUTO-STD",
            None,
            None if rate is None else Decimal(rate),
            datetime(2026, 2, 1),
            "tester",
        )
    assert error.value.code == -20001
    expected = "NULL" if rate is None else to_char(Decimal(rate))
    assert error.value.message == f"Rate must be in (0, 50]: {expected}"


@pytest.mark.rule("R1")
def test_rate_of_exactly_fifty_is_accepted() -> None:
    repo = seeded()
    rate_id = domain.upsert_commission_rate(
        repo, "AUTO-STD", None, Decimal("50"), datetime(2026, 2, 1), "tester"
    )
    assert repo.rate_pct(rate_id) == Decimal("50")


@pytest.mark.rule("R2")
def test_unknown_product_is_rejected() -> None:
    repo = seeded()
    with pytest.raises(CommissionError) as error:
        domain.upsert_commission_rate(
            repo, "NOPE", None, Decimal("5"), datetime(2026, 1, 1), "tester"
        )
    assert (error.value.code, error.value.message) == (-20004, "Unknown product: NOPE")


@pytest.mark.rule("R3")
def test_unknown_agent_is_rejected() -> None:
    repo = seeded()
    with pytest.raises(CommissionError) as error:
        domain.upsert_commission_rate(
            repo, "AUTO-STD", 99, Decimal("5"), datetime(2026, 1, 1), "tester"
        )
    assert (error.value.code, error.value.message) == (-20002, "Unknown agent: 99")


@pytest.mark.rule("R4")
def test_suspended_agent_is_rejected() -> None:
    repo = seeded()
    with pytest.raises(CommissionError) as error:
        domain.upsert_commission_rate(
            repo, "AUTO-STD", 4, Decimal("9"), datetime(2026, 2, 1), "tester"
        )
    assert (error.value.code, error.value.message) == (-20003, "Agent 4 is SUSPENDED")


@pytest.mark.rule("R5")
def test_same_day_upsert_amends_in_place() -> None:
    repo = seeded()
    first = domain.upsert_commission_rate(
        repo, "AUTO-STD", None, Decimal("8.50"), datetime(2026, 1, 1), "tester"
    )
    again = domain.upsert_commission_rate(
        repo, "AUTO-STD", None, Decimal("8.75"), datetime(2026, 1, 1), "amender"
    )
    open_rates = [
        rate
        for rate in repo.rates
        if rate.agent_id is None and rate.product_code == "AUTO-STD" and rate.effective_to is None
    ]
    assert again == first
    assert [(rate.rate_pct, rate.created_by) for rate in open_rates] == [
        (Decimal("8.75"), "amender")
    ]


@pytest.mark.rule("R6")
def test_upsert_closes_the_prior_open_rate_the_day_before() -> None:
    repo = seeded()
    domain.upsert_commission_rate(
        repo, "AUTO-STD", None, Decimal("8.50"), datetime(2026, 1, 1), "tester"
    )
    prior = next(rate for rate in repo.rates if rate.rate_id == 1)
    assert prior.effective_to == datetime(2025, 12, 31)


@pytest.mark.rule("R6")
def test_upsert_does_not_close_a_later_starting_open_rate() -> None:
    repo = seeded()
    repo.rates.append(
        StoredRate(9, "AUTO-STD", None, Decimal("7"), datetime(2027, 1, 1), None, "seed")
    )
    domain.upsert_commission_rate(
        repo, "AUTO-STD", None, Decimal("8.50"), datetime(2026, 1, 1), "tester"
    )
    assert next(rate for rate in repo.rates if rate.rate_id == 9).effective_to is None


@pytest.mark.rule("R7")
def test_upsert_opens_the_new_rate() -> None:
    repo = seeded()
    rate_id = domain.upsert_commission_rate(
        repo, "AUTO-STD", None, Decimal("8.50"), datetime(2026, 1, 1), "tester"
    )
    new_rate = next(rate for rate in repo.rates if rate.rate_id == rate_id)
    assert (new_rate.effective_from, new_rate.effective_to, new_rate.created_by) == (
        datetime(2026, 1, 1),
        None,
        "tester",
    )


@pytest.mark.rule("R8")
def test_upsert_writes_an_audit_row() -> None:
    repo = seeded()
    rate_id = domain.upsert_commission_rate(
        repo, "AUTO-STD", None, Decimal("8.50"), datetime(2026, 1, 1), "tester"
    )
    assert repo.audit[-1].action == "RATE_UPSERT"
    assert repo.audit[-1].detail == f"rate_id={rate_id} pct=8.5 from=2026-01-01"
    assert (repo.audit[-1].product_code, repo.audit[-1].agent_id) == ("AUTO-STD", None)


@pytest.mark.rule("R10")
def test_end_rate_closes_the_open_rate() -> None:
    repo = seeded()
    domain.end_commission_rate(repo, "AUTO-STD", None, datetime(2026, 3, 31), "tester")
    assert next(rate for rate in repo.rates if rate.rate_id == 1).effective_to == datetime(
        2026, 3, 31
    )


@pytest.mark.rule("R11")
def test_end_rate_without_an_open_rate_is_rejected() -> None:
    repo = seeded()
    domain.end_commission_rate(repo, "AUTO-STD", None, datetime(2026, 3, 31), "tester")
    with pytest.raises(CommissionError) as error:
        domain.end_commission_rate(repo, "AUTO-STD", None, datetime(2026, 4, 30), "tester")
    assert (error.value.code, error.value.message) == (
        -20007,
        "No open rate for AUTO-STD/default",
    )


@pytest.mark.rule("R11")
def test_end_rate_names_the_agent_scope_in_the_error() -> None:
    repo = seeded()
    with pytest.raises(CommissionError) as error:
        domain.end_commission_rate(repo, "AUTO-STD", 2, datetime(2026, 4, 30), "tester")
    assert error.value.message == "No open rate for AUTO-STD/2"


@pytest.mark.rule("R12")
def test_end_rate_writes_an_audit_row() -> None:
    repo = seeded()
    domain.end_commission_rate(repo, "AUTO-STD", None, datetime(2026, 3, 31), "tester")
    assert (repo.audit[-1].action, repo.audit[-1].detail) == ("RATE_END", "to=2026-03-31")


@pytest.mark.rule("R13")
def test_splits_for_an_unknown_policy_are_rejected() -> None:
    repo = seeded()
    with pytest.raises(CommissionError) as error:
        domain.set_commission_splits(repo, 99, [split(1, "100")], "tester")
    assert (error.value.code, error.value.message) == (-20005, "Unknown policy: 99")


@pytest.mark.rule("R14")
def test_empty_split_allocation_is_rejected() -> None:
    repo = seeded()
    with pytest.raises(CommissionError) as error:
        domain.set_commission_splits(repo, 3, [], "tester")
    assert (error.value.code, error.value.message) == (
        -20006,
        "At least one split allocation is required",
    )


@pytest.mark.rule("R15")
def test_duplicate_agent_in_split_is_rejected() -> None:
    repo = seeded()
    with pytest.raises(CommissionError) as error:
        domain.set_commission_splits(repo, 3, [split(1, "50"), split(1, "50")], "tester")
    assert (error.value.code, error.value.message) == (
        -20006,
        "Duplicate agent in split allocation",
    )


@pytest.mark.rule("R16")
@pytest.mark.parametrize("pct", [None, "0", "-5", "100.01"])
def test_split_percentage_must_be_within_zero_to_hundred(pct: str | None) -> None:
    repo = seeded()
    allocation = SplitInput(agent_id=2, split_pct=None if pct is None else Decimal(pct))
    with pytest.raises(CommissionError) as error:
        domain.set_commission_splits(repo, 3, [allocation], "tester")
    assert (error.value.code, error.value.message) == (
        -20006,
        "Split pct must be in (0, 100]: agent 2",
    )


@pytest.mark.rule("R16")
def test_split_percentage_is_validated_before_the_agent() -> None:
    # Agent 4 is SUSPENDED and its percentage is invalid: the percentage check
    # runs first, so -20006 wins over -20003.
    repo = seeded()
    with pytest.raises(CommissionError) as error:
        domain.set_commission_splits(repo, 3, [SplitInput(4, Decimal("0"))], "tester")
    assert error.value.code == -20006


@pytest.mark.rule("R17")
def test_split_agent_must_be_active() -> None:
    repo = seeded()
    with pytest.raises(CommissionError) as error:
        domain.set_commission_splits(repo, 3, [split(4, "60"), split(1, "40")], "tester")
    assert (error.value.code, error.value.message) == (-20003, "Agent 4 is SUSPENDED")


@pytest.mark.rule("R18")
@pytest.mark.parametrize(("pcts", "total"), [(("70", "40"), "110"), (("70", "20"), "90")])
def test_split_percentages_must_total_one_hundred(pcts: tuple[str, str], total: str) -> None:
    repo = seeded()
    allocation = [split(1, pcts[0]), split(2, pcts[1])]
    with pytest.raises(CommissionError) as error:
        domain.set_commission_splits(repo, 3, allocation, "tester")
    assert (error.value.code, error.value.message) == (
        -20006,
        f"Split percentages must total 100.00, got {total}",
    )


@pytest.mark.rule("R19")
def test_valid_split_replaces_the_whole_allocation_in_order() -> None:
    repo = seeded()
    count = domain.set_commission_splits(repo, 2, [split(2, "65"), split(3, "35")], "tester")
    assert count == 2
    assert [(agent, pct) for policy, agent, pct in repo.splits if policy == 2] == [
        (2, Decimal("65")),
        (3, Decimal("35")),
    ]


@pytest.mark.rule("R20")
def test_split_set_writes_an_audit_row() -> None:
    repo = seeded()
    domain.set_commission_splits(repo, 3, [split(2, "65"), split(3, "35")], "tester")
    audit = repo.audit[-1]
    assert (audit.action, audit.policy_id, audit.detail) == ("SPLIT_SET", 3, "2 agents")
    assert (audit.product_code, audit.agent_id) == (None, None)


@pytest.mark.rule("R22")
def test_rates_outside_the_effective_window_are_not_candidates() -> None:
    repo = seeded()
    with pytest.raises(CommissionError) as error:
        domain.resolve_rate(repo, "AUTO-STD", 1, datetime(2023, 12, 31))
    assert (error.value.code, error.value.message) == (
        -20007,
        "No rate in force for AUTO-STD/agent 1 on 2023-12-31",
    )


@pytest.mark.rule("R23")
def test_agent_specific_rate_beats_the_product_default() -> None:
    repo = seeded()
    assert domain.resolve_rate(repo, "AUTO-STD", 1, datetime(2025, 6, 15)) == 4
    assert domain.resolve_rate(repo, "AUTO-STD", 2, datetime(2025, 6, 15)) == 1


@pytest.mark.rule("R23")
def test_latest_starting_rate_wins_within_a_scope() -> None:
    repo = seeded()
    repo.rates.append(
        StoredRate(9, "AUTO-STD", None, Decimal("6"), datetime(2025, 1, 1), None, "seed")
    )
    assert domain.resolve_rate(repo, "AUTO-STD", 2, datetime(2025, 6, 15)) == 9


@pytest.mark.rule("R24")
def test_no_rate_in_force_is_rejected_for_the_default_scope() -> None:
    repo = seeded()
    with pytest.raises(CommissionError) as error:
        domain.resolve_rate(repo, "AUTO-STD", None, datetime(2020, 1, 1))
    assert error.value.message == "No rate in force for AUTO-STD/agent default on 2020-01-01"


@pytest.mark.rule("R25")
def test_commission_for_an_unknown_policy_is_rejected() -> None:
    repo = seeded()
    with pytest.raises(CommissionError) as error:
        domain.calculate_policy_commission(repo, 99, "2025-06", "tester")
    assert (error.value.code, error.value.message) == (-20005, "Unknown policy: 99")


@pytest.mark.rule("R26")
@pytest.mark.parametrize("status", ["LAPSED", "CANCELLED"])
def test_commission_requires_a_policy_in_force(status: str) -> None:
    repo = seeded()
    repo.policies[5] = PolicyRow(5, "HOME-PLUS", Decimal("2000.00"), status)
    with pytest.raises(CommissionError) as error:
        domain.calculate_policy_commission(repo, 5, "2025-06", "tester")
    assert (error.value.code, error.value.message) == (-20008, f"Policy 5 is {status}")


@pytest.mark.rule("R27")
@pytest.mark.parametrize(
    ("period", "as_of"),
    [
        ("2025-06", datetime(2025, 6, 30)),
        ("2025-02", datetime(2025, 2, 28)),
        ("2024-02", datetime(2024, 2, 29)),
        ("2025-12", datetime(2025, 12, 31)),
    ],
)
def test_period_resolves_as_of_the_last_day_of_the_month(period: str, as_of: datetime) -> None:
    assert domain.period_as_of(period) == as_of


@pytest.mark.rule("R27")
def test_the_rate_in_force_at_month_end_is_the_one_used() -> None:
    # A rate that opens mid-month is the one that applies: the period resolves
    # on the last day, not the first.
    repo = seeded()
    repo.rates.append(
        StoredRate(9, "AUTO-STD", 1, Decimal("20"), datetime(2025, 6, 15), None, "seed")
    )
    repo.splits = [(4, 1, Decimal("100.00"))]
    domain.calculate_policy_commission(repo, 4, "2025-06", "tester")
    assert repo.ledger[0].rate_id == 9


@pytest.mark.rule("R28")
def test_recalculating_a_period_replaces_its_rows() -> None:
    repo = seeded()
    domain.calculate_policy_commission(repo, 4, "2025-06", "tester")
    domain.calculate_policy_commission(repo, 4, "2025-06", "tester")
    assert len(repo.ledger) == 3


@pytest.mark.rule("R28")
def test_recalculating_a_period_leaves_other_periods_alone() -> None:
    repo = seeded()
    domain.calculate_policy_commission(repo, 4, "2025-05", "tester")
    domain.calculate_policy_commission(repo, 4, "2025-06", "tester")
    assert {row.period_month for row in repo.ledger} == {"2025-05", "2025-06"}


@pytest.mark.rule("R29")
def test_splits_are_processed_highest_share_first_then_by_agent() -> None:
    repo = seeded()
    repo.splits = [
        (4, 3, Decimal("20.00")),
        (4, 2, Decimal("40.00")),
        (4, 1, Decimal("40.00")),
    ]
    domain.calculate_policy_commission(repo, 4, "2025-06", "tester")
    assert [row.agent_id for row in repo.ledger] == [1, 2, 3]


@pytest.mark.rule("R30")
def test_commission_is_monthly_premium_times_rate_times_share() -> None:
    repo = seeded()
    domain.calculate_policy_commission(repo, 4, "2025-06", "tester")
    amounts = {row.agent_id: row.commission_amt for row in repo.ledger}
    # 9600/12 = 800; agent 1 at its 9.50 override, agents 2 and 3 at the 8.00 default.
    assert amounts == {
        1: Decimal("38.00"),
        2: Decimal("19.20"),
        3: Decimal("12.80"),
    }


@pytest.mark.rule("R30")
def test_rounding_is_half_away_from_zero_at_two_decimals() -> None:
    repo = seeded()
    # 1000/12 * 10% * 100% = 8.3333…, so the third decimal rounds down.
    repo.policies[2] = PolicyRow(2, "HOME-PLUS", Decimal("1000.00"), "IN_FORCE")
    repo.splits = [(2, 1, Decimal("100.00"))]
    domain.calculate_policy_commission(repo, 2, "2025-06", "tester")
    assert repo.ledger[0].commission_amt == Decimal("8.33")

    repo.policies[2] = PolicyRow(2, "HOME-PLUS", Decimal("1000.20"), "IN_FORCE")
    domain.calculate_policy_commission(repo, 2, "2025-07", "tester")
    # 1000.20/12 = 83.35; 83.35 * 10% = 8.335 → half away from zero → 8.34.
    assert repo.ledger[-1].commission_amt == Decimal("8.34")


@pytest.mark.rule("R31")
def test_rounding_remainders_are_not_redistributed() -> None:
    repo = seeded()
    # Three equal shares of a premium that does not divide evenly: each row
    # rounds on its own and the rows deliberately do not add up to the total.
    repo.policies[3] = PolicyRow(3, "TERM-20", Decimal("1000.00"), "IN_FORCE")
    repo.splits = [
        (3, 1, Decimal("33.34")),
        (3, 2, Decimal("33.33")),
        (3, 3, Decimal("33.33")),
    ]
    domain.calculate_policy_commission(repo, 3, "2025-06", "tester")
    amounts = [row.commission_amt for row in repo.ledger]
    # 1000/12 * 15% = 12.50 for the whole policy.
    assert amounts == [Decimal("4.17"), Decimal("4.17"), Decimal("4.17")]
    assert sum(amounts) == Decimal("12.51")


@pytest.mark.rule("R32")
def test_ledger_row_records_rate_share_and_annual_premium() -> None:
    repo = seeded()
    domain.calculate_policy_commission(repo, 4, "2025-06", "tester")
    row = next(row for row in repo.ledger if row.agent_id == 1)
    assert (row.rate_id, row.split_pct, row.base_premium, row.period_month) == (
        4,
        Decimal("50.00"),
        Decimal("9600.00"),
        "2025-06",
    )


@pytest.mark.rule("R33")
def test_policy_without_a_split_allocation_cannot_be_calculated() -> None:
    repo = seeded()
    with pytest.raises(CommissionError) as error:
        domain.calculate_policy_commission(repo, 3, "2025-06", "tester")
    assert (error.value.code, error.value.message) == (
        -20006,
        "Policy 3 has no split allocation",
    )


@pytest.mark.rule("R34")
def test_commission_run_writes_an_audit_row() -> None:
    repo = seeded()
    domain.calculate_policy_commission(repo, 4, "2025-06", "tester")
    audit = repo.audit[-1]
    assert (audit.action, audit.product_code, audit.policy_id, audit.detail) == (
        "COMMISSION_CALC",
        "AUTO-STD",
        4,
        "2025-06 rows=3",
    )


@pytest.mark.rule("R36")
def test_the_product_default_and_an_agent_rate_are_separate_scopes() -> None:
    repo = seeded()
    domain.upsert_commission_rate(
        repo, "AUTO-STD", 1, Decimal("11"), datetime(2026, 1, 1), "tester"
    )
    # The default rate for the same product is untouched by an agent-scoped upsert.
    assert next(rate for rate in repo.rates if rate.rate_id == 1).effective_to is None
    assert next(rate for rate in repo.rates if rate.rate_id == 4).effective_to == datetime(
        2025, 12, 31
    )


@pytest.mark.rule("R37")
def test_commission_arithmetic_never_goes_through_binary_float() -> None:
    repo = seeded()
    # 0.1 + 0.2 territory: 2400/12 * 10% * 60% = 12.00 exactly, and the stored
    # value must be an exact decimal, not a float that merely prints as one.
    domain.calculate_policy_commission(repo, 2, "2025-06", "tester")
    for row in repo.ledger:
        assert isinstance(row.commission_amt, Decimal)
    amounts = {row.agent_id: row.commission_amt for row in repo.ledger}
    assert amounts == {1: Decimal("12.00"), 2: Decimal("8.00")}


@pytest.mark.rule("R38")
@pytest.mark.parametrize(
    ("value", "rendered"),
    [
        ("8.50", "8.5"),
        ("0.5", ".5"),
        ("100", "100"),
        ("110.00", "110"),
        ("8", "8"),
        ("-0.25", "-.25"),
    ],
)
def test_numbers_render_the_way_oracle_renders_them(value: str, rendered: str) -> None:
    assert to_char(Decimal(value)) == rendered
