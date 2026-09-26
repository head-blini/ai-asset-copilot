"""HTTP and form regressions for the optional local budget preview."""

import asyncio
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from importlib import import_module
from urllib.parse import urlencode

import pytest
pytest.importorskip("fastapi", reason="optional web extra is not installed in core CI")
pytest.importorskip("httpx", reason="optional web test extra is not installed in core CI")
import httpx
from fastapi.testclient import TestClient

from asset_copilot.budget import (Allocation, BudgetCategory as C, BudgetInput, BudgetPolicy,
                                  CashEntry, EntryKind as K, Goal, GoalContribution,
                                  calculate_month)
from asset_copilot.budget.examples import SCENARIOS, sample_input
from asset_copilot.web.forms import MAX_BODY, FormError, from_budget, form_from_values, to_budget

web = import_module("asset_copilot.web.app")
ORIGIN = {"Origin": "http://127.0.0.1:8765"}
SOURCE = "synthetic-web-test"


def flatten(form):
    values = {key: value for key, value in form.items()
              if key not in ("allocations", "entries", "goals", "contributions")}
    for category, cell in form["allocations"].items():
        for key, value in cell.items():
            values[f"allocation.{category}.{key}"] = value
    for plural, singular in (("entries", "entry"), ("goals", "goal"),
                             ("contributions", "contribution")):
        for index, row in enumerate(form[plural]):
            for key, value in row.items():
                values[f"{singular}.{index}.{key}"] = value
    return values


def client():
    return TestClient(web.app, base_url="http://127.0.0.1:8765")


def submit(browser, values):
    token = browser.cookies.get("budget_csrf")
    return browser.post("/calculate", data={**values, "csrf_token": token}, headers=ORIGIN)


def goal_input():
    return BudgetInput(
        date(2026, 9, 1), datetime(2026, 9, 25, 9, tzinfo=timezone.utc),
        date(2026, 9, 25), Decimal("1000"), Decimal("0"), SOURCE, (),
        (Goal("home", "HOME", Decimal("300"), date(2026, 9, 30),
              Decimal("0"), 28, 1, SOURCE),),
        BudgetPolicy(tuple(Allocation(category, Decimal("0"))
                           for category in C if category is not C.GOAL), Decimal("0"), SOURCE),
        True, True, protected_contributions_in_balance=())


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_each_shared_example_roundtrips_through_http_without_changing_calculation(
        scenario, monkeypatch):
    original = sample_input(scenario)
    seen = []
    direct = calculate_month(original)
    real = web.calculate_month

    def capture(data):
        result = real(data)
        seen.append(result)
        return result

    monkeypatch.setattr(web, "calculate_month", capture)
    with client() as browser:
        loaded = browser.get(f"/examples/{scenario}")
        assert loaded.status_code == 200
        assert "가상 예제 기반" in loaded.text
        assert original.evaluated_at.isoformat() in loaded.text
        result = submit(browser, flatten(from_budget(original, scenario)))
    assert result.status_code == 200
    assert seen == [direct]
    assert "가상 예제 기반" in result.text
    assert "현재 확인된 현금" in result.text
    assert result.headers["cache-control"].startswith("no-store")


def test_direct_form_starts_without_financial_defaults_and_requires_explicit_modes():
    with client() as browser:
        page = browser.get("/")
        assert 'name="cash_balance" type="text" value=""' in page.text
        assert 'name="income_complete"' in page.text
        assert 'name="policy_mode"' in page.text
        assert "저장되지 않는 미리보기" in page.text
        invalid = submit(browser, {})
        assert invalid.status_code == 422
        assert "기준 월" in invalid.text
        assert 'id="result"' not in invalid.text


