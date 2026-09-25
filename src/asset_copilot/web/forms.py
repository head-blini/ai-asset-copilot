"""Lossless, bounded HTML form adapter for the existing monthly budget API."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal

from asset_copilot.budget import (Allocation, BudgetCategory, BudgetInput, BudgetPolicy,
                                  CashEntry, EntryKind, Goal, GoalContribution)

MAX_BODY = 64_000
MAX_FIELDS = 500
MAX_ENTRIES = 40
MAX_GOALS = 8
MAX_CONTRIBUTIONS = 24
MAX_TEXT = 160
AMOUNT = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")
ROW_KEY = re.compile(r"(entry|goal|contribution)\.([0-9]+)\.([a-z_]+)\Z")
SOURCE = "manual-local-web"
NON_GOAL = tuple(category for category in BudgetCategory if category is not BudgetCategory.GOAL)


class FormError(ValueError):
    def __init__(self, field: str, message: str):
        self.field = field
        super().__init__(message)


def empty_form() -> dict:
    return {
        "month": "", "evaluated_at": "", "balance_date": "", "cash_balance": "",
        "existing_protected": "", "protected_floor": "", "balance_source": SOURCE,
        "policy_source": SOURCE,
        "income_complete": "", "obligations_complete": "", "entries_mode": "",
        "goals_mode": "", "policy_mode": "", "example_id": "",
        "allocations": {category.value: {"state": "", "amount": "", "reserved": ""}
                        for category in NON_GOAL},
        "entries": [], "goals": [], "contributions": [],
    }


def _text(raw: str, field: str, *, required: bool = False, limit: int = MAX_TEXT) -> str:
    if len(raw) > limit:
        raise FormError(field, f"{field}: {limit}자를 초과했습니다.")
    value = raw.strip()
    if required and not value:
        raise FormError(field, f"{field}: 값을 입력해 주세요.")
    return value


def _money(raw: str, field: str, *, optional: bool = False) -> Decimal | None:
    value = _text(raw, field, limit=32)
    if not value and optional:
        return None
    if not AMOUNT.fullmatch(value):
        raise FormError(field, f"{field}: 0 이상의 유한한 십진 금액을 입력해 주세요.")
    return Decimal(value)


def _date(raw: str, field: str, *, optional: bool = False) -> date | None:
    value = _text(raw, field, limit=10)
    if not value and optional:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise FormError(field, f"{field}: YYYY-MM-DD 날짜가 필요합니다.") from exc
    if parsed.isoformat() != value or not 2000 <= parsed.year <= 2100:
        raise FormError(field, f"{field}: 2000~2100년의 날짜가 필요합니다.")
    return parsed


def _datetime(raw: str, field: str) -> datetime:
    value = _text(raw, field, required=True, limit=40)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise FormError(field, f"{field}: 시간대가 있는 ISO 시각이 필요합니다.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None or not 2000 <= parsed.year <= 2100:
        raise FormError(field, f"{field}: 시간대와 2000~2100년 범위가 필요합니다.")
    return parsed


def _number(raw: str, field: str, low: int, high: int) -> int:
    value = _text(raw, field, limit=5)
    if not value.isdecimal():
        raise FormError(field, f"{field}: 정수를 입력해 주세요.")
    number = int(value)
    if not low <= number <= high:
        raise FormError(field, f"{field}: {low}~{high} 범위가 필요합니다.")
    return number


def _choice(raw: str, field: str, allowed: tuple[str, ...]) -> str:
    if raw not in allowed:
        raise FormError(field, f"{field}: 선택지를 확인해 주세요.")
    return raw


def _rows(values: dict[str, str], kind: str, limit: int,
          *, strict: bool = True) -> list[dict[str, str]]:
    rows: dict[int, dict[str, str]] = {}
    for key, value in values.items():
        match = ROW_KEY.fullmatch(key)
        if match and match.group(1) == kind:
            index = int(match.group(2))
            if str(index) != match.group(2):
                if strict:
                    raise FormError(kind, f"{kind}: 행 번호 형식이 잘못됐습니다.")
                continue
            if index >= limit:
                if strict:
                    raise FormError(kind, f"{kind}: 최대 {limit}행입니다.")
                continue
            rows.setdefault(index, {})[match.group(3)] = value
    if rows and set(rows) != set(range(len(rows))):
        if strict:
            raise FormError(kind, f"{kind}: 행 번호가 연속되어야 합니다.")
        return [rows[i] for i in sorted(rows)]
    return [rows[i] for i in range(len(rows))]


def form_from_values(values: dict[str, str], *, strict: bool = True) -> dict:
    form = empty_form()
    scalar_keys = {key for key in form if key not in ("allocations", "entries", "goals", "contributions")}
    for key in scalar_keys:
        form[key] = values.get(key, "")
    for category in NON_GOAL:
        for field in ("state", "amount", "reserved"):
            form["allocations"][category.value][field] = values.get(
                f"allocation.{category.value}.{field}", "")
    for kind, limit in (("entry", MAX_ENTRIES), ("goal", MAX_GOALS),
                        ("contribution", MAX_CONTRIBUTIONS)):
        form[{"entry": "entries", "goal": "goals", "contribution": "contributions"}[kind]] = _rows(
            values, kind, limit, strict=strict)
    allowed = scalar_keys | {"csrf_token"}
    allowed.update(f"allocation.{category.value}.{field}" for category in NON_GOAL
                   for field in ("state", "amount", "reserved"))
    allowed_fields = {
        "entry": {"id", "day", "kind", "amount", "source", "recorded_at", "category",
                  "link_id", "prior_period_card_payment", "gross_income", "observed",
                  "reservation_draw"},
        "goal": {"id", "kind", "target_amount", "deadline", "saved_amount",
                 "contribution_day", "priority", "source", "allocation_state",
                 "allocation_amount", "allocation_reserved"},
        "contribution": {"goal_id", "day", "amount", "source", "recorded_at",
                         "protection_source", "included"},
    }
    for key in values:
        if key in allowed:
            continue
        match = ROW_KEY.fullmatch(key)
        if strict and (match is None or match.group(3) not in allowed_fields[match.group(1)]):
            raise FormError(key, f"지원하지 않는 필드: {key}")
    return form


def to_budget(form: dict) -> BudgetInput:
    try:
        month_text = _text(form["month"], "month", required=True, limit=7)
        if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", month_text):
            raise FormError("month", "기준 월은 YYYY-MM 형식이어야 합니다.")
        month = _date(month_text + "-01", "month")
        evaluated_at = _datetime(form["evaluated_at"], "evaluated_at")
        balance_date = _date(form["balance_date"], "balance_date")
        cash_balance = _money(form["cash_balance"], "cash_balance")
        existing_protected = _money(form["existing_protected"], "existing_protected")
        balance_source = _text(form["balance_source"], "balance_source", required=True)
        income_complete = _choice(form["income_complete"], "income_complete", ("yes", "no")) == "yes"
        obligations_complete = _choice(form["obligations_complete"], "obligations_complete", ("yes", "no")) == "yes"
        entries_mode = _choice(form["entries_mode"], "entries_mode", ("none", "rows"))
        goals_mode = _choice(form["goals_mode"], "goals_mode", ("none", "rows"))
        policy_mode = _choice(form["policy_mode"], "policy_mode", ("none", "rows"))
        if entries_mode == "none" and form["entries"]:
            raise FormError("entries_mode", "해당 없음과 입력 행을 함께 보낼 수 없습니다.")
        if goals_mode == "none" and (form["goals"] or form["contributions"]):
            raise FormError("goals_mode", "목표 없음과 목표 행을 함께 보낼 수 없습니다.")
        if entries_mode == "rows" and not form["entries"]:
            raise FormError("entries", "내역 행을 추가하거나 해당 없음을 선택해 주세요.")
        if goals_mode == "rows" and not form["goals"]:
            raise FormError("goals", "목표 행을 추가하거나 목표 없음을 선택해 주세요.")
        entries = []
        entry_ids = set()
        for i, row in enumerate(form["entries"]):
            field = f"entry.{i}"
            entry_id = _text(row.get("id", ""), field + ".id", required=True, limit=64)
            if entry_id in entry_ids:
                raise FormError(field + ".id", "내역 ID가 중복됐습니다.")
            entry_ids.add(entry_id)
            kind = EntryKind(_choice(row.get("kind", ""), field + ".kind",
                                     tuple(item.value for item in EntryKind)))
            category_text = row.get("category", "")
            category = BudgetCategory(_choice(category_text, field + ".category",
                            ("",) + tuple(item.value for item in BudgetCategory))) if category_text else None
            entries.append(CashEntry(
                entry_id,
                _date(row.get("day", ""), field + ".day"), kind,
                _money(row.get("amount", ""), field + ".amount"),
                _text(row.get("source", ""), field + ".source", required=True),
                _datetime(row.get("recorded_at", ""), field + ".recorded_at"),
                category, _text(row.get("link_id", ""), field + ".link_id", limit=64) or None,
                _choice(row.get("prior_period_card_payment", ""),
                        field + ".prior_period_card_payment", ("yes", "no")) == "yes",
                _money(row.get("gross_income", ""), field + ".gross_income", optional=True),
                _choice(row.get("observed", ""), field + ".observed", ("yes", "no")) == "yes",
                _money(row.get("reservation_draw", ""), field + ".reservation_draw", optional=True)
                or Decimal("0")))
        contributions: dict[str, list[GoalContribution]] = {}
        included = []
        for i, row in enumerate(form["contributions"]):
            field = f"contribution.{i}"
            goal_id = _text(row.get("goal_id", ""), field + ".goal_id", required=True, limit=64)
            day = _date(row.get("day", ""), field + ".day")
            included_value = _choice(row.get("included", ""), field + ".included", ("yes", "no"))
            if included_value == "yes":
                included.append((goal_id, day))
            contributions.setdefault(goal_id, []).append(GoalContribution(
                day, _money(row.get("amount", ""), field + ".amount"),
                _text(row.get("source", ""), field + ".source", required=True),
                _datetime(row.get("recorded_at", ""), field + ".recorded_at"),
                _choice(row.get("protection_source", ""), field + ".protection_source",
                        ("FREE_CASH",))))
        goals = []
        goal_allocations = []
        goal_ids = set()
        for i, row in enumerate(form["goals"]):
            field = f"goal.{i}"
            goal_id = _text(row.get("id", ""), field + ".id", required=True, limit=64)
            if goal_id in goal_ids:
                raise FormError(field + ".id", "목표 ID가 중복됐습니다.")
            goal_ids.add(goal_id)
            goals.append(Goal(
                goal_id, _text(row.get("kind", ""), field + ".kind", required=True, limit=64),
                _money(row.get("target_amount", ""), field + ".target_amount", optional=True),
                _date(row.get("deadline", ""), field + ".deadline", optional=True),
                _money(row.get("saved_amount", ""), field + ".saved_amount"),
                _number(row.get("contribution_day", ""), field + ".contribution_day", 1, 28),
                _number(row.get("priority", ""), field + ".priority", 1, 100),
                _text(row.get("source", ""), field + ".source", required=True),
                tuple(contributions.pop(goal_id, []))))
            state = _choice(row.get("allocation_state", ""), field + ".allocation_state",
                            ("none", "amount")) if policy_mode == "rows" else \
                _choice(row.get("allocation_state", ""), field + ".allocation_state",
                        ("", "none", "amount"))
            if state == "amount":
                goal_allocations.append(Allocation(
                    BudgetCategory.GOAL, _money(row.get("allocation_amount", ""),
                                                field + ".allocation_amount"), goal_id,
                    _money(row.get("allocation_reserved", ""),
                           field + ".allocation_reserved", optional=True) or Decimal("0")))
            elif state == "none" and (row.get("allocation_amount") or row.get("allocation_reserved")):
                raise FormError(field + ".allocation_state", "배정 없음과 금액을 함께 입력할 수 없습니다.")
        if contributions:
            raise FormError("contributions", "존재하지 않는 목표에 연결된 납입이 있습니다.")
        if policy_mode == "none":
            if form["protected_floor"] or goal_allocations or any(
                    cell[field] for cell in form["allocations"].values()
                    for field in ("state", "amount", "reserved")) or any(
                    row.get("allocation_amount") or row.get("allocation_reserved")
                    for row in form["goals"]):
                raise FormError("policy_mode", "배정안 없음과 정책 값을 함께 보낼 수 없습니다.")
            policy = None
        else:
            allocations = []
            for category in NON_GOAL:
                cell = form["allocations"][category.value]
                state = _choice(cell["state"], f"allocation.{category.value}.state",
                                ("none", "amount"))
                if state == "none":
                    if cell["amount"] or cell["reserved"]:
                        raise FormError(f"allocation.{category.value}.state",
                                        "배정 없음과 금액을 함께 입력할 수 없습니다.")
                    amount = reserved = Decimal("0")
                else:
                    amount = _money(cell["amount"], f"allocation.{category.value}.amount")
                    reserved = _money(cell["reserved"],
                                      f"allocation.{category.value}.reserved", optional=True) or Decimal("0")
                allocations.append(Allocation(category, amount, reserved=reserved))
            policy = BudgetPolicy(tuple(allocations + goal_allocations),
                                  _money(form["protected_floor"], "protected_floor", optional=True),
                                  _text(form["policy_source"], "policy_source", required=True))
        return BudgetInput(month, evaluated_at, balance_date, cash_balance,
                           existing_protected, balance_source, tuple(entries), tuple(goals),
                           policy, income_complete, obligations_complete,
                           protected_contributions_in_balance=tuple(included))
    except (KeyError, TypeError) as exc:
        raise FormError("form", "입력 구조를 확인해 주세요.") from exc


def from_budget(data: BudgetInput, example_id: str) -> dict:
    form = empty_form()
    form.update(month=data.month.strftime("%Y-%m"), evaluated_at=data.evaluated_at.isoformat(),
                balance_date=data.balance_date.isoformat(), cash_balance=str(data.cash_balance),
                existing_protected=str(data.existing_protected), balance_source=data.balance_source,
                protected_floor="" if data.policy is None or data.policy.protected_floor is None
                else str(data.policy.protected_floor),
                policy_source=data.policy.source if data.policy else SOURCE,
                income_complete="yes" if data.income_complete else "no",
                obligations_complete="yes" if data.obligations_complete else "no",
                entries_mode="rows" if data.entries else "none",
                goals_mode="rows" if data.goals else "none",
                policy_mode="rows" if data.policy else "none", example_id=example_id)
    if data.policy:
        for allocation in data.policy.allocations:
            if allocation.category is not BudgetCategory.GOAL:
                form["allocations"][allocation.category.value] = {
                    "state": "amount", "amount": str(allocation.amount),
                    "reserved": str(allocation.reserved)}
    for entry in data.entries:
        form["entries"].append({
            "id": entry.id, "day": entry.day.isoformat(), "kind": entry.kind.value,
            "amount": str(entry.amount), "source": entry.source,
            "recorded_at": entry.recorded_at.isoformat(),
            "category": entry.category.value if entry.category else "",
            "link_id": entry.link_id or "",
            "prior_period_card_payment": "yes" if entry.prior_period_card_payment else "no",
            "gross_income": str(entry.gross_income) if entry.gross_income is not None else "",
            "observed": "yes" if entry.observed else "no",
            "reservation_draw": str(entry.reservation_draw)})
    allocation_by_goal = {item.goal_id: item for item in data.policy.allocations
                          if item.goal_id} if data.policy else {}
    included = set(data.protected_contributions_in_balance or ())
    for goal in data.goals:
        allocation = allocation_by_goal.get(goal.id)
        form["goals"].append({
            "id": goal.id, "kind": goal.kind, "target_amount": "" if goal.target_amount is None
            else str(goal.target_amount), "deadline": goal.deadline.isoformat() if goal.deadline else "",
            "saved_amount": str(goal.saved_amount), "contribution_day": str(goal.contribution_day),
            "priority": str(goal.priority), "source": goal.source,
            "allocation_state": "amount" if allocation else "none",
            "allocation_amount": str(allocation.amount) if allocation else "",
            "allocation_reserved": str(allocation.reserved) if allocation else ""})
        for contribution in goal.contributions:
            form["contributions"].append({
                "goal_id": goal.id, "day": contribution.day.isoformat(),
                "amount": str(contribution.amount), "source": contribution.source,
                "recorded_at": contribution.recorded_at.isoformat(),
                "protection_source": contribution.protection_source or "",
                "included": "yes" if (goal.id, contribution.day) in included else "no"})
    return form
