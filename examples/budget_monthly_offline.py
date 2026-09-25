"""Offline report for the shared synthetic monthly budget examples."""

import argparse

from asset_copilot.budget import calculate_month
from asset_copilot.budget.examples import MONTH, SOURCE, STAMP, SCENARIOS, entry, policy, sample_input

def render(scenario: str) -> str:
    result = calculate_month(sample_input(scenario))
    lines = [f"[{scenario}] 2026-09 KRW budget proposal (not approval, transfer or order)",
             f"  evaluated_at={result.evaluated_at.isoformat()} balance_date={result.balance_date}",
             f"  original plan margin={result.original_plan_margin} current_cash={result.current_cash} unpaid_card_due={result.unpaid_card_due} current allocation margin={result.allocation_margin} expected margin={result.expected_allocation_margin} unallocated={result.unallocated} shortage={result.shortage} investment_proposal={result.investment_proposal}",
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
                     f"funding_check={goal.funding_check_status} "
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