def test_blank_is_not_zero_and_bad_values_are_retained():
    values = flatten(from_budget(sample_input("overspend"), ""))
    with client() as browser:
        browser.get("/")
        values["allocation.LIVING.amount"] = ""
        empty = submit(browser, values)
        assert empty.status_code == 422
        assert "0 이상의 유한한 십진 금액" in empty.text
        values["allocation.LIVING.amount"] = "0"
        zero = submit(browser, values)
        assert zero.status_code == 200
        assert 'id="result"' in zero.text
        values["cash_balance"] = "1234.567890123456789"
        exact = submit(browser, values)
        assert exact.status_code == 200
        assert "1234.567890123456789" in exact.text
        values["cash_balance"] = "NaN"
        bad = submit(browser, values)
        assert bad.status_code == 422
        assert 'value="NaN"' in bad.text
        assert 'id="result"' not in bad.text


@pytest.mark.parametrize("key,value", [
    ("month", "2026-13"), ("balance_date", "2026-09-99"),
    ("cash_balance", "Infinity"), ("cash_balance", "-1"),
    ("entry.0.kind", "FAKE"), ("entry.0.day", "1900-01-01"),
    ("entry.0.recorded_at", "2026-09-25T09:00:00"),
    ("example_id", "../../etc/passwd"),
])
def test_invalid_dates_amounts_enums_and_hidden_example_id_are_rejected(key, value):
    values = flatten(from_budget(sample_input("normal"), "normal"))
    values[key] = value
    with client() as browser:
        browser.get("/")
        response = submit(browser, values)
    assert response.status_code == 422
    assert 'id="result"' not in response.text


def test_duplicate_identity_missing_card_link_and_protection_inclusion_are_rejected():
    values = flatten(from_budget(sample_input("normal"), "normal"))
    with client() as browser:
        browser.get("/")
        values["entry.1.id"] = values["entry.0.id"]
        assert submit(browser, values).status_code == 422
        values["entry.1.id"] = "rent"
        values["entry.8.link_id"] = "missing-charge"
        assert submit(browser, values).status_code == 422
        values["entry.8.link_id"] = "card-use"
        assert submit(browser, values).status_code == 200
        values["contribution.0.goal_id"] = "home"
        values["contribution.0.day"] = "2026-09-05"
        values["contribution.0.amount"] = "300"
        values["contribution.0.recorded_at"] = "2026-09-05T18:00:00+09:00"
        values["contribution.0.source"] = SOURCE
        values["contribution.0.protection_source"] = "FREE_CASH"
        values["contribution.0.included"] = ""
        assert submit(browser, values).status_code == 422
        values["balance_date"] = "2026-09-25"
        values["contribution.0.included"] = "no"
        assert submit(browser, values).status_code == 422  # before balance snapshot; must be included
        values["contribution.0.included"] = "yes"
        assert submit(browser, values).status_code == 422  # existing protection is only 200 < 300


def test_missing_card_payment_date_obligation_survives_web_adapter():
    month = date(2026, 9, 1)
    stamp = datetime(2026, 9, 25, tzinfo=timezone.utc)
    allocations = tuple(Allocation(category, Decimal("900") if category is C.LIVING
                                   else Decimal("500") if category is C.US_INVEST else Decimal("0"))
                        for category in C if category is not C.GOAL)
    data = BudgetInput(month, stamp, month, Decimal("1000"), Decimal("0"), SOURCE,
                       (CashEntry("charge", date(2026, 9, 15), K.CARD_CHARGE, Decimal("900"),
                                  SOURCE, stamp, category=C.LIVING, observed=True),),
                       (), BudgetPolicy(allocations, Decimal("0"), SOURCE), True, True)
    with client() as browser:
        browser.get("/")
        response = submit(browser, flatten(from_budget(data, "")))
    assert response.status_code == 200
    assert "미결제 카드 의무" in response.text
    assert "900 원" in response.text
    assert "-400 원" in response.text
    assert "card_payment_date:charge" in response.text


