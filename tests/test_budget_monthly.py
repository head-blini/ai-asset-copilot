"""BUD-01 manual KRW calculation, evidence and failure boundaries."""

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, Inexact, ROUND_DOWN, localcontext

import pytest

from examples.budget_monthly_offline import MONTH, entry, policy, render, sample_input
from asset_copilot.budget import (Allocation, BudgetCategory as C, BudgetPolicy, EntryKind as K,
                                  Goal, GoalContribution, calculate_month)


D = Decimal


def line(result, category, goal_id=None):
    return next(item for item in result.allocations
                if item.category is category and item.goal_id == goal_id)


def day(result, number):
    return next(item for item in result.cash_days if item.day == date(2026, 9, number))


def focused_policy(amounts, *, reserved=None, goal_rules=()):
    reserved = reserved or {}
    rules = tuple(Allocation(category, D(amounts.get(category, "0")),
                             reserved=D(reserved.get(category, "0")))
                  for category in C if category is not C.GOAL)
    return BudgetPolicy(rules + goal_rules, D("0"), "synthetic-manual-example")


def test_normal_month_preserves_categories_cash_and_provenance():
    data = sample_input()
    result = calculate_month(data)
    assert (result.allocation_margin, result.unallocated, result.shortage) == (D("230"), D("230"), D("0"))
    assert (result.original_plan_margin, result.expected_allocation_margin,
            result.current_cash) == (D("730"), D("730"), D("1680"))
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
    assert all(item.contribution_date_this_month == date(2026, 9, 28)
               and item.end_of_day_funding_gap == D("0") for item in result.goals)
    assert result.investment_proposal == D("500")
    assert result.cash_days[-1].ending_cash == D("1000") + D("2500") + D("500") - D("1820")


def test_gross_income_is_information_not_second_income():
    base = sample_input()
    salary = replace(base.entries[0], gross_income=D("3000"))
    result = calculate_month(replace(base, entries=(salary,) + base.entries[1:]))
    assert day(result, 5).actual_income == D("2500")
    assert result.allocation_margin == D("230")


def test_salary_delay_causes_midmonth_shortage_despite_positive_month_end():
    result = calculate_month(sample_input("cash_gap"))
    assert day(result, 10).ending_cash == D("-400")
    assert day(result, 10).shortage == D("400")
    assert day(result, 20).ending_cash == D("-400")
    assert day(result, 26).ending_cash == D("600")
    assert day(result, 26).shortage == D("0")
    assert (result.allocation_margin, result.expected_allocation_margin) == (D("-400"), D("600"))


def test_unknown_home_goal_and_protection_do_not_hide_known_cashflow():
    result = calculate_month(sample_input("unknown_goal"))
    home = next(item for item in result.goals if item.goal_id == "home")
    assert home.required_monthly is None
    assert home.missing == ("target_amount", "deadline")
    assert result.allocation_margin is result.unallocated is result.investment_proposal is None
    assert "protected_floor" in result.missing
    assert "goal_contribution_confirmation:retirement" not in result.missing
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


def test_goal_priority_prevents_same_cash_from_funding_two_payment_days():
    base = sample_input()
    rules = tuple(replace(item, amount=D("1500") if item.goal_id == "home" else D("1000"))
                  if item.category is C.GOAL else item for item in base.policy.allocations)
    result = calculate_month(replace(base, policy=replace(base.policy, allocations=rules)))
    home, retirement = result.goals
    assert home.end_of_day_funding_gap == D("0")
    assert retirement.end_of_day_funding_gap == D("520")
    assert result.investment_proposal is None


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
    assert result.allocation_margin == D("230")  # The unconfirmed 26th receipt is not cash yet.
    assert result.original_plan_margin is None  # No opening-month balance was supplied.
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
    assert (result.allocation_margin, result.expected_allocation_margin) == (D("-480"), D("520"))
    assert day(result, 12).cash_out == D("80")
    assert line(result, C.LIVING).used == D("0")


