"""Deterministic, single-person KRW monthly budget and end-of-day cash forecast."""

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum

from asset_copilot.portfolio.calculator import _add, _div, _sub


ZERO = Decimal("0")


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


def _month_end(first: date) -> date:
    if first.month == 12:
        return date(first.year + 1, 1, 1) - timedelta(days=1)
    return date(first.year, first.month + 1, 1) - timedelta(days=1)


def _validate(data: BudgetInput) -> None:
    if not isinstance(data, BudgetInput):
        raise TypeError("data must be BudgetInput")
    if data.currency != "KRW" or type(data.month) is not date or data.month.day != 1:
        raise ValueError("BUD-01 supports one KRW calendar month")
    _time(data.evaluated_at, "evaluated_at")
    end = _month_end(data.month)
    if type(data.balance_date) is not date or not data.month <= data.balance_date <= end:
        raise ValueError("balance_date must be in month")
    if data.evaluated_at.date() < data.balance_date:
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
    for item in data.entries:
        if not isinstance(item, CashEntry) or not isinstance(item.id, str) or not item.id.strip() \
                or item.id in seen_entries or not isinstance(item.kind, EntryKind) \
                or type(item.day) is not date or not data.month <= item.day <= end:
            raise ValueError("entry identity, kind or date is invalid/duplicated")
        seen_entries.add(item.id)
        _money(item.amount, f"entry {item.id} amount")
        _time(item.recorded_at, f"entry {item.id} recorded_at")
        _source(item.source, f"entry {item.id}")
        if not isinstance(item.observed, bool) or (item.observed and item.day > data.evaluated_at.date()):
            raise ValueError("observed entry cannot be in the future")
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
                EntryKind.TRANSFER_IN, EntryKind.TRANSFER_OUT} or pair[0].amount != pair[1].amount:
            raise ValueError(f"internal transfer {key} must have equal in/out legs")
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


def _goal_result(goal: Goal, data: BudgetInput, proposed: Decimal | None) -> GoalResult:
    missing: list[str] = []
    if goal.target_amount is None:
        missing.append("target_amount")
    if goal.deadline is None:
        missing.append("deadline")
    if missing:
        return GoalResult(goal.id, goal.kind, None, tuple(missing), None, proposed, None)
    remaining = max(_sub(goal.target_amount, goal.saved_amount), ZERO)
    current = data.month
    count = 0
    while current <= goal.deadline:
        contribution = date(current.year, current.month, goal.contribution_day)
        if contribution >= data.balance_date and contribution <= goal.deadline:
            count += 1
        current = date(current.year + (current.month == 12), current.month % 12 + 1, 1)
    if count == 0 and remaining > ZERO:
        return GoalResult(goal.id, goal.kind, None, ("contribution_date_before_deadline",),
                          0, proposed, None)
    required = _div(remaining, Decimal(count)) if count else ZERO
    shortfall = max(_sub(required, proposed), ZERO) if proposed is not None else None
    return GoalResult(goal.id, goal.kind, required, (), count, proposed, shortfall)