def test_protected_snapshot_relation_is_not_inferred_or_double_counted():
    base = sample_input("overspend")
    goal = Goal("home", "HOME", Decimal("300"), date(2026, 9, 30),
                Decimal("300"), 5, 1, SOURCE,
                (GoalContribution(date(2026, 9, 5), Decimal("300"), SOURCE,
                                  base.evaluated_at, "FREE_CASH"),))
    data = replace(base, entries=(), goals=(goal,), existing_protected=Decimal("800"),
                   balance_date=date(2026, 9, 25),
                   protected_contributions_in_balance=(("home", date(2026, 9, 5)),))
    values = flatten(from_budget(data, ""))
    with client() as browser:
        browser.get("/")
        good = submit(browser, values)
        assert good.status_code == 200
        values["contribution.0.included"] = "no"
        bad = submit(browser, values)
        assert bad.status_code == 422
        assert "포함" in bad.text or "inclusion" in bad.text
        values["contribution.0.included"] = "yes"
        values["contribution.0.protection_source"] = "EXISTING"
        assert submit(browser, values).status_code == 422


def test_edit_recalculation_errors_and_request_isolation(monkeypatch):
    seen = []
    real = web.calculate_month
    def capture(data):
        seen.append(data.cash_balance)
        return real(data)
    monkeypatch.setattr(web, "calculate_month", capture)
    values = flatten(from_budget(sample_input("overspend"), ""))
    with client() as a, client() as b:
        a.get("/")
        b_page = b.get("/")
        assert "900" not in b_page.text  # no other tab's financial entries
        first = submit(a, values)
        assert first.status_code == 200
        values["cash_balance"] = "2000"
        second = submit(a, values)
        assert second.status_code == 200
        assert seen == [Decimal("1000"), Decimal("2000")]
        assert first.text != second.text
        assert 'id="result"' not in b.get("/").text
        values["cash_balance"] = "bad-value"
        error = submit(a, values)
        assert error.status_code == 422
        assert 'value="bad-value"' in error.text
        assert 'id="result"' not in error.text


def test_security_headers_host_origin_csrf_escape_limits_and_no_query_data(caplog):
    values = flatten(from_budget(sample_input("overspend"), ""))
    forged = "a" * 43 + "." + "b" * 43
    with client() as attacker:
        assert attacker.post("/calculate", data={**values, "csrf_token": forged},
                             headers={**ORIGIN, "Cookie": f"budget_csrf={forged}"}).status_code == 403
    with client() as browser:
        page = browser.get("/")
        assert page.headers["cache-control"].startswith("no-store")
        assert "'self'" in page.headers["content-security-policy"]
        assert browser.get("/docs").status_code == 404
        assert browser.get("/openapi.json").status_code == 404
        assert browser.get("/?cash_balance=999").status_code == 400
        assert browser.get("/", headers={"Host": "evil.example"}).status_code == 400
        assert browser.post("/calculate", data=values,
                            headers={"Origin": "http://evil.example"}).status_code == 403
        assert browser.post("/calculate", data=values,
                            headers={"Origin": "null"}).status_code == 403
        assert browser.post("/calculate", data=values, headers=ORIGIN).status_code == 403
        response = submit(browser, values)
        assert response.status_code == 200
        assert "budget_csrf" not in response.headers.get("set-cookie", "")
        assert "cash_balance" not in str(browser.cookies)
        values["balance_source"] = "<script>alert(1)</script>"
        escaped = submit(browser, values)
        assert escaped.status_code == 200
        assert "&lt;script&gt;" in escaped.text
        assert "<script>alert(1)</script>" not in escaped.text
        assert escaped.headers["cache-control"].startswith("no-store")
        oversized = browser.post("/calculate", content=b"x" * (MAX_BODY + 1),
                                 headers={**ORIGIN, "Content-Type": "application/x-www-form-urlencoded"})
        assert oversized.status_code == 413
        values["entry.40.id"] = "too-many"
        row_limit = submit(browser, values)
        assert row_limit.status_code == 422
        assert "최대 40행" in row_limit.text
        assert 'name="cash_balance" type="text" value="1000"' in row_limit.text
        values.pop("entry.40.id")
        values["entry.00.id"] = "bad-index"
        assert submit(browser, values).status_code == 422
        assert "alert(1)" not in caplog.text


