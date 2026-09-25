"""Deterministic, single-person KRW monthly budget and end-of-day cash forecast."""

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum

from asset_copilot.portfolio.calculator import _add, _div, _sub


ZERO = Decimal("0")
KST = timezone(timedelta(hours=9))


def _positive_gap(required: Decimal, available: Decimal) -> Decimal:
    return max(_sub(required, available), ZERO)


class EntryKind(str, Enum):
    INCOME_ACTUAL = "INCOME_ACTUAL"
    INCOME_PLANNED = "INCOME_PLANNED"
    INCOME_UNCERTAIN = "INCOME_UNCERTAIN"
    CASH_SPEND = "CASH_SPEND"
    CARD_CHARGE = "CARD_CHARGE"
    CARD_PAYMENT = "CARD_PAYMENT"
    DEBT_PRINCIPAL = "DEBT_PRINCIPAL"
    DEBT_COST = "DEBT_COST"
    TRANSFER_IN = "TRANSFER_IN"
    TRANSFER_OUT = "TRANSFER_OUT"


class BudgetCategory(str, Enum):
    FIXED = "FIXED"
    LIVING = "LIVING"
    FREEDOM = "FREEDOM"
    DEBT_PRINCIPAL = "DEBT_PRINCIPAL"
    DEBT_COST = "DEBT_COST"
    EMERGENCY = "EMERGENCY"
    GOAL = "GOAL"
    US_INVEST = "US_INVEST"
    KR_STRATEGY = "KR_STRATEGY"


REQUIRED_CATEGORIES = tuple(item for item in BudgetCategory if item is not BudgetCategory.GOAL)
SPEND_KINDS = (EntryKind.CASH_SPEND, EntryKind.CARD_CHARGE)
INCOME_KINDS = (EntryKind.INCOME_ACTUAL, EntryKind.INCOME_PLANNED, EntryKind.INCOME_UNCERTAIN)