def calculate_month(data: BudgetInput) -> BudgetResult:
    """Return a proposal, never an approval, transfer, FX conversion or order."""
    _validate(data)
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
    used_before_balance: dict[tuple[BudgetCategory, str | None], Decimal] = {}
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
        if entry.day < data.balance_date:
            used_before_balance[key] = _add(used_before_balance.get(key, ZERO), entry.amount)
    allocation_results = tuple(AllocationResult(
        rule.category, rule.goal_id, rule.amount, used.get(key, ZERO), rule.reserved,
        _sub(_sub(rule.amount, used.get(key, ZERO)), rule.reserved))
        for key, rule in sorted(rules.items(), key=lambda pair: (pair[0][0].value, pair[0][1] or "")))
    for key, amount in used.items():
        if key not in rules and amount > ZERO:
            missing.append(f"allocation:{key[0].value}")

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
                transfer_in = _add(transfer_in, item.amount)
            elif item.kind is EntryKind.INCOME_PLANNED:
                planned = _add(planned, item.amount)
            elif item.kind is EntryKind.INCOME_UNCERTAIN:
                uncertain = _add(uncertain, item.amount)
            elif item.kind in (EntryKind.CASH_SPEND, EntryKind.CARD_PAYMENT,
                               EntryKind.DEBT_PRINCIPAL, EntryKind.DEBT_COST,
                               EntryKind.TRANSFER_OUT):
                out = _add(out, item.amount)
                if item.observed:
                    actual_out = _add(actual_out, item.amount)
                else:
                    planned_out = _add(planned_out, item.amount)
        balance = _sub(_add(_add(_add(balance, actual), planned), transfer_in), out)
        day_shortage = max(-balance, ZERO) if data.income_complete and data.obligations_complete else None
        days.append(CashDay(current, actual, planned, uncertain, transfer_in, out,
                            actual_out, planned_out, balance,
                            day_shortage, tuple(item.id for item in items)))
        current += timedelta(days=1)

    # This is a conservative end-of-day check, not proof of intraday transfer capacity.
    day_by_date = {item.day: item for item in days}
    reserved_for_prior_goals = ZERO
    checked_goals: list[GoalResult] = []
    for goal, result in zip(sorted(data.goals, key=lambda item: (item.priority, item.id)), goal_results):
        contribution_date = date(data.month.year, data.month.month, goal.contribution_day)
        if contribution_date < data.balance_date:
            checked_goals.append(result)
            continue
        gap = None
        if result.proposed_amount is not None and policy is not None \
                and policy.protected_floor is not None and data.income_complete \
                and data.obligations_complete:
            protected = max(data.existing_protected, policy.protected_floor)
            available = _sub(_sub(day_by_date[contribution_date].ending_cash, protected),
                             reserved_for_prior_goals)
            gap = max(_sub(result.proposed_amount, available), ZERO)
            reserved_for_prior_goals = _add(reserved_for_prior_goals, result.proposed_amount)
        checked_goals.append(replace(result, contribution_date_this_month=contribution_date,
                                     end_of_day_funding_gap=gap))
    goal_results = tuple(checked_goals)

    margin = unallocated = shortage = investment = None
    if not missing:
        confirmed_income = ZERO
        prior_card_due = ZERO
        charges = {item.id: item for item in entries if item.kind is EntryKind.CARD_CHARGE}
        for entry in entries:
            if entry.day >= data.balance_date:
                if entry.kind in (EntryKind.INCOME_ACTUAL, EntryKind.INCOME_PLANNED):
                    confirmed_income = _add(confirmed_income, entry.amount)
                elif entry.kind is EntryKind.CARD_PAYMENT and (entry.prior_period_card_payment
                        or charges[entry.link_id].day < data.balance_date):
                    prior_card_due = _add(prior_card_due, entry.amount)
        protected = max(data.existing_protected, policy.protected_floor)
        remaining_plan = ZERO
        for line in allocation_results:
            before = used_before_balance.get((line.category, line.goal_id), ZERO)
            remaining_plan = _add(remaining_plan, max(_sub(line.planned, before), line.reserved, ZERO))
        margin = _sub(_sub(_sub(_add(data.cash_balance, confirmed_income), protected),
                           remaining_plan), prior_card_due)
        unallocated, shortage = max(margin, ZERO), max(-margin, ZERO)
        if margin >= ZERO and all(item.shortage == ZERO for item in days) \
                and all(item.shortfall == ZERO and item.end_of_day_funding_gap == ZERO
                        for item in goal_results):
            investment = _add(rules[(BudgetCategory.US_INVEST, None)].amount,
                              rules[(BudgetCategory.KR_STRATEGY, None)].amount)
    sources = tuple(sorted({data.balance_source, *(item.source for item in entries),
                            *(item.source for item in data.goals),
                            *((policy.source,) if policy else ())}))
    reasons = []
    if margin is not None and margin < ZERO:
        reasons.append(f"monthly allocations and prior card dues exceed confirmed funding by {-margin}")
    for line in allocation_results:
        if line.remaining < ZERO:
            reasons.append(f"{line.category.value}{':' + line.goal_id if line.goal_id else ''} "
                           f"used/reserved exceeds allocation by {-line.remaining}")
    for goal in goal_results:
        if goal.shortfall is not None and goal.shortfall > ZERO:
            reasons.append(f"goal {goal.goal_id} monthly contribution below required by {goal.shortfall}")
        if goal.end_of_day_funding_gap is not None and goal.end_of_day_funding_gap > ZERO:
            reasons.append(f"goal {goal.goal_id} lacks {goal.end_of_day_funding_gap} "
                           f"at {goal.contribution_date_this_month} end of day")
    previous_shortage = ZERO
    for item in days:
        if item.shortage is not None and item.shortage > ZERO and previous_shortage == ZERO:
            reasons.append(f"{item.day} end-of-day cash shortage {item.shortage}; entries: "
                           + ", ".join(item.entry_ids))
        previous_shortage = item.shortage or ZERO
    return BudgetResult(data.month, data.evaluated_at, data.balance_date, data.currency,
                        allocation_results, goal_results, tuple(days), margin, unallocated,
                        shortage, tuple(reasons), investment, tuple(sorted(set(missing))), sources,
                        ("Day figures are end-of-day estimates; intraday order is unknown.",
                         "Planned income is not cash until its dated receipt; uncertain income is excluded.",
                         "With incomplete records, ending cash uses known entries only and shortage is UNKNOWN.",
                         "Allocation is a proposal, not approval, transfer or order."))
