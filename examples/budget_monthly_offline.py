"""Synthetic manual KRW examples; no account, provider, AI or order access.

Run: python examples/budget_monthly_offline.py --scenario all
"""

import argparse
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal

from asset_copilot.budget import (Allocation, BudgetCategory as C, BudgetInput, BudgetPolicy,
                                  CashEntry, EntryKind as K, Goal, calculate_month)


D = Decimal
MONTH = date(2026, 9, 1)
STAMP = datetime(2026, 9, 25, 9, tzinfo=timezone.utc)
SOURCE = "synthetic-manual-example"


def entry(id: str, day: int, kind: K, amount: str, *, category: C | None = None,
          link_id: str | None = None, observed: bool = False,
          prior_period_card_payment: bool = False,
          recorded_at: datetime = STAMP) -> CashEntry:
    return CashEntry(id, date(2026, 9, day), kind, D(amount), SOURCE, recorded_at,
                     category, link_id, prior_period_card_payment, observed=observed)


def policy(*, fixed: str = "1200", living: str = "400", freedom: str = "150",
           protected_floor: str | None = "200", with_goals: bool = True) -> BudgetPolicy:
    values = ((C.FIXED, fixed), (C.LIVING, living), (C.FREEDOM, freedom),
              (C.DEBT_PRINCIPAL, "200"), (C.DEBT_COST, "20"), (C.EMERGENCY, "100"),
              (C.US_INVEST, "400"), (C.KR_STRATEGY, "100"))
    rules = [Allocation(category, D(amount)) for category, amount in values]
    if with_goals:
        rules += [Allocation(C.GOAL, D("300"), "home"),
                  Allocation(C.GOAL, D("200"), "retirement")]
    return BudgetPolicy(tuple(rules), D(protected_floor) if protected_floor is not None else None,
                        SOURCE)


def sample_input(scenario: str = "normal") -> BudgetInput:
    if scenario not in ("normal", "cash_gap", "unknown_goal", "overspend",
                        "extra_reservation", "overdue_salary", "goal_conflict"):
        raise ValueError("unknown scenario")
    def zero_policy(values=None, reservations=None, goals=()):
        values = values or {}
        reservations = reservations or {}
        rules = tuple(Allocation(category, D(values.get(category, "0")),
                                 reserved=D(reservations.get(category, "0")))
                      for category in C if category is not C.GOAL)
        return BudgetPolicy(rules + goals, D("0"), SOURCE)
    if scenario == "cash_gap":
        gap_policy = zero_policy({C.FIXED: "500"})
        return BudgetInput(MONTH, STAMP, MONTH, D("100"), D("0"), SOURCE,
                           (entry("rent", 10, K.CASH_SPEND, "500", category=C.FIXED, observed=True),
                            entry("late-salary", 26, K.INCOME_PLANNED, "1000")),
                           (), gap_policy, True, True)
    if scenario == "overspend":
        return BudgetInput(MONTH, STAMP, MONTH, D("1000"), D("0"), SOURCE,
                           (entry("living-overrun", 10, K.CASH_SPEND, "900", category=C.LIVING,
                                  observed=True),), (),
                           zero_policy({C.LIVING: "100", C.US_INVEST: "700"}), True, True)
    if scenario == "extra_reservation":
        return BudgetInput(MONTH, STAMP, MONTH, D("1200"), D("0"), SOURCE,
                           (entry("living-used", 10, K.CASH_SPEND, "500", category=C.LIVING,
                                  observed=True),), (),
                           zero_policy({C.LIVING: "500"}, {C.LIVING: "700"}), True, True)
    if scenario == "overdue_salary":
        return BudgetInput(MONTH, STAMP, MONTH, D("1000"), D("0"), SOURCE,
                           (entry("unconfirmed-salary", 20, K.INCOME_PLANNED, "1000"),), (),
                           zero_policy({C.US_INVEST: "500"}), True, True)
    if scenario == "goal_conflict":
        early = datetime(2026, 9, 1, tzinfo=timezone.utc)
        home = Goal("home", "HOME", D("800"), date(2026, 9, 30), D("0"), 5, 1, SOURCE)
        return BudgetInput(MONTH, early, MONTH, D("1000"), D("0"), SOURCE,
                           (entry("living-due", 10, K.CASH_SPEND, "500", category=C.LIVING,
                                  recorded_at=early),
                            entry("salary-due", 20, K.INCOME_PLANNED, "1000", recorded_at=early)),
                           (home,), zero_policy({C.LIVING: "500"}, goals=(Allocation(C.GOAL,
                                                                                     D("800"), "home"),)),
                           True, True)
    goals = (Goal("home", "HOME", D("4000"), date(2027, 9, 30), D("1000"), 28, 1, SOURCE),
             Goal("retirement", "RETIREMENT", D("3000"), date(2027, 9, 30),
                  D("500"), 28, 2, SOURCE))
    entries = (
        entry("salary", 5, K.INCOME_ACTUAL, "2500", observed=True),
        entry("rent", 10, K.CASH_SPEND, "1200", category=C.FIXED, observed=True),
        entry("groceries", 12, K.CASH_SPEND, "300", category=C.LIVING, observed=True),
        entry("card-use", 15, K.CARD_CHARGE, "100", category=C.LIVING, observed=True),
        entry("principal", 20, K.DEBT_PRINCIPAL, "200", observed=True),
        entry("interest", 20, K.DEBT_COST, "20", observed=True),
        entry("move-out", 22, K.TRANSFER_OUT, "50", link_id="internal-1", observed=True),
        entry("move-in", 22, K.TRANSFER_IN, "50", link_id="internal-1", observed=True),
        entry("card-bill", 25, K.CARD_PAYMENT, "100", link_id="card-use", observed=True),
        entry("planned-side-income", 26, K.INCOME_PLANNED, "500"),
        entry("uncertain-bonus", 27, K.INCOME_UNCERTAIN, "500"),
    )
    if scenario == "unknown_goal":
        goals = (replace(goals[0], target_amount=None, deadline=None), goals[1])
        return BudgetInput(MONTH, STAMP, MONTH, D("1000"), D("200"), SOURCE,
                           entries, goals, policy(protected_floor=None, with_goals=False), True, True)
    return BudgetInput(MONTH, STAMP, MONTH, D("1000"), D("200"), SOURCE,
                       entries, goals, policy(), True, True)