def _money(value: Decimal, label: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value < ZERO:
        raise ValueError(f"{label} must be a nonnegative finite Decimal")


def _time(value: datetime, label: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be a timezone-aware datetime")


def _source(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} needs a nonempty source")


@dataclass(frozen=True, slots=True)
class CashEntry:
    id: str
    day: date
    kind: EntryKind
    amount: Decimal
    source: str
    recorded_at: datetime
    category: BudgetCategory | None = None
    link_id: str | None = None
    prior_period_card_payment: bool = False
    gross_income: Decimal | None = None  # Informational; never added to net income.
    observed: bool = False
    reservation_draw: Decimal = ZERO  # Future payment consuming this category's outstanding reservation.


@dataclass(frozen=True, slots=True)
class Goal:
    id: str
    kind: str
    target_amount: Decimal | None
    deadline: date | None
    saved_amount: Decimal
    contribution_day: int
    priority: int
    source: str
    contributions: tuple["GoalContribution", ...] = ()  # Included in saved_amount; not a cash entry.


@dataclass(frozen=True, slots=True)
class GoalContribution:
    day: date
    amount: Decimal
    source: str
    recorded_at: datetime


@dataclass(frozen=True, slots=True)
class Allocation:
    category: BudgetCategory
    amount: Decimal
    goal_id: str | None = None
    reserved: Decimal = ZERO


@dataclass(frozen=True, slots=True)
class BudgetPolicy:
    allocations: tuple[Allocation, ...]
    protected_floor: Decimal | None
    source: str


@dataclass(frozen=True, slots=True)
class BudgetInput:
    month: date  # First day of the month.
    evaluated_at: datetime
    balance_date: date  # Balance immediately before this date's entries.
    cash_balance: Decimal
    existing_protected: Decimal
    balance_source: str
    entries: tuple[CashEntry, ...]
    goals: tuple[Goal, ...]
    policy: BudgetPolicy | None
    income_complete: bool
    obligations_complete: bool
    currency: str = "KRW"


@dataclass(frozen=True, slots=True)
class GoalResult:
    goal_id: str
    kind: str
    required_monthly: Decimal | None
    missing: tuple[str, ...]
    contribution_dates: int | None
    proposed_amount: Decimal | None
    shortfall: Decimal | None
    contribution_date_this_month: date | None = None
    end_of_day_funding_gap: Decimal | None = None
    contribution_status: str = "UNCONFIRMED"
    funding_check_status: str = "UNKNOWN"  # CHECKED, NOT_REQUIRED, UNKNOWN


@dataclass(frozen=True, slots=True)
class AllocationResult:
    category: BudgetCategory
    goal_id: str | None
    planned: Decimal
    used: Decimal
    reserved: Decimal
    remaining: Decimal  # May be negative; overruns are never silently clipped.


@dataclass(frozen=True, slots=True)
class CashDay:
    day: date
    actual_income: Decimal
    planned_income: Decimal
    uncertain_income: Decimal
    transfer_in: Decimal
    cash_out: Decimal
    actual_cash_out: Decimal
    planned_cash_out: Decimal
    ending_cash: Decimal
    shortage: Decimal | None
    entry_ids: tuple[str, ...]
    overdue_income: Decimal = ZERO
    available_cash: Decimal | None = None
    available_shortage: Decimal | None = None
    cash_status: str = "FORECAST"  # OBSERVED_REPLAY, TODAY_FORECAST, FUTURE_FORECAST


@dataclass(frozen=True, slots=True)
class BudgetResult:
    month: date
    evaluated_at: datetime
    balance_date: date
    currency: str
    allocations: tuple[AllocationResult, ...]
    goals: tuple[GoalResult, ...]
    cash_days: tuple[CashDay, ...]
    allocation_margin: Decimal | None  # Signed monthly plan margin.
    unallocated: Decimal | None
    shortage: Decimal | None
    shortage_reasons: tuple[str, ...]
    investment_proposal: Decimal | None
    missing: tuple[str, ...]
    sources: tuple[str, ...]
    assumptions: tuple[str, ...]
    original_plan_margin: Decimal | None = None  # Only knowable from a month-start balance.
    current_cash: Decimal = ZERO
    expected_allocation_margin: Decimal | None = None
    unpaid_card_due: Decimal = ZERO  # Observed charges without observed settlement.


def _month_end(first: date) -> date:
    if first.month == 12:
        return date(first.year + 1, 1, 1) - timedelta(days=1)
    return date(first.year, first.month + 1, 1) - timedelta(days=1)


def _sum_goal_locks(locks: dict[date, Decimal], through: date) -> Decimal:
    total = ZERO
    for day, amount in locks.items():
        if day <= through:
            total = _add(total, amount)
    return total


def _reservation_category(entry: CashEntry) -> BudgetCategory | None:
    if entry.kind is EntryKind.CASH_SPEND:
        return entry.category
    if entry.kind is EntryKind.DEBT_PRINCIPAL:
        return BudgetCategory.DEBT_PRINCIPAL
    if entry.kind is EntryKind.DEBT_COST:
        return BudgetCategory.DEBT_COST
    return None


def _released_reservations(entries: tuple[CashEntry, ...], through: date) -> Decimal:
    released = ZERO
    for entry in entries:
        if entry.day <= through:
            released = _add(released, entry.reservation_draw)
    return released


def _validate(data: BudgetInput) -> None:
    if not isinstance(data, BudgetInput):
        raise TypeError("data must be BudgetInput")
    if data.currency != "KRW" or type(data.month) is not date or data.month.day != 1:
        raise ValueError("BUD-01 supports one KRW calendar month")
    _time(data.evaluated_at, "evaluated_at")
    end = _month_end(data.month)
    if type(data.balance_date) is not date or not data.month <= data.balance_date <= end:
        raise ValueError("balance_date must be in month")
    evaluation_day = data.evaluated_at.astimezone(KST).date()
    if evaluation_day < data.balance_date:
        raise ValueError("evaluated_at precedes the opening balance date")
    _money(data.cash_balance, "cash_balance")
    _money(data.existing_protected, "existing_protected")
    if data.existing_protected > data.cash_balance:
        raise ValueError("existing protected cash exceeds balance")
    if not isinstance(data.income_complete, bool) or not isinstance(data.obligations_complete, bool):
        raise ValueError("income and obligation completeness must be explicit booleans")
    _source(data.balance_source, "balance")
    if not isinstance(data.entries, tuple) or not isinstance(data.goals, tuple):
        raise ValueError("entries and goals must be tuples")
    seen_entries: set[str] = set()
    transfers: dict[str, list[CashEntry]] = {}
    charges: dict[str, CashEntry] = {}
    payments: list[CashEntry] = []
    reservation_draws: dict[BudgetCategory, Decimal] = {}
    for item in data.entries:
        if not isinstance(item, CashEntry) or not isinstance(item.id, str) or not item.id.strip() \
                or item.id in seen_entries or not isinstance(item.kind, EntryKind) \
                or type(item.day) is not date or not data.month <= item.day <= end:
            raise ValueError("entry identity, kind or date is invalid/duplicated")
        seen_entries.add(item.id)
        _money(item.amount, f"entry {item.id} amount")
        _money(item.reservation_draw, f"entry {item.id} reservation_draw")
        _time(item.recorded_at, f"entry {item.id} recorded_at")
        _source(item.source, f"entry {item.id}")
        if item.recorded_at > data.evaluated_at:
            raise ValueError("entry cannot be recorded after evaluation")
        if not isinstance(item.observed, bool) or (item.observed and item.day > evaluation_day):
            raise ValueError("observed entry cannot be in the future")
        if item.observed and item.recorded_at.astimezone(KST).date() < item.day:
            raise ValueError("observed entry cannot be recorded before its event date")
        if item.kind is EntryKind.INCOME_ACTUAL and not item.observed:
            raise ValueError("actual income must be observed")
        if item.kind in (EntryKind.INCOME_PLANNED, EntryKind.INCOME_UNCERTAIN) and item.observed:
            raise ValueError("planned or uncertain income is not observed")
        if item.day < data.balance_date and item.kind not in INCOME_KINDS and not item.observed:
            raise ValueError("past entry before observed balance must be observed")
        if item.gross_income is not None:
            _money(item.gross_income, "gross_income")
            if item.kind not in INCOME_KINDS or item.gross_income < item.amount:
                raise ValueError("gross income must be informational and at least net income")
        if item.kind in SPEND_KINDS:
            if item.category not in (BudgetCategory.FIXED, BudgetCategory.LIVING,
                                     BudgetCategory.FREEDOM):
                raise ValueError("spending needs FIXED, LIVING or FREEDOM category")
        elif item.category is not None:
            raise ValueError("category is only for cash spending or card charges")
        if item.reservation_draw > ZERO:
            draw_category = _reservation_category(item)
            if draw_category is None or item.observed or item.day < evaluation_day \
                    or item.reservation_draw > item.amount:
                raise ValueError("reservation_draw needs a future unpaid category expense")
            reservation_draws[draw_category] = _add(
                reservation_draws.get(draw_category, ZERO), item.reservation_draw)
        if item.kind in (EntryKind.TRANSFER_IN, EntryKind.TRANSFER_OUT):
            if not item.link_id:
                raise ValueError("internal transfer needs link_id")
            transfers.setdefault(item.link_id, []).append(item)
        elif item.kind is EntryKind.CARD_CHARGE:
            charges[item.id] = item
        elif item.kind is EntryKind.CARD_PAYMENT:
            if not item.link_id:
                raise ValueError("card payment needs charge link_id or prior-period invoice ID")
            payments.append(item)
        elif item.link_id is not None:
            raise ValueError("link_id is only for transfers and card payments")
        if item.prior_period_card_payment and item.kind is not EntryKind.CARD_PAYMENT:
            raise ValueError("prior-period flag is only for card payment")
    for key, pair in transfers.items():
        if len(pair) != 2 or {item.kind for item in pair} != {
                EntryKind.TRANSFER_IN, EntryKind.TRANSFER_OUT} or pair[0].amount != pair[1].amount \
                or pair[0].day != pair[1].day or pair[0].observed != pair[1].observed:
            raise ValueError(f"internal transfer {key} must have matching in/out legs")
    paid_charges: set[str] = set()
    for payment in payments:
        if payment.prior_period_card_payment:
            if payment.link_id in charges:
                raise ValueError("prior-period card payment links a current charge")
        else:
            charge = charges.get(payment.link_id)
            if charge is None or charge.amount != payment.amount or charge.day > payment.day \
                    or payment.link_id in paid_charges:
                raise ValueError("card payment must match one unpaid current charge")
            paid_charges.add(payment.link_id)
    goal_ids: set[str] = set()
    for goal in data.goals:
        if not isinstance(goal, Goal) or not isinstance(goal.id, str) or not goal.id.strip() \
                or goal.id in goal_ids or not isinstance(goal.kind, str) or not goal.kind.strip() \
                or not isinstance(goal.priority, int) or goal.priority < 1 \
                or not isinstance(goal.contribution_day, int) or not 1 <= goal.contribution_day <= 28:
            raise ValueError("goal identity, priority or contribution day is invalid")
        goal_ids.add(goal.id)
        _money(goal.saved_amount, "saved_amount")
        if goal.target_amount is not None:
            _money(goal.target_amount, "target_amount")
        if goal.deadline is not None and type(goal.deadline) is not date:
            raise ValueError("deadline must be a date")
        _source(goal.source, "goal")
        if not isinstance(goal.contributions, tuple):
            raise ValueError("goal contributions must be a tuple")
        paid = ZERO
        seen_days: set[date] = set()
        for contribution in goal.contributions:
            if not isinstance(contribution, GoalContribution) or type(contribution.day) is not date \
                    or contribution.day < data.month or contribution.day > evaluation_day \
                    or contribution.day in seen_days:
                raise ValueError("goal contribution date is invalid/duplicated")
            _money(contribution.amount, "goal contribution")
            if contribution.amount == ZERO:
                raise ValueError("observed goal contribution must be positive")
            _source(contribution.source, "goal contribution")
            _time(contribution.recorded_at, "goal contribution recorded_at")
            if contribution.recorded_at > data.evaluated_at \
                    or contribution.recorded_at.astimezone(KST).date() < contribution.day:
                raise ValueError("goal contribution cannot be recorded outside observation time")
            paid = _add(paid, contribution.amount)
            seen_days.add(contribution.day)
        if paid > goal.saved_amount:
            raise ValueError("goal contributions exceed saved_amount")
    if data.policy is not None:
        if not isinstance(data.policy, BudgetPolicy) or not isinstance(data.policy.allocations, tuple):
            raise ValueError("policy must contain tuple allocations")
        _source(data.policy.source, "policy")
        if data.policy.protected_floor is not None:
            _money(data.policy.protected_floor, "protected_floor")
        keys: set[tuple[BudgetCategory, str | None]] = set()
        for rule in data.policy.allocations:
            if not isinstance(rule, Allocation) or not isinstance(rule.category, BudgetCategory):
                raise ValueError("invalid allocation rule")
            _money(rule.amount, "allocation amount")
            _money(rule.reserved, "allocation reserved")
            key = (rule.category, rule.goal_id)
            if key in keys or (rule.category is BudgetCategory.GOAL) != (rule.goal_id is not None) \
                    or (rule.goal_id is not None and rule.goal_id not in goal_ids):
                raise ValueError("duplicate or invalid allocation target")
            keys.add(key)
    for category, amount in reservation_draws.items():
        rule = next((item for item in data.policy.allocations
                     if item.category is category and item.goal_id is None), None) if data.policy else None
        if rule is None or amount > rule.reserved:
            raise ValueError("reservation_draw exceeds outstanding category reservation")


def _goal_result(goal: Goal, data: BudgetInput, proposed: Decimal | None) -> GoalResult:
    evaluation_day = data.evaluated_at.astimezone(KST).date()
    contribution_date = date(data.month.year, data.month.month, goal.contribution_day)
    paid = ZERO
    for item in goal.contributions:
        paid = _add(paid, item.amount)
    observed = bool(goal.contributions)
    status = ("OBSERVED" if observed and (proposed is None or paid >= proposed)
              else "PARTIAL" if observed else "OVERDUE_UNCONFIRMED"
              if contribution_date < evaluation_day else "PLANNED")
    missing: list[str] = []
    if goal.target_amount is None:
        missing.append("target_amount")
    if goal.deadline is None:
        missing.append("deadline")
    if missing:
        return GoalResult(goal.id, goal.kind, None, tuple(missing), None, proposed, None,
                          contribution_date, contribution_status=status)
    remaining = max(_sub(goal.target_amount, goal.saved_amount), ZERO)
    current = data.month
    count = 0
    while current <= goal.deadline:
        contribution = date(current.year, current.month, goal.contribution_day)
        if contribution >= max(data.balance_date, evaluation_day) and contribution <= goal.deadline \
                and not (contribution == contribution_date and status == "OBSERVED"):
            count += 1
        current = date(current.year + (current.month == 12), current.month % 12 + 1, 1)
    if count == 0 and remaining > ZERO:
        return GoalResult(goal.id, goal.kind, None, ("contribution_date_before_deadline",),
                          0, proposed, None, contribution_date, contribution_status=status)
    required = _div(remaining, Decimal(count)) if count else ZERO
    additional_proposed = (max(_sub(proposed, paid), ZERO)
                           if proposed is not None and contribution_date >= evaluation_day
                           else proposed)
    shortfall = (_positive_gap(required, additional_proposed)
                 if additional_proposed is not None else None)
    return GoalResult(goal.id, goal.kind, required, (), count, proposed, shortfall,
                      contribution_date, contribution_status=status)


def calculate_month(data: BudgetInput) -> BudgetResult:
    """Return a proposal, never an approval, transfer, FX conversion or order."""
    _validate(data)
    evaluation_day = data.evaluated_at.astimezone(KST).date()
    entries = tuple(sorted(data.entries, key=lambda item: (item.day, item.id)))
    policy = data.policy
    rules = { (item.category, item.goal_id): item for item in policy.allocations} if policy else {}
    missing: list[str] = []
    if not data.income_complete:
        missing.append("income_records")
    if not data.obligations_complete:
        missing.append("obligation_records")
    if policy is None:
        missing.append("budget_policy")
    else:
        if policy.protected_floor is None:
            missing.append("protected_floor")
        for category in REQUIRED_CATEGORIES:
            if (category, None) not in rules:
                missing.append(f"allocation:{category.value}")
    goal_results = tuple(_goal_result(goal, data,
                         rules[(BudgetCategory.GOAL, goal.id)].amount
                         if (BudgetCategory.GOAL, goal.id) in rules else None)
                         for goal in sorted(data.goals, key=lambda item: (item.priority, item.id)))
    for item in goal_results:
        missing.extend(f"goal:{item.goal_id}:{field}" for field in item.missing)
        if item.proposed_amount is None and not item.missing:
            missing.append(f"allocation:GOAL:{item.goal_id}")

    used: dict[tuple[BudgetCategory, str | None], Decimal] = {}
    for entry in entries:
        if not entry.observed:
            continue
        if entry.kind in SPEND_KINDS:
            key = (entry.category, None)
        elif entry.kind is EntryKind.DEBT_PRINCIPAL:
            key = (BudgetCategory.DEBT_PRINCIPAL, None)
        elif entry.kind is EntryKind.DEBT_COST:
            key = (BudgetCategory.DEBT_COST, None)
        else:
            continue
        used[key] = _add(used.get(key, ZERO), entry.amount)
    for goal in data.goals:
        key = (BudgetCategory.GOAL, goal.id)
        for contribution in goal.contributions:
            used[key] = _add(used.get(key, ZERO), contribution.amount)
    allocation_results = tuple(AllocationResult(
        rule.category, rule.goal_id, rule.amount, used.get(key, ZERO), rule.reserved,
        _sub(_sub(rule.amount, used.get(key, ZERO)), rule.reserved))
        for key, rule in sorted(rules.items(), key=lambda pair: (pair[0][0].value, pair[0][1] or "")))
    for key, amount in used.items():
        if key not in rules and amount > ZERO:
            missing.append(f"allocation:{key[0].value}")

    overdue_income_ids = tuple(item.id for item in entries
                               if item.kind is EntryKind.INCOME_PLANNED
                               and item.day < evaluation_day and not item.observed)
    overdue_obligation_ids = tuple(item.id for item in entries
                                   if item.kind in (EntryKind.CASH_SPEND, EntryKind.CARD_PAYMENT,
                                                    EntryKind.DEBT_PRINCIPAL, EntryKind.DEBT_COST)
                                   and item.day < evaluation_day and not item.observed)
    charges = {item.id: item for item in entries if item.kind is EntryKind.CARD_CHARGE}
    card_payments = {item.link_id: item for item in entries
                     if item.kind is EntryKind.CARD_PAYMENT and not item.prior_period_card_payment}
    unpaid_charges = tuple(item for item in charges.values() if item.observed and
                           (item.id not in card_payments or not card_payments[item.id].observed))
    unpaid_card_due = ZERO
    for charge in unpaid_charges:
        unpaid_card_due = _add(unpaid_card_due, charge.amount)
    undated_card_ids = tuple(item.id for item in unpaid_charges
                             if item.id not in card_payments)
    missing.extend(f"income_unconfirmed:{id}" for id in overdue_income_ids)
    missing.extend(f"obligation_unconfirmed:{id}" for id in overdue_obligation_ids)
    missing.extend(f"card_payment_date:{id}" for id in undated_card_ids)
    critical_missing = tuple(item for item in missing if not item.startswith(
        ("income_unconfirmed:", "card_payment_date:")))

    end = _month_end(data.month)
    by_day: dict[date, list[CashEntry]] = {}
    for entry in entries:
        if entry.day >= data.balance_date:
            by_day.setdefault(entry.day, []).append(entry)
    days: list[CashDay] = []
    balance = data.cash_balance
    current = data.balance_date
    while current <= end:
        actual = planned = uncertain = transfer_in = out = actual_out = planned_out = ZERO
        items = by_day.get(current, [])
        for item in items:
            if item.kind is EntryKind.INCOME_ACTUAL:
                actual = _add(actual, item.amount)
            elif item.kind is EntryKind.TRANSFER_IN:
                if current >= evaluation_day or item.observed:
                    transfer_in = _add(transfer_in, item.amount)
            elif item.kind is EntryKind.INCOME_PLANNED:
                if current >= evaluation_day:
                    planned = _add(planned, item.amount)
            elif item.kind is EntryKind.INCOME_UNCERTAIN:
                uncertain = _add(uncertain, item.amount)
            elif item.kind in (EntryKind.CASH_SPEND, EntryKind.CARD_PAYMENT,
                               EntryKind.DEBT_PRINCIPAL, EntryKind.DEBT_COST,
                               EntryKind.TRANSFER_OUT):
                if current < evaluation_day and not item.observed:
                    continue
                out = _add(out, item.amount)
                if item.observed:
                    actual_out = _add(actual_out, item.amount)
                else:
                    planned_out = _add(planned_out, item.amount)
        balance = _sub(_add(_add(_add(balance, actual), planned), transfer_in), out)
        day_shortage = (_positive_gap(ZERO, balance)
                        if data.income_complete and data.obligations_complete
                        and not overdue_obligation_ids else None)
        overdue_amount = ZERO
        for item in items:
            if item.kind is EntryKind.INCOME_PLANNED and current < evaluation_day:
                overdue_amount = _add(overdue_amount, item.amount)
        days.append(CashDay(current, actual, planned, uncertain, transfer_in, out,
                            actual_out, planned_out, balance,
                            day_shortage, tuple(item.id for item in items), overdue_amount,
                            cash_status=("OBSERVED_REPLAY" if current < evaluation_day else
                                         "TODAY_FORECAST" if current == evaluation_day else
                                         "FUTURE_FORECAST")))
        current += timedelta(days=1)

    # This is a conservative end-of-day check, not proof of intraday transfer capacity.
    day_by_date = {item.day: item for item in days}
    observed_goal_savings = ZERO
    reserved_goals = ZERO
    reserved_other = ZERO
    for rule in rules.values():
        if rule.category is not BudgetCategory.GOAL:
            reserved_other = _add(reserved_other, rule.reserved)
    for goal in data.goals:
        for contribution in goal.contributions:
            observed_goal_savings = _add(observed_goal_savings, contribution.amount)
        rule = rules.get((BudgetCategory.GOAL, goal.id))
        if rule is not None:
            reserved_goals = _add(reserved_goals, rule.reserved)
    protected = max(data.existing_protected, policy.protected_floor if policy and
                    policy.protected_floor is not None else ZERO, observed_goal_savings)
    goal_locks: dict[date, Decimal] = {}
    checked_goals: dict[str, GoalResult] = {}
    ordered_goals = sorted(zip(sorted(data.goals, key=lambda item: (item.priority, item.id)),
                               goal_results),
                           key=lambda pair: (pair[0].contribution_day, pair[0].priority,
                                             pair[0].id))
    for goal, result in ordered_goals:
        contribution_date = date(data.month.year, data.month.month, goal.contribution_day)
        if result.required_monthly == ZERO or result.contribution_status == "OBSERVED":
            checked_goals[goal.id] = replace(result, funding_check_status="NOT_REQUIRED")
            continue
        if contribution_date < max(data.balance_date, evaluation_day):
            checked_goals[goal.id] = result
            continue
        gap = None
        if result.proposed_amount is not None and policy is not None \
                and policy.protected_floor is not None and data.income_complete \
                and data.obligations_complete and not critical_missing:
            rule = rules[(BudgetCategory.GOAL, goal.id)]
            used_goal = used.get((BudgetCategory.GOAL, goal.id), ZERO)
            new_lock = max(_sub(_sub(rule.amount, used_goal), rule.reserved), ZERO)
            prior_same_day = goal_locks.get(contribution_date, ZERO)
            earlier_locks = ZERO
            for lock_day, amount in goal_locks.items():
                if lock_day <= contribution_date:
                    earlier_locks = _add(earlier_locks, amount)
            remaining_other = _sub(reserved_other,
                                   _released_reservations(entries, contribution_date))
            available = _sub(_sub(_sub(_sub(day_by_date[contribution_date].ending_cash,
                                           protected), reserved_goals), remaining_other),
                             earlier_locks)
            gap = _positive_gap(new_lock, available)
            goal_locks[contribution_date] = _add(prior_same_day, new_lock)
        checked_goals[goal.id] = replace(result, contribution_date_this_month=contribution_date,
                                         end_of_day_funding_gap=gap,
                                         funding_check_status=("CHECKED" if gap is not None
                                                               else "UNKNOWN"))
    goal_results = tuple(checked_goals[item.goal_id] for item in goal_results)
    for goal in goal_results:
        if goal.funding_check_status == "UNKNOWN" and not goal.missing and \
                goal.contribution_date_this_month < evaluation_day:
            missing.append(f"goal_contribution_confirmation:{goal.goal_id}")

    if policy is not None and policy.protected_floor is not None and not critical_missing:
        available_days = []
        for day in days:
            saved_through_day = ZERO
            for goal in data.goals:
                for contribution in goal.contributions:
                    if contribution.day <= day.day:
                        saved_through_day = _add(saved_through_day, contribution.amount)
            day_protected = max(data.existing_protected, policy.protected_floor,
                                saved_through_day)
            remaining_other = (_sub(reserved_other,
                                    _released_reservations(entries, day.day))
                               if day.day >= evaluation_day else ZERO)
            current_goal_reservations = reserved_goals if day.day >= evaluation_day else ZERO
            card_due_on_day = ZERO
            for charge in charges.values():
                payment = card_payments.get(charge.id)
                settled_by_day = payment is not None and payment.day <= day.day and (
                    payment.observed or payment.day >= evaluation_day)
                if charge.observed and charge.day <= day.day and not settled_by_day:
                    card_due_on_day = _add(card_due_on_day, charge.amount)
            available = _sub(_sub(_sub(day.ending_cash, day_protected),
                                  remaining_other),
                             _add(current_goal_reservations,
                                  _add(_sum_goal_locks(goal_locks, day.day), card_due_on_day)))
            available_days.append(replace(day, available_cash=available,
                                          available_shortage=(
                                              _positive_gap(ZERO, available)
                                              if data.income_complete and data.obligations_complete
                                              else None)))
        days = available_days

    current_cash = data.cash_balance
    for entry in entries:
        if data.balance_date <= entry.day <= evaluation_day and entry.observed:
            if entry.kind in (EntryKind.INCOME_ACTUAL, EntryKind.TRANSFER_IN):
                current_cash = _add(current_cash, entry.amount)
            elif entry.kind in (EntryKind.CASH_SPEND, EntryKind.CARD_PAYMENT,
                                EntryKind.DEBT_PRINCIPAL, EntryKind.DEBT_COST,
                                EntryKind.TRANSFER_OUT):
                current_cash = _sub(current_cash, entry.amount)
    margin = unallocated = shortage = investment = original_margin = expected_margin = None
    if not critical_missing:
        future_income = ZERO
        original_income = ZERO
        prior_card_due = original_prior_card_due = ZERO
        for entry in entries:
            if entry.kind in (EntryKind.INCOME_ACTUAL, EntryKind.INCOME_PLANNED):
                original_income = _add(original_income, entry.amount)
                if entry.day > evaluation_day and entry.kind is EntryKind.INCOME_PLANNED:
                    future_income = _add(future_income, entry.amount)
            if entry.kind is EntryKind.CARD_PAYMENT:
                if entry.prior_period_card_payment:
                    original_prior_card_due = _add(original_prior_card_due, entry.amount)
                if entry.day > evaluation_day or (entry.day == evaluation_day and not entry.observed):
                    if entry.prior_period_card_payment:
                        prior_card_due = _add(prior_card_due, entry.amount)
        future_unreserved: dict[tuple[BudgetCategory, str | None], Decimal] = {}
        for entry in entries:
            if entry.observed or entry.day < evaluation_day:
                continue
            if entry.kind in SPEND_KINDS:
                key = (entry.category, None)
            elif entry.kind is EntryKind.DEBT_PRINCIPAL:
                key = (BudgetCategory.DEBT_PRINCIPAL, None)
            elif entry.kind is EntryKind.DEBT_COST:
                key = (BudgetCategory.DEBT_COST, None)
            else:
                continue
            future_unreserved[key] = _add(
                future_unreserved.get(key, ZERO),
                _sub(entry.amount, entry.reservation_draw))
        remaining_plan = original_plan = ZERO
        for line in allocation_results:
            key = (line.category, line.goal_id)
            remaining_plan = _add(remaining_plan,
                                  max(_sub(line.planned, line.used),
                                      _add(line.reserved, future_unreserved.get(key, ZERO)), ZERO))
            original_plan = _add(original_plan, max(line.planned, line.reserved))
        margin = _sub(_sub(_sub(_sub(current_cash, protected), remaining_plan),
                           prior_card_due), unpaid_card_due)
        expected_margin = _add(margin, future_income)
        if data.balance_date == data.month:
            opening_protected = max(data.existing_protected, policy.protected_floor)
            original_margin = _sub(_sub(_sub(_add(data.cash_balance, original_income), opening_protected),
                                        original_plan), original_prior_card_due)
        unallocated, shortage = max(margin, ZERO), _positive_gap(ZERO, margin)
        if not overdue_income_ids and not undated_card_ids and margin >= ZERO \
                and all(item.shortage == ZERO and item.available_shortage == ZERO
                        for item in days if item.day >= evaluation_day) \
                and all(item.shortfall == ZERO and
                        (item.funding_check_status == "NOT_REQUIRED" or
                         (item.funding_check_status == "CHECKED" and
                          item.end_of_day_funding_gap == ZERO))
                        for item in goal_results):
            investment = ZERO
            for category in (BudgetCategory.US_INVEST, BudgetCategory.KR_STRATEGY):
                line = next(item for item in allocation_results if item.category is category)
                investment = _add(investment, max(line.remaining, ZERO))
    sources = tuple(sorted({data.balance_source, *(item.source for item in entries),
                            *(item.source for item in data.goals),
                            *(contribution.source for goal in data.goals
                              for contribution in goal.contributions),
                            *((policy.source,) if policy else ())}))
    reasons = []
    if margin is not None and margin < ZERO:
        reasons.append(f"current allocations and unpaid card dues exceed confirmed funding by {_sub(ZERO, margin)}")
    for entry_id in undated_card_ids:
        reasons.append(f"card charge {entry_id} is unpaid; supply its payment date to assess daily funding")
    for entry_id in overdue_income_ids:
        reasons.append(f"planned income {entry_id} is overdue and unconfirmed at {evaluation_day}")
    for entry_id in overdue_obligation_ids:
        reasons.append(f"planned obligation {entry_id} is overdue and unconfirmed at {evaluation_day}")
    for line in allocation_results:
        if line.remaining < ZERO:
            reasons.append(f"{line.category.value}{':' + line.goal_id if line.goal_id else ''} "
                           f"used/reserved exceeds allocation by {_sub(ZERO, line.remaining)}")
    for goal in goal_results:
        if goal.funding_check_status == "UNKNOWN" and not goal.missing and \
                goal.contribution_date_this_month < evaluation_day:
            reasons.append(f"goal {goal.goal_id} contribution at {goal.contribution_date_this_month} "
                           "needs an observed completion or an updated payment schedule")
        if goal.shortfall is not None and goal.shortfall > ZERO:
            reasons.append(f"goal {goal.goal_id} monthly contribution below required by {goal.shortfall}")
        if goal.end_of_day_funding_gap is not None and goal.end_of_day_funding_gap > ZERO:
            reasons.append(f"goal {goal.goal_id} lacks {goal.end_of_day_funding_gap} "
                           f"at {goal.contribution_date_this_month} end of day")
    previous_shortage = ZERO
    previous_available_excess = ZERO
    for item in days:
        if item.shortage is not None and item.shortage > ZERO and previous_shortage == ZERO:
            reasons.append(f"{item.day} end-of-day cash shortage {item.shortage}; entries: "
                           + ", ".join(item.entry_ids))
        previous_shortage = item.shortage or ZERO
        available_excess = (max(_sub(item.available_shortage, item.shortage or ZERO), ZERO)
                            if item.available_shortage is not None else ZERO)
        if available_excess > ZERO and previous_available_excess == ZERO:
            reasons.append(f"{item.day} available cash after protection and goal allocation "
                           f"short by {item.available_shortage}; entries: " + ", ".join(item.entry_ids))
        previous_available_excess = available_excess
    return BudgetResult(data.month, data.evaluated_at, data.balance_date, data.currency,
                        allocation_results, goal_results, tuple(days), margin, unallocated,
                        shortage, tuple(reasons), investment, tuple(sorted(set(missing))), sources,
                        ("Day figures are end-of-day estimates; intraday order is unknown.",
                         "Planned income is forecast only until observed; overdue and uncertain income is excluded.",
                         "With incomplete records, ending cash uses known entries only and shortage is UNKNOWN.",
                         "Allocation is a proposal, not approval, transfer or order."),
                        original_margin, current_cash, expected_margin, unpaid_card_due)
