"""BUD-01 manual KRW calculation, evidence and failure boundaries."""

from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal, Inexact, ROUND_DOWN, localcontext

import pytest

from examples.budget_monthly_offline import MONTH, entry, policy, render, sample_input
from asset_copilot.budget import (Allocation, BudgetCategory as C, BudgetPolicy, EntryKind as K,
                                  calculate_month)


D = Decimal


def line(result, category, goal_id=None):
    return next(item for item in result.allocations
                if item.category is category and item.goal_id == goal_id)


def day(result, number):
    return next(item for item in result.cash_days if item.day == date(2026, 9, number))


def test_normal_month_preserves_categories_cash_and_provenance():
    data = sample_input()
    result = calculate_month(data)
    assert (result.allocation_margin, result.unallocated, result.shortage) == (D("730"), D("730"), D("0"))
    assert sum((item.planned for item in result.allocations), D("0")) == D("3070")
    assert (line(result, C.LIVING).planned, line(result, C.LIVING).used,
            line(result, C.LIVING).remaining) == (D("400"), D("400"), D("0"))
    assert (line(result, C.DEBT_PRINCIPAL).used, line(result, C.DEBT_COST).used) == (D("200"), D("20"))
    assert (day(result, 5).actual_income, day(result, 26).planned_income,
            day(result, 27).uncertain_income) == (D("2500"), D("500"), D("500"))
    assert day(result, 27).ending_cash == D("2180")  # Uncertain bonus is excluded.
    assert day(result, 15).cash_out == D("0")  # Card use is consumption, not immediate cash.
    assert day(result, 25).cash_out == D("100")  # Card bill is cash, not second consumption.
    assert day(result, 25).actual_cash_out == D("100")
    assert day(result, 26).planned_income == D("500")
    assert day(result, 22).transfer_in == day(result, 22).cash_out == D("50")
    assert result.sources == ("synthetic-manual-example",)
    assert "intraday order is unknown" in result.assumptions[0]
    assert all(item.required_monthly is not None for item in result.goals)
    assert result.investment_proposal == D("500")
    assert result.cash_days[-1].ending_cash == D("1000") + D("2500") + D("500") - D("1820")


def test_gross_income_is_information_not_second_income():
    base = sample_input()
    salary = replace(base.entries[0], gross_income=D("3000"))
    result = calculate_month(replace(base, entries=(salary,) + base.entries[1:]))
    assert day(result, 5).actual_income == D("2500")
    assert result.allocation_margin == D("730")


def test_salary_delay_causes_midmonth_shortage_despite_positive_month_end():
    result = calculate_month(sample_input("cash_gap"))
    assert day(result, 10).ending_cash == D("-400")
    assert day(result, 10).shortage == D("400")
    assert day(result, 20).ending_cash == D("600")
    assert day(result, 20).shortage == D("0")
    assert result.allocation_margin == D("600")


def test_unknown_home_goal_and_protection_do_not_hide_known_cashflow():
    result = calculate_month(sample_input("unknown_goal"))
    home = next(item for item in result.goals if item.goal_id == "home")
    assert home.required_monthly is None
    assert home.missing == ("target_amount", "deadline")
    assert result.allocation_margin is result.unallocated is result.investment_proposal is None
    assert "protected_floor" in result.missing
    assert day(result, 26).ending_cash == D("2180")
    assert "required_monthly=None" in render("unknown_goal")


def test_goal_deadline_shortfall_is_visible_and_blocks_investment_proposal():
    base = sample_input()
    home = replace(base.goals[0], target_amount=D("10000"))
    result = calculate_month(replace(base, goals=(home,) + base.goals[1:]))
    first = next(item for item in result.goals if item.goal_id == "home")
    assert first.shortfall > D("0")
    assert result.investment_proposal is None
    assert any("goal home" in reason for reason in result.shortage_reasons)


def test_zero_income_is_known_deficit_while_missing_income_is_unknown():
    base = sample_input("cash_gap")
    zero = replace(base, entries=(base.entries[0],))
    known = calculate_month(zero)
    assert known.allocation_margin == D("-400")
    assert known.shortage == D("400")
    assert day(known, 10).shortage == D("400")
    unknown = calculate_month(replace(zero, income_complete=False))
    assert unknown.allocation_margin is unknown.shortage is None
    assert day(unknown, 10).shortage is None
    assert "income_records" in unknown.missing


def test_incomplete_obligation_or_policy_keeps_known_entries_but_no_margin():
    data = sample_input("cash_gap")
    missing = calculate_month(replace(data, obligations_complete=False, policy=None))
    assert missing.allocation_margin is None
    assert day(missing, 10).ending_cash == D("-400")
    assert day(missing, 10).shortage is None
    assert {"obligation_records", "budget_policy"} <= set(missing.missing)