def test_midmonth_card_charge_already_used_but_future_bill_remains_cash_due():
    base = sample_input()
    mid = replace(base, balance_date=date(2026, 9, 21),
                  evaluated_at=datetime(2026, 9, 21, 9, tzinfo=timezone.utc),
                  cash_balance=D("1780"), balance_source="synthetic-midmonth-observation",
                  entries=tuple(replace(item, recorded_at=datetime(2026, 9, 21, 9,
                                                                  tzinfo=timezone.utc),
                                        observed=False if item.day > date(2026, 9, 21)
                                        else item.observed) for item in base.entries))
    result = calculate_month(mid)
    assert line(result, C.LIVING).used == D("400")
    assert day(result, 25).cash_out == D("100")
    assert (result.allocation_margin, result.expected_allocation_margin) == (D("230"), D("730"))


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
    assert over.allocation_margin == D("-1670")
    assert over.shortage == D("1670")
    assert over.expected_allocation_margin == D("-1170")
    assert any("confirmed funding" in reason for reason in over.shortage_reasons)


def test_existing_reservation_over_allocated_is_not_released_as_unallocated_cash():
    base = sample_input("cash_gap")
    rules = tuple(replace(item, reserved=D("1200")) if item.category is C.FIXED else item
                  for item in base.policy.allocations)
    result = calculate_month(replace(base, policy=replace(base.policy, allocations=rules)))
    assert line(result, C.FIXED).remaining == D("-1200")  # 500 used, 1200 additionally reserved.
    assert result.allocation_margin == D("-1600")
    assert result.shortage == D("1600")
    assert result.expected_allocation_margin == D("-600")


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
    assert "current allocation margin=230 expected margin=730" in render("normal")
    assert "end_cash=-400 shortage=400" in render("cash_gap")
    assert "goal HOME: required_monthly=None" in render("unknown_goal")


def test_month_start_and_midmonth_observation_agree_on_current_overrun():
    start = sample_input("overspend")
    mid = replace(start, balance_date=date(2026, 9, 11), cash_balance=D("100"))
    first, second = calculate_month(start), calculate_month(mid)
    assert first.original_plan_margin == D("200")
    assert second.original_plan_margin is None
    assert (first.allocation_margin, first.unallocated, first.shortage,
            first.investment_proposal) == (D("-600"), D("0"), D("600"), None)
    assert (first.allocation_margin, first.unallocated, first.shortage,
            first.investment_proposal) == (second.allocation_margin, second.unallocated,
                                            second.shortage, second.investment_proposal)


def test_additional_use_and_reservation_never_create_free_cash():
    base = sample_input("extra_reservation")
    free = calculate_month(replace(base, policy=replace(base.policy, allocations=tuple(
        replace(rule, reserved=D("0")) if rule.category is C.LIVING else rule
        for rule in base.policy.allocations))))
    reserved = calculate_month(base)
    more_used = calculate_month(replace(base, entries=(replace(base.entries[0], amount=D("600")),)))
    more_reserved = calculate_month(replace(base, policy=replace(base.policy, allocations=tuple(
        replace(rule, reserved=D("800")) if rule.category is C.LIVING else rule
        for rule in base.policy.allocations))))
    assert (free.unallocated, reserved.unallocated, more_used.unallocated,
            more_reserved.unallocated) == (D("700"), D("0"), D("0"), D("0"))
    assert (reserved.shortage, more_used.shortage, more_reserved.shortage) == (
        D("0"), D("100"), D("100"))
    assert line(reserved, C.LIVING).reserved == D("700")
    assert day(reserved, 10).available_cash == D("700")  # Current reservation has no past start date.
    assert day(reserved, 25).available_cash == D("0")


def test_linked_future_payment_consumes_one_reservation_without_double_charge():
    base = sample_input("extra_reservation")
    due = replace(entry("reserved-living-due", 26, K.CASH_SPEND, "700", category=C.LIVING),
                  reservation_draw=D("700"))
    linked = calculate_month(replace(base, entries=base.entries + (due,)))
    separate = calculate_month(replace(base, entries=base.entries +
                                       (replace(due, reservation_draw=D("0")),)))
    assert day(linked, 10).available_cash == D("700")
    assert day(linked, 25).available_cash == D("0")
    assert (day(linked, 26).ending_cash, day(linked, 26).available_cash) == (D("0"), D("0"))
    assert day(separate, 26).available_cash == D("-700")
    assert linked.allocation_margin == D("0")
    assert separate.allocation_margin == D("-700")
    with pytest.raises(ValueError, match="reservation_draw exceeds"):
        calculate_month(replace(base, entries=base.entries +
                                (replace(due, amount=D("800"), reservation_draw=D("800")),)))