def test_form_duplicate_fields_and_unknown_field_fail_closed():
    values = flatten(from_budget(sample_input("overspend"), ""))
    with client() as browser:
        browser.get("/")
        token = browser.cookies.get("budget_csrf")
        pairs = list(values.items()) + [("csrf_token", token), ("cash_balance", "5000")]
        response = browser.post("/calculate", content=urlencode(pairs),
                                headers={**ORIGIN, "Content-Type": "application/x-www-form-urlencoded"})
        assert response.status_code == 422
        values["mystery_hidden"] = "5000"
        rejected = submit(browser, values)
        assert rejected.status_code == 422
        assert 'name="cash_balance" type="text" value="1000"' in rejected.text
        values.pop("mystery_hidden")
        values.update({f"unknown_{i}": "x" for i in range(501)})
        too_many_fields = submit(browser, values)
        assert too_many_fields.status_code == 422
        assert "Max number of fields exceeded" in too_many_fields.text


def test_body_limit_stops_receiving_on_first_excess_chunk(monkeypatch):
    monkeypatch.setattr(web, "MAX_BODY", 11)

    async def post(chunks, length=None):
        seen = []
        async def stream():
            for index, chunk in enumerate(chunks):
                seen.append(index)
                yield chunk
        headers = {**ORIGIN, "Content-Type": "application/x-www-form-urlencoded"}
        if length is not None:
            headers["Content-Length"] = length
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web.app),
                                     base_url="http://127.0.0.1:8765") as browser:
            response = await browser.post("/calculate", content=stream(), headers=headers)
        return response, seen

    for length in (None, "11"):
        exact, seen = asyncio.run(post([b"csrf", b"_token", b"="], length))
        assert exact.status_code == 403
        assert seen == [0, 1, 2]
        below, seen = asyncio.run(post([b"csrf", b"_token"], length))
        assert below.status_code == 403
        assert seen == [0, 1]
        excess, seen = asyncio.run(post([b"aaaa", b"bbbb", b"cccc", b"dddd"],
                                        length if length is None else "8"))
        assert excess.status_code == 413
        assert seen == [0, 1, 2]  # fourth chunk was never requested
        assert excess.headers["cache-control"].startswith("no-store")
    declared_excess, seen = asyncio.run(post([b"unread"], "12"))
    assert declared_excess.status_code == 413
    assert seen == []
    for malformed in ("", "nope", "+11", "9" * 100):
        response, seen = asyncio.run(post([b"unread"], malformed))
        assert response.status_code in (400, 413)
        assert seen == []
        assert response.headers["cache-control"].startswith("no-store")


def test_complete_form_at_exact_body_limit(monkeypatch):
    values = flatten(from_budget(sample_input("overspend"), ""))
    with client() as browser:
        browser.get("/")
        payload = urlencode({**values, "csrf_token": browser.cookies.get("budget_csrf")}).encode()
        monkeypatch.setattr(web, "MAX_BODY", len(payload))
        exact = browser.post("/calculate", content=payload,
                             headers={**ORIGIN, "Content-Type": "application/x-www-form-urlencoded"})
        assert exact.status_code == 200
        monkeypatch.setattr(web, "MAX_BODY", len(payload) - 1)
        excess = browser.post("/calculate", content=payload,
                              headers={**ORIGIN, "Content-Type": "application/x-www-form-urlencoded"})
        assert excess.status_code == 413