def test_midmonth_observed_cash_not_replayed_from_month_start_and_used_not_reallocated():
    base = sample_input()
    # The 26th opening balance already includes all observed activity through the 25th.
    mid = replace(base, balance_date=date(2026, 9, 26),
                  evaluated_at=datetime(2026, 9, 26, 9, tzinfo=timezone.utc),
                  cash_balance=D("1680"),
                  balance_source="synthetic-midmonth-observation")
    result = calculate_month(mid)
    assert day(result, 26).ending_cash == D("2180")
    assert line(result, C.LIVING).used == D("400")
    assert line(result, C.LIVING).remaining == D("0")
    assert result.allocation_margin == D("730")  # Same plan margin after actual cash and use reconcile.
    reserved_rules = tuple(replace(rule, reserved=D("50")) if rule.category is C.FREEDOM
                           else rule for rule in mid.policy.allocations)
    reserved = calculate_month(replace(mid, policy=replace(mid.policy, allocations=reserved_rules)))
    assert line(reserved, C.FREEDOM).remaining == D("100")
    assert reserved.allocation_margin == result.allocation_margin  # Reservation stays inside allocation.


def test_card_payment_for_prior_period_is_cash_obligation_not_second_consumption():
    base = sample_input("cash_gap")
    prior = entry("old-card-bill", 12, K.CARD_PAYMENT, "80", link_id="old-invoice",
                  prior_period_card_payment=True, observed=True)
    result = calculate_month(replace(base, entries=base.entries + (prior,)))
    assert result.allocation_margin == D("520")
    assert day(result, 12).cash_out == D("80")
    assert line(result, C.LIVING).used == D("0")


def test_midmonth_card_charge_already_used_but_future_bill_remains_cash_due():
    base = sample_input()
    mid = replace(base, balance_date=date(2026, 9, 21),
                  evaluated_at=datetime(2026, 9, 21, 9, tzinfo=timezone.utc),
                  cash_balance=D("1780"), balance_source="synthetic-midmonth-observation",
                  entries=tuple(replace(item, observed=False) if item.day > date(2026, 9, 21)
                                and item.observed else item for item in base.entries))
    result = calculate_month(mid)
    assert line(result, C.LIVING).used == D("400")
    assert day(result, 25).cash_out == D("100")
    assert result.allocation_margin == D("730")


@pytest.mark.parametrize("change", [
    lambda d: replace(d, entries=d.entries + (d.entries[0],)),
    lambda d: replace(d, entries=d.entries + (entry("bad-transfer", 23, K.TRANSFER_OUT,
                                                "10", link_id="unpaired"),)),
    lambda d: replace(d, entries=d.entries + (entry("bad-card", 24, K.CARD_PAYMENT,
                                                "10", link_id="card-use"),)),
    lambda d: replace(d, cash_balance=D("NaN")),
    lambda d: replace(d, currency="USD"),
    lambda d: replace(d, entries=(replace(d.entries[0], kind="LOAN"),) + d.entries[1:]),
    lambda d: replace(d, existing_protected=D("1001")),
])
def test_damaged_input_is_rejected_instead_of_becoming_a_false_budget(change):
    with pytest.raises((TypeError, ValueError)):
        calculate_month(change(sample_input()))


def test_same_money_cannot_be_hidden_by_duplicate_goal_rule_or_overallocation():
    base = sample_input()
    duplicate = replace(base.policy, allocations=base.policy.allocations +
                        (Allocation(C.GOAL, D("300"), "home"),))
    with pytest.raises(ValueError, match="duplicate"):
        calculate_month(replace(base, policy=duplicate))
    rules = tuple(replace(item, amount=D("1200")) if item.category is C.GOAL else item
                  for item in base.policy.allocations)
    over = calculate_month(replace(base, policy=replace(base.policy, allocations=rules)))
    assert over.allocation_margin == D("-1170")
    assert over.shortage == D("1170")
    assert any("confirmed funding" in reason for reason in over.shortage_reasons)


def test_existing_reservation_over_allocated_is_not_released_as_unallocated_cash():
    base = sample_input("cash_gap")
    rules = tuple(replace(item, reserved=D("1200")) if item.category is C.FIXED else item
                  for item in base.policy.allocations)
    result = calculate_month(replace(base, policy=replace(base.policy, allocations=rules)))
    assert line(result, C.FIXED).remaining == D("-1200")  # 500 used, 1200 additionally reserved.
    assert result.allocation_margin == D("-100")
    assert result.shortage == D("100")


def test_input_order_and_decimal_context_do_not_change_result():
    base = sample_input()
    first = calculate_month(base)
    reordered = replace(base, entries=tuple(reversed(base.entries)),
                        goals=tuple(reversed(base.goals)),
                        policy=replace(base.policy, allocations=tuple(reversed(base.policy.allocations))))
    with localcontext() as context:
        context.prec = 4
        context.rounding = ROUND_DOWN
        context.traps[Inexact] = True
        second = calculate_month(reordered)
    assert first == second


def test_report_outputs_three_offline_scenarios():
    assert "allocation margin=730" in render("normal")
    assert "end_cash=-400 shortage=400" in render("cash_gap")
    assert "goal HOME: required_monthly=None" in render("unknown_goal")