def test_investment_plan_is_not_reproposed_after_full_reservation():
    base = sample_input("extra_reservation")
    rules = tuple(replace(rule, amount=D("500"), reserved=D("500"))
                  if rule.category is C.US_INVEST else replace(rule, amount=D("0"),
                                                                reserved=D("0"))
                  for rule in base.policy.allocations)
    result = calculate_month(replace(base, entries=(), cash_balance=D("1000"),
                                     policy=replace(base.policy, allocations=rules)))
    assert line(result, C.US_INVEST).planned == D("500")
    assert line(result, C.US_INVEST).remaining == D("0")
    assert result.investment_proposal == D("0")


def test_future_expense_over_plan_already_reduces_current_funding():
    base = sample_input("overspend")
    planned = replace(base.entries[0], day=date(2026, 9, 26), observed=False)
    result = calculate_month(replace(base, entries=(planned,)))
    assert result.current_cash == D("1000")
    assert result.allocation_margin == D("-600")
    assert result.shortage == D("600")
    assert result.investment_proposal is None
    assert day(result, 26).ending_cash == D("100")


def test_overdue_salary_is_excluded_without_hiding_observed_income():
    base = sample_input("overdue_salary")
    pending = calculate_month(base)
    assert pending.original_plan_margin == D("1500")
    assert pending.allocation_margin == D("500")
    assert pending.investment_proposal is None
    assert day(pending, 20).ending_cash == D("1000")
    assert day(pending, 20).overdue_income == D("1000")
    assert "income_unconfirmed:unconfirmed-salary" in pending.missing
    confirmed = replace(base.entries[0], kind=K.INCOME_ACTUAL, observed=True)
    actual = calculate_month(replace(base, entries=(confirmed,)))
    assert actual.allocation_margin == D("1500")
    assert actual.investment_proposal == D("500")
    assert day(actual, 20).actual_income == D("1000")
    mid = calculate_month(replace(base, balance_date=date(2026, 9, 21),
                                  cash_balance=D("1000")))
    assert (mid.allocation_margin, mid.investment_proposal) == (
        pending.allocation_margin, pending.investment_proposal)


def test_goal_due_date_counts_only_future_opportunities_and_actual_savings():
    base = sample_input("goal_conflict")
    goal = replace(base.goals[0], target_amount=D("1200"), deadline=date(2026, 11, 30))
    late = replace(base, evaluated_at=datetime(2026, 9, 25, 9, tzinfo=timezone.utc),
                   goals=(goal,))
    pending = calculate_month(late).goals[0]
    assert (pending.contribution_dates, pending.required_monthly,
            pending.contribution_status) == (2, D("600"), "OVERDUE_UNCONFIRMED")
    paid = replace(goal, saved_amount=D("300"), contributions=(GoalContribution(
        date(2026, 9, 5), D("300"), "synthetic-manual-example",
        datetime(2026, 9, 25, 9, tzinfo=timezone.utc), "FREE_CASH"),))
    actual = calculate_month(replace(late, goals=(paid,))).goals[0]
    assert (actual.contribution_dates, actual.required_monthly,
            actual.contribution_status) == (2, D("450"), "PARTIAL")
    complete = replace(goal, saved_amount=D("800"), contributions=(GoalContribution(
        date(2026, 9, 5), D("800"), "synthetic-manual-example",
        datetime(2026, 9, 25, 9, tzinfo=timezone.utc), "FREE_CASH"),))
    confirmed = calculate_month(replace(late, goals=(complete,))).goals[0]
    assert (confirmed.contribution_dates, confirmed.required_monthly,
            confirmed.contribution_status) == (2, D("200"), "OBSERVED")


def test_partial_goal_payment_does_not_count_again_as_future_proposal():
    base = sample_input("goal_conflict")
    paid = replace(base.goals[0], target_amount=D("1000"), saved_amount=D("200"),
                   contributions=(GoalContribution(date(2026, 9, 1), D("200"),
                                                   "synthetic-partial-payment",
                                                   base.evaluated_at, "FREE_CASH"),))
    rules = tuple(replace(rule, amount=D("500")) if rule.category is C.GOAL else rule
                  for rule in base.policy.allocations)
    result = calculate_month(replace(base, goals=(paid,),
                                     protected_contributions_in_balance=(),
                                     policy=replace(base.policy, allocations=rules)))
    assert (result.goals[0].required_monthly, result.goals[0].shortfall,
            result.goals[0].contribution_status) == (D("800"), D("500"), "PARTIAL")