def render(scenario: str) -> str:
    result = calculate_month(sample_input(scenario))
    lines = [f"[{scenario}] 2026-09 KRW budget proposal (not approval, transfer or order)",
             f"  evaluated_at={result.evaluated_at.isoformat()} balance_date={result.balance_date}",
             f"  original plan margin={result.original_plan_margin} current_cash={result.current_cash} current allocation margin={result.allocation_margin} expected margin={result.expected_allocation_margin} unallocated={result.unallocated} shortage={result.shortage} investment_proposal={result.investment_proposal}",
             "  goal monthly amounts below are rounded to 0.01 KRW for display; API Decimal is unrounded"]
    for item in result.allocations:
        label = item.category.value + (f":{item.goal_id}" if item.goal_id else "")
        lines.append(f"  {label}: planned={item.planned} used={item.used} reserved={item.reserved} remaining={item.remaining}")
    for goal in result.goals:
        required = f"{goal.required_monthly:.2f}" if goal.required_monthly is not None else "None"
        shortfall = f"{goal.shortfall:.2f}" if goal.shortfall is not None else "None"
        lines.append(f"  goal {goal.kind}: required_monthly={required} shortfall={shortfall} "
                     f"payment_day={goal.contribution_date_this_month} "
                     f"payment_status={goal.contribution_status} "
                     f"end_of_day_funding_gap={goal.end_of_day_funding_gap} "
                     f"missing={','.join(goal.missing) or '-'}")
    for day in result.cash_days:
        if day.entry_ids or day.shortage:
            lines.append(f"  {day.day}: actual_income={day.actual_income} planned_income={day.planned_income} "
                         f"uncertain_excluded={day.uncertain_income} transfer_in={day.transfer_in} "
                         f"cash_out={day.cash_out} (actual={day.actual_cash_out}, planned={day.planned_cash_out}) "
                         f"end_cash={day.ending_cash} shortage={day.shortage} cash_status={day.cash_status} "
                         f"available_cash={day.available_cash} available_shortage={day.available_shortage} "
                         f"overdue_income={day.overdue_income}")
    lines += ["  missing=" + (", ".join(result.missing) or "none"),
              *["  shortage reason: " + item for item in result.shortage_reasons],
              "  sources=" + ", ".join(result.sources),
              *["  assumption: " + item for item in result.assumptions]]
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=("all", "normal", "cash_gap", "unknown_goal",
                                               "overspend", "extra_reservation", "overdue_salary",
                                               "goal_conflict"),
                        default="all")
    selected = parser.parse_args().scenario
    for name in (("normal", "cash_gap", "unknown_goal", "overspend", "extra_reservation",
                  "overdue_salary", "goal_conflict") if selected == "all" else (selected,)):
        print(render(name))