def test_invalid_csrf_and_origin_are_explicit_rejections_with_security_headers(monkeypatch):
    values = flatten(from_budget(sample_input("overspend"), ""))
    with client() as browser:
        browser.get("/")
        token = browser.cookies.get("budget_csrf")
        changed = "A" if token[44] != "A" else "B"
        for submitted in (token + "가", token[:44] + changed + token[45:]):
            response = browser.post("/calculate", data={**values, "csrf_token": submitted},
                                    headers=ORIGIN)
            assert response.status_code == 403
            assert response.headers["cache-control"].startswith("no-store")
            assert response.headers["x-content-type-options"] == "nosniff"
            assert "'self'" in response.headers["content-security-policy"]
        assert submit(browser, values).status_code == 200
        for origin in ("http://[", "null", "http://evil.example",
                       "http://127.0.0.1:8765/", "http://127.0.0.1:8765/?x=1",
                       "http://127.0.0.1:8765/#x", "https://127.0.0.1:8765"):
            response = browser.post("/calculate", data={**values, "csrf_token": token},
                                    headers={"Origin": origin})
            assert response.status_code == 403
            assert response.headers["cache-control"].startswith("no-store")
            assert response.headers["x-frame-options"] == "DENY"
        missing = browser.post("/calculate", data={**values, "csrf_token": token})
        assert missing.status_code == 403
        assert missing.headers["cache-control"].startswith("no-store")
        monkeypatch.setattr(web, "_CSRF_SECRET", b"rotated-process-secret" * 2)
        expired = browser.post("/calculate", data={**values, "csrf_token": token}, headers=ORIGIN)
        assert expired.status_code == 403
        assert expired.headers["cache-control"].startswith("no-store")


def test_goal_allocation_unset_zero_and_positive_are_distinct_and_roundtrip():
    base = goal_input()
    form = from_budget(base, "")
    assert form["goals"][0]["allocation_state"] == "unset"
    assert to_budget(form) == base
    unset = calculate_month(to_budget(form))
    assert "allocation:GOAL:home" in unset.missing
    assert not any(item.category is C.GOAL for item in to_budget(form).policy.allocations)

    form["goals"][0]["allocation_state"] = "none"
    zero = to_budget(form)
    assert [item.amount for item in zero.policy.allocations if item.category is C.GOAL] == [Decimal("0")]
    assert calculate_month(zero).goals[0].shortfall == Decimal("300")
    assert "allocation:GOAL:home" not in calculate_month(zero).missing
    assert from_budget(zero, "")["goals"][0]["allocation_state"] == "none"

    form["goals"][0]["allocation_state"] = "amount"
    form["goals"][0]["allocation_amount"] = "0"
    assert to_budget(form) == zero
    form["goals"][0]["allocation_amount"] = "100"
    positive = to_budget(form)
    assert calculate_month(positive).goals[0].shortfall == Decimal("200")
    assert from_budget(positive, "")["goals"][0]["allocation_state"] == "amount"

    form["goals"][0]["allocation_amount"] = ""
    with pytest.raises(FormError):
        to_budget(form)
    form["goals"][0]["allocation_state"] = "unset"
    form["goals"][0]["allocation_amount"] = "0"
    with pytest.raises(FormError):
        to_budget(form)

    no_policy = replace(base, policy=None)
    assert from_budget(no_policy, "")["goals"][0]["allocation_state"] == "unset"
    assert to_budget(from_budget(no_policy, "")) == no_policy
    no_policy_form = from_budget(no_policy, "")
    no_policy_form["goals"][0]["allocation_state"] = "none"
    with pytest.raises(FormError):
        to_budget(no_policy_form)
    unknown = replace(base, goals=(replace(base.goals[0], target_amount=None, deadline=None),))
    converted_unknown = to_budget(from_budget(unknown, ""))
    assert converted_unknown.goals[0].target_amount is None
    assert converted_unknown.goals[0].deadline is None


def test_core_form_conversion_requires_explicit_zero_and_preserves_time():
    original = sample_input("goal_conflict")
    form = from_budget(original, "goal_conflict")
    converted = to_budget(form_from_values(flatten(form)))
    assert converted.evaluated_at == original.evaluated_at
    assert calculate_month(converted) == calculate_month(original)