def test_goal_lock_persists_after_due_date_without_changing_total_cash():
    result = calculate_month(sample_input("goal_conflict"))
    assert result.goals[0].end_of_day_funding_gap == D("0")
    assert (day(result, 10).ending_cash, day(result, 10).shortage,
            day(result, 10).available_cash, day(result, 10).available_shortage) == (
                D("500"), D("0"), D("-300"), D("300"))
    assert day(result, 20).available_cash == D("700")
    assert any("2026-09-10 available cash" in reason and "300" in reason
               for reason in result.shortage_reasons)


def test_goal_cannot_use_existing_protected_cash():
    base = sample_input("goal_conflict")
    result = calculate_month(replace(base, existing_protected=D("500"),
                                     policy=replace(base.policy, protected_floor=D("500"))))
    assert result.goals[0].end_of_day_funding_gap == D("300")
    assert day(result, 5).ending_cash == D("1000")
    assert day(result, 5).available_cash == D("-300")
    assert any("goal home lacks 300" in reason for reason in result.shortage_reasons)


def test_goal_priority_follows_dates_and_protection_is_counted_once():
    base = sample_input("goal_conflict")
    second = replace(base.goals[0], id="second", kind="RETIREMENT", target_amount=D("200"),
                     contribution_day=8, priority=1)
    first = replace(base.goals[0], target_amount=D("300"), priority=2)
    rules = tuple(replace(rule, amount=D("100") if rule.category is C.LIVING else D("0"))
                  for rule in base.policy.allocations if rule.category is not C.GOAL)
    rules += (Allocation(C.GOAL, D("300"), "home"),
              Allocation(C.GOAL, D("200"), "second"))
    data = replace(base, cash_balance=D("600"), existing_protected=D("100"),
                   entries=(base.entries[0],), goals=(second, first),
                   policy=BudgetPolicy(rules, D("100"), "synthetic-manual-example"))
    result = calculate_month(data)
    assert {goal.goal_id: goal.end_of_day_funding_gap for goal in result.goals} == {
        "home": D("0"), "second": D("0")}
    assert day(result, 10).ending_cash == D("100")
    assert day(result, 10).available_cash == D("-500")


def test_goal_reservation_and_observed_savings_are_each_protected_once():
    base = sample_input("goal_conflict")
    reserved_rules = tuple(replace(rule, reserved=D("800")) if rule.category is C.GOAL
                           else rule for rule in base.policy.allocations)
    reserved = calculate_month(replace(base, policy=replace(base.policy,
                                                            allocations=reserved_rules)))
    assert day(reserved, 5).available_cash == D("200")
    assert reserved.goals[0].end_of_day_funding_gap == D("0")
    paid = replace(base.goals[0], saved_amount=D("800"), contributions=(GoalContribution(
        date(2026, 9, 5), D("800"), "synthetic-goal-payment",
        datetime(2026, 9, 25, 9, tzinfo=timezone.utc), "FREE_CASH"),))
    observed = calculate_month(replace(base, evaluated_at=datetime(2026, 9, 25, 9,
                                                                    tzinfo=timezone.utc),
                                       existing_protected=D("0"), goals=(paid,),
                                       entries=(replace(base.entries[0], observed=True,
                                                        recorded_at=datetime(2026, 9, 25, 9,
                                                                             tzinfo=timezone.utc)),
                                                base.entries[1])))
    assert observed.current_cash == D("500")
    assert day(observed, 10).available_cash == D("-300")
    assert line(observed, C.GOAL, "home").used == D("800")
    assert "synthetic-goal-payment" in observed.sources


def test_observed_goal_saving_does_not_rewrite_earlier_available_cash():
    base = sample_input("goal_conflict")
    paid = replace(base.goals[0], contribution_day=20, saved_amount=D("800"),
                   contributions=(GoalContribution(date(2026, 9, 20), D("800"),
                                                   "synthetic-goal-payment",
                                                   datetime(2026, 9, 25, 9,
                                                            tzinfo=timezone.utc), "FREE_CASH"),))
    data = replace(base, evaluated_at=datetime(2026, 9, 25, 9, tzinfo=timezone.utc),
                   cash_balance=D("2000"), goals=(paid,),
                   entries=(replace(base.entries[0], observed=True,
                                    recorded_at=datetime(2026, 9, 25, 9,
                                                         tzinfo=timezone.utc)),))
    result = calculate_month(data)
    assert day(result, 10).available_cash == D("1500")
    assert day(result, 20).available_cash == D("700")
    assert result.goals[0].contribution_status == "OBSERVED"


def test_observed_card_charge_has_one_future_cash_due_and_no_second_consumption():
    base = sample_input()
    charge = next(item for item in base.entries if item.id == "card-use")
    payment = next(item for item in base.entries if item.id == "card-bill")
    rules = tuple(replace(rule, amount=D("100") if rule.category is C.LIVING else D("0"))
                  for rule in base.policy.allocations if rule.category is not C.GOAL)
    data = replace(base, cash_balance=D("200"), existing_protected=D("0"),
                   entries=(charge, replace(payment, day=date(2026, 9, 26), observed=False)),
                   goals=(), policy=BudgetPolicy(rules, D("0"), "synthetic-manual-example"))
    start = calculate_month(data)
    mid = calculate_month(replace(data, balance_date=date(2026, 9, 16)))
    assert start.allocation_margin == mid.allocation_margin == D("100")
    assert day(start, 26).ending_cash == D("100")
    assert line(start, C.LIVING).used == D("100")


def test_overdue_obligation_is_unknown_while_observed_deficit_is_known():
    base = sample_input("cash_gap")
    unconfirmed = replace(base.entries[0], observed=False)
    unknown = calculate_month(replace(base, entries=(unconfirmed,)))
    known = calculate_month(base)
    assert unknown.allocation_margin is unknown.shortage is None
    assert day(unknown, 10).ending_cash == D("100")
    assert "obligation_unconfirmed:rent" in unknown.missing
    assert (known.allocation_margin, known.expected_allocation_margin) == (D("-400"), D("600"))
    assert day(known, 10).shortage == D("400")


def test_kst_evaluation_boundary_and_record_time_are_respected():
    base = sample_input("overdue_salary")
    before = datetime(2026, 9, 24, 14, 59, tzinfo=timezone.utc)  # Sep 24 23:59 KST
    after = datetime(2026, 9, 24, 15, 1, tzinfo=timezone.utc)  # Sep 25 00:01 KST
    salary = replace(base.entries[0], day=date(2026, 9, 25), recorded_at=before)
    future = calculate_month(replace(base, evaluated_at=before, entries=(salary,)))
    today = calculate_month(replace(base, evaluated_at=after, entries=(salary,)))
    assert (future.allocation_margin, future.expected_allocation_margin) == (D("500"), D("1500"))
    assert today.allocation_margin == D("500")
    with pytest.raises(ValueError, match="recorded after evaluation"):
        calculate_month(replace(base, evaluated_at=before))
    kst = timezone(timedelta(hours=9))
    observed = replace(salary, kind=K.INCOME_ACTUAL, observed=True,
                       recorded_at=datetime(2026, 9, 25, 0, 1, tzinfo=kst))
    assert calculate_month(replace(base, evaluated_at=after, entries=(observed,))).allocation_margin == D("1500")


def test_goal_gap_and_overrun_messages_preserve_large_fractional_decimals():
    base = sample_input("goal_conflict")
    amount = D("12345678901234567890.123456789")
    goal = replace(base.goals[0], target_amount=amount)
    rules = tuple(replace(rule, amount=amount) if rule.category is C.GOAL else rule
                  for rule in base.policy.allocations)
    data = replace(base, cash_balance=D("0"), goals=(goal,),
                   policy=replace(base.policy, allocations=rules))
    first = calculate_month(data)
    reordered = replace(data, entries=tuple(reversed(data.entries)),
                        policy=replace(data.policy, allocations=tuple(reversed(rules))))
    with localcontext() as context:
        context.prec = 4
        context.rounding = ROUND_DOWN
        context.traps[Inexact] = True
        second = calculate_month(reordered)
    assert first == second
    assert first.goals[0].end_of_day_funding_gap == amount
    assert any(str(amount) in reason for reason in first.shortage_reasons)


@pytest.mark.parametrize("amount", ["12345", "12345678901234567890.123456789"])
def test_large_decimal_shortages_and_messages_ignore_caller_context(amount):
    base = sample_input("overspend")
    spent = replace(base.entries[0], amount=D(amount))
    rules = tuple(replace(rule, amount=D(amount) if rule.category is C.LIVING else D("0"))
                  for rule in base.policy.allocations)
    data = replace(base, cash_balance=D("0"), entries=(spent,),
                   policy=replace(base.policy, allocations=rules))
    first = calculate_month(data)
    with localcontext() as context:
        context.prec = 4
        context.rounding = ROUND_DOWN
        context.traps[Inexact] = True
        second = calculate_month(data)
    assert first == second
    assert (first.shortage, day(first, 10).shortage) == (D(amount), D(amount))
    assert any(amount in reason for reason in first.shortage_reasons)


@pytest.mark.parametrize("settlement", ("cash", "unscheduled", "scheduled", "paid"))
def test_card_consumption_retains_one_cash_obligation_until_payment(settlement):
    base = sample_input("overdue_salary")
    spending = entry("living-use", 15,
                     K.CASH_SPEND if settlement == "cash" else K.CARD_CHARGE,
                     "900", category=C.LIVING, observed=True)
    entries = (spending,)
    if settlement in ("scheduled", "paid"):
        entries += (entry("card-bill", 28 if settlement == "scheduled" else 20,
                          K.CARD_PAYMENT, "900", link_id=spending.id,
                          observed=settlement == "paid"),)
    result = calculate_month(replace(base, entries=entries, goals=(),
                                     policy=focused_policy({C.LIVING: "900", C.US_INVEST: "500"})))
    assert line(result, C.LIVING).used == D("900")
    assert result.allocation_margin == D("-400")
    assert result.shortage == D("400")
    assert result.investment_proposal is None
    assert result.unpaid_card_due == (D("900") if settlement in ("unscheduled", "scheduled")
                                      else D("0"))
    assert day(result, 28).ending_cash == (D("1000") if settlement == "unscheduled"
                                           else D("100"))
    assert day(result, 28).available_cash == D("100")
    if settlement == "unscheduled":
        assert "card_payment_date:living-use" in result.missing
        assert any("living-use" in reason for reason in result.shortage_reasons)


def test_undated_card_due_blocks_even_with_positive_margin_until_schedule_is_known():
    base = sample_input("overdue_salary")
    charge = entry("undated-card", 15, K.CARD_CHARGE, "900", category=C.LIVING,
                   observed=True)
    result = calculate_month(replace(base, cash_balance=D("2000"), entries=(charge,),
                                     policy=focused_policy({C.LIVING: "900", C.US_INVEST: "500"})))
    assert (result.current_cash, result.unpaid_card_due, result.allocation_margin) == (
        D("2000"), D("900"), D("600"))
    assert result.investment_proposal is None
    assert "card_payment_date:undated-card" in result.missing
    assert any("supply its payment date" in reason for reason in result.shortage_reasons)


@pytest.mark.parametrize("reserved", ("0", "200"))
@pytest.mark.parametrize("past_shortage", (False, True))
@pytest.mark.parametrize("balance_day", (1, 11, 25))
def test_current_investment_decision_ignores_balance_start_and_historical_gaps(
        reserved, past_shortage, balance_day):
    base = sample_input("overdue_salary")
    spent = (entry("past-living", 5, K.CASH_SPEND, "150", category=C.LIVING,
                   observed=True),) if past_shortage else ()
    income = entry("salary", 10, K.INCOME_ACTUAL, "1050" if past_shortage else "900",
                   observed=True)
    data = replace(base, balance_date=date(2026, 9, balance_day),
                   cash_balance=D("100") if balance_day == 1 else D("1000"),
                   entries=spent + (income,), goals=(),
                   policy=focused_policy({C.LIVING: "200", C.US_INVEST: "500"},
                                         reserved={C.LIVING: reserved}))
    result = calculate_month(data)
    assert result.current_cash == D("1000")
    assert result.allocation_margin == (D("300") if reserved == "200" else
                                        D("450") if past_shortage else D("300"))
    assert result.investment_proposal == D("500")
    if balance_day == 1 and (past_shortage or reserved == "200"):
        assert day(result, 5).available_cash == (D("-50") if past_shortage else D("100"))


@pytest.mark.parametrize("observed,paid,target,expected_proposal", (
    (True, "800", "800", D("500")),
    (True, "800", "1200", D("500")),
    (True, "300", "800", None),
    (False, "0", "800", None),
    (True, "300", "300", D("500")),
    (False, "0", "0", D("500")),
))
def test_goal_funding_check_separates_completed_partial_and_unconfirmed(
        observed, paid, target, expected_proposal):
    base = sample_input("overdue_salary")
    contribution = (GoalContribution(date(2026, 9, 5), D(paid),
                                     "synthetic-goal-payment", base.evaluated_at,
                                     "FREE_CASH"),) if observed else ()
    goal = Goal("home", "HOME", D(target), date(2026, 10, 30), D(paid), 5, 1,
                "synthetic-manual-example", contribution)
    data = replace(base, cash_balance=D("3000"), entries=(), goals=(goal,),
                   policy=focused_policy({C.US_INVEST: "500"},
                                         goal_rules=(Allocation(C.GOAL, D("800"), "home"),)))
    result = calculate_month(data)
    assert result.goals[0].contribution_status == (
        "OBSERVED" if observed and paid == "800" else
        "PARTIAL" if observed else "OVERDUE_UNCONFIRMED")
    assert result.goals[0].end_of_day_funding_gap is None
    assert result.goals[0].funding_check_status == (
        "NOT_REQUIRED" if target == paid or observed and paid == "800" else "UNKNOWN")
    assert result.investment_proposal == expected_proposal
    if expected_proposal is None:
        assert any("goal home" in reason for reason in result.shortage_reasons)
        assert "goal_contribution_confirmation:home" in result.missing


def protected_goal_case(*, balance_day=1, observed=False, included=None):
    base = sample_input("overdue_salary")
    contribution = (GoalContribution(date(2026, 9, 5), D("300"),
                                     "synthetic-goal-payment", base.evaluated_at,
                                     "FREE_CASH"),) if observed else ()
    goal = Goal("home", "HOME", D("300"), date(2026, 9, 30),
                D("300") if observed else D("0"), 5, 1,
                "synthetic-manual-example", contribution)
    return replace(base, evaluated_at=(base.evaluated_at if observed else
                   datetime(2026, 9, 1, 0, tzinfo=timezone.utc)),
                   balance_date=date(2026, 9, balance_day),
                   cash_balance=D("1000"), existing_protected=D("800") if balance_day == 25
                   else D("500"), entries=(), goals=(goal,),
                   policy=replace(focused_policy({C.US_INVEST: "500"},
                                                  goal_rules=(Allocation(C.GOAL, D("300"), "home"),)),
                                  protected_floor=D("500")),
                   protected_contributions_in_balance=included)


def test_new_goal_saving_replaces_plan_without_releasing_prior_protection():
    planned = calculate_month(protected_goal_case())
    observed = calculate_month(protected_goal_case(observed=True))
    assert (planned.allocation_margin, planned.shortage, planned.investment_proposal) == (
        D("-300"), D("300"), None)
    assert (observed.allocation_margin, observed.shortage, observed.investment_proposal) == (
        D("-300"), D("300"), None)
    assert day(observed, 25).ending_cash == D("1000")
    assert day(observed, 25).available_cash == D("200")
    assert observed.goals[0].funding_check_status == "NOT_REQUIRED"


def test_midmonth_protected_snapshot_includes_prior_goal_once():
    mid = calculate_month(protected_goal_case(balance_day=25, observed=True,
                              included=(("home", date(2026, 9, 5)),)))
    start = calculate_month(protected_goal_case(observed=True))
    assert (mid.current_cash, mid.allocation_margin, mid.shortage,
            mid.investment_proposal, day(mid, 25).available_cash) == (
                start.current_cash, start.allocation_margin, start.shortage,
                start.investment_proposal, day(start, 25).available_cash)


def test_two_new_goal_contributions_each_protect_once():
    base = protected_goal_case(observed=True)
    second = Goal("retirement", "RETIREMENT", D("200"), date(2026, 9, 30),
                  D("200"), 7, 2, "synthetic-manual-example",
                  (GoalContribution(date(2026, 9, 7), D("200"),
                                    "synthetic-goal-payment", base.evaluated_at, "FREE_CASH"),))
    data = replace(base, goals=base.goals + (second,),
                   policy=replace(base.policy, allocations=base.policy.allocations +
                                  (Allocation(C.GOAL, D("200"), "retirement"),)))
    result = calculate_month(data)
    assert (result.allocation_margin, result.shortage, result.investment_proposal) == (
        D("-500"), D("500"), None)
    assert (day(result, 4).available_cash, day(result, 5).available_cash,
            day(result, 7).available_cash) == (D("500"), D("200"), D("0"))
    mid = calculate_month(replace(data, balance_date=date(2026, 9, 25),
                                  existing_protected=D("1000"),
                                  protected_contributions_in_balance=(
                                      ("home", date(2026, 9, 5)),
                                      ("retirement", date(2026, 9, 7)))))
    assert (mid.allocation_margin, mid.shortage,
            day(mid, 25).available_cash) == (D("-500"), D("500"), D("0"))


def test_future_goal_check_uses_prior_protection_and_new_savings_together():
    base = protected_goal_case(observed=True)
    second = Goal("retirement", "RETIREMENT", D("300"), date(2026, 9, 30),
                  D("0"), 27, 2, "synthetic-manual-example")
    data = replace(base, goals=base.goals + (second,),
                   policy=replace(base.policy, allocations=base.policy.allocations +
                                  (Allocation(C.GOAL, D("300"), "retirement"),)))
    result = calculate_month(data)
    retirement = next(goal for goal in result.goals if goal.goal_id == "retirement")
    assert retirement.funding_check_status == "CHECKED"
    assert retirement.end_of_day_funding_gap == D("100")
    assert day(result, 27).available_cash == D("-100")
    assert result.investment_proposal is None


def test_same_day_balance_requires_explicit_goal_inclusion():
    base = protected_goal_case(balance_day=1, observed=True)
    same_day = replace(base.goals[0], contribution_day=1,
                       contributions=(replace(base.goals[0].contributions[0],
                                              day=date(2026, 9, 1)),))
    data = replace(base, balance_date=date(2026, 9, 1), goals=(same_day,))
    with pytest.raises(ValueError, match="protected contribution inclusion"):
        calculate_month(data)
    excluded = calculate_month(replace(data, protected_contributions_in_balance=()))
    included = calculate_month(replace(data, existing_protected=D("800"),
                                       protected_contributions_in_balance=(("home", date(2026, 9, 1)),)))
    assert excluded.allocation_margin == included.allocation_margin == D("-300")


def test_protected_snapshot_rejects_missing_duplicate_or_future_inclusion():
    data = protected_goal_case(balance_day=25, observed=True)
    with pytest.raises(ValueError, match="protected contribution inclusion"):
        calculate_month(data)
    with pytest.raises(ValueError, match="protected contribution inclusion"):
        calculate_month(replace(data, protected_contributions_in_balance=()))
    key = ("home", date(2026, 9, 5))
    with pytest.raises(ValueError, match="protected contribution inclusion"):
        calculate_month(replace(data, protected_contributions_in_balance=(key, key)))
    with pytest.raises(ValueError, match="protected contribution inclusion"):
        calculate_month(replace(data, protected_contributions_in_balance=(("home", date(2026, 9, 28)),)))
    with pytest.raises(ValueError, match="exceeds protected balance"):
        calculate_month(replace(data, existing_protected=D("200"),
                                protected_contributions_in_balance=(key,)))


def test_goal_contribution_cannot_relabel_already_protected_cash():
    data = protected_goal_case(observed=True)
    changed = replace(data.goals[0], contributions=(
        replace(data.goals[0].contributions[0], protection_source="PROTECTED_REALLOCATION"),))
    with pytest.raises(ValueError, match="reallocation is unsupported"):
        calculate_month(replace(data, goals=(changed,)))
    missing = replace(data.goals[0], contributions=(
        replace(data.goals[0].contributions[0], protection_source=None),))
    with pytest.raises(ValueError, match="protection_source must be FREE_CASH"):
        calculate_month(replace(data, goals=(missing,)))


def test_protected_floor_is_a_minimum_for_same_total_not_an_extra_reserve():
    data = protected_goal_case(observed=True)
    result = calculate_month(replace(data, existing_protected=D("100"),
                                     policy=replace(data.policy, protected_floor=D("500"))))
    assert day(result, 25).available_cash == D("500")
    assert result.allocation_margin == D("0")
