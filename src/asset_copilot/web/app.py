"""Loopback-only preview for manual monthly budget input."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from asset_copilot.budget import BudgetCategory, EntryKind, calculate_month
from asset_copilot.budget.examples import SCENARIOS, sample_input
from asset_copilot.web.forms import (MAX_BODY, MAX_FIELDS, FormError, empty_form,
                                     form_from_values, from_budget, to_budget)

ROOT = Path(__file__).resolve().parent
app = FastAPI(title="로컬 월간 예산 미리보기", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
templates = Jinja2Templates(directory=ROOT / "templates")
HOST = re.compile(r"(?:127\.0\.0\.1|localhost)(?::[0-9]{1,5})?\Z", re.I)
_CSRF_SECRET = secrets.token_bytes(32)  # Process-local; contains no financial data.
LABELS = {
    "FIXED": "고정비", "LIVING": "생활비", "FREEDOM": "자유지출",
    "DEBT_PRINCIPAL": "부채 원금", "DEBT_COST": "부채 이자·비용",
    "EMERGENCY": "비상자금", "GOAL": "목표 적립", "US_INVEST": "미국 장기투자",
    "KR_STRATEGY": "한국 전략 자금", "INCOME_ACTUAL": "실제 소득",
    "INCOME_PLANNED": "예정 소득", "INCOME_UNCERTAIN": "불확실 소득",
    "CASH_SPEND": "현금 지출", "CARD_CHARGE": "카드 사용",
    "CARD_PAYMENT": "카드 납부", "DEBT_PRINCIPAL_ENTRY": "부채 원금 상환",
    "DEBT_COST_ENTRY": "부채 이자 지급", "TRANSFER_IN": "본인 계좌 입금",
    "TRANSFER_OUT": "본인 계좌 출금", "UNKNOWN": "확인 불가",
    "NOT_REQUIRED": "검사 불필요", "CHECKED": "검사 완료", "OBSERVED": "관측 완료",
    "PARTIAL": "부분 납입", "PLANNED": "예정", "OVERDUE_UNCONFIRMED": "지난 납입 미확인",
    "HOME": "주택", "RETIREMENT": "노후", "OTHER": "기타",
    "OBSERVED_REPLAY": "과거 관측 재생", "TODAY_FORECAST": "오늘 추정",
    "FUTURE_FORECAST": "미래 전망", "FORECAST": "전망",
}
ASSUMPTIONS = {
    "Day figures are end-of-day estimates; intraday order is unknown.":
        "날짜별 수치는 일마감 추정이며 하루 안의 거래 순서는 확인되지 않았습니다.",
    "Planned income is forecast only until observed; overdue and uncertain income is excluded.":
        "예정 소득은 관측 전까지 전망이며, 지난 미확인·불확실 소득은 현재 재원에서 제외합니다.",
    "With incomplete records, ending cash uses known entries only and shortage is UNKNOWN.":
        "기록이 불완전하면 확인된 내역으로만 현금을 계산하고 부족 판정은 확인 불가입니다.",
    "Allocation is a proposal, not approval, transfer or order.":
        "배정은 제안이며 승인·이체·주문이 아닙니다.",
}


def display(value):
    if value is None:
        return "확인 불가"
    if hasattr(value, "value"):
        value = value.value
    return LABELS.get(value, str(value))


templates.env.filters["display"] = display


def explain(value: str) -> str:
    if value in ASSUMPTIONS:
        return ASSUMPTIONS[value]
    if value == "protected_floor":
        return "보호총액 하한 확인 필요 (protected_floor)"
    if value in ("target_amount", "deadline"):
        return ("목표금액" if value == "target_amount" else "목표 기한") + " 확인 필요"
    if value.startswith("goal:") and value.count(":") == 2:
        _, goal_id, field = value.split(":")
        return f"목표 {goal_id}의 {explain(field)}"
    if value.startswith("allocation:GOAL:"):
        return f"목표 {value.removeprefix('allocation:GOAL:')}의 이번 달 배정 확인 필요"
    if value.startswith("income_unconfirmed:"):
        return f"예정 소득 {value.removeprefix('income_unconfirmed:')}의 실제 입금 확인 필요"
    if value.startswith("card_payment_date:"):
        return f"카드 사용 {value.removeprefix('card_payment_date:')}의 납부일 확인 필요 ({value})"
    match = re.fullmatch(r"current allocations and unpaid card dues exceed confirmed funding by (.+)", value)
    if match:
        return f"현재 배정과 미결제 카드 의무가 확인된 자금을 {match[1]}원 초과합니다."
    match = re.fullmatch(r"([0-9-]+) end-of-day cash shortage (.+); entries: (.+)", value)
    if match:
        return f"{match[1]} 일마감 총현금 {match[2]}원 부족 · 관련 내역: {match[3]}"
    match = re.fullmatch(
        r"([0-9-]+) available cash after protection and goal allocation short by (.+); entries: (.+)",
        value)
    if match:
        return f"{match[1]} 보호액·목표 배정 후 가용현금 {match[2]}원 부족 · 관련 내역: {match[3]}"
    match = re.fullmatch(r"([A-Z_]+) used/reserved exceeds allocation by (.+)", value)
    if match:
        return f"{display(match[1])} 사용·예약이 배정액보다 {match[2]}원 많습니다."
    match = re.fullmatch(r"planned income (.+) is overdue and unconfirmed at ([0-9-]+)", value)
    if match:
        return f"예정 소득 {match[1]}은 {match[2]} 기준 기일이 지났으나 입금이 확인되지 않았습니다."
    return value


templates.env.filters["explain"] = explain


@app.middleware("http")
async def local_boundary(request: Request, call_next):
    host = request.headers.get("host", "")
    if not HOST.fullmatch(host) or (":" in host and int(host.rsplit(":", 1)[1]) > 65535):
        response = PlainTextResponse("허용되지 않은 Host입니다.", status_code=400)
    elif request.url.query:
        response = PlainTextResponse("URL query 입력은 지원하지 않습니다.", status_code=400)
    elif request.method == "POST" and not _same_origin(request, host):
        response = PlainTextResponse("외부 Origin의 계산 요청은 거부합니다.", status_code=403)
    else:
        response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; style-src 'self'; script-src 'self'; "
        "form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
    )
    return response


def _same_origin(request: Request, host: str) -> bool:
    origin = request.headers.get("origin", "")
    parsed = urlsplit(origin)
    return parsed.scheme == "http" and parsed.netloc.lower() == host.lower() \
        and not parsed.username and not parsed.password and not parsed.path


def _token(request: Request) -> tuple[str, bool]:
    current = request.cookies.get("budget_csrf", "")
    if _valid_token(current):
        return current, False
    nonce = secrets.token_urlsafe(32)
    signature = base64.urlsafe_b64encode(hmac.new(
        _CSRF_SECRET, nonce.encode("ascii"), hashlib.sha256).digest()).rstrip(b"=").decode("ascii")
    return nonce + "." + signature, True


def _valid_token(token: str) -> bool:
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}\.[A-Za-z0-9_-]{43}", token):
        return False
    nonce, signature = token.split(".", 1)
    expected = base64.urlsafe_b64encode(hmac.new(
        _CSRF_SECRET, nonce.encode("ascii"), hashlib.sha256).digest()).rstrip(b"=").decode("ascii")
    return secrets.compare_digest(signature, expected)


def _page(request: Request, form: dict, *, result=None, error: FormError | None = None,
          code: int = 200) -> HTMLResponse:
    token, fresh = _token(request)
    anchor = error.field if error else ""
    if anchor == "form":
        anchor = "budget-form"
    elif anchor in ("entry", "entries"):
        anchor = "entry-rows"
    elif anchor in ("goal", "goals"):
        anchor = "goal-rows"
    elif anchor in ("contribution", "contributions"):
        anchor = "contribution-rows"
    response = templates.TemplateResponse(request, "index.html", {
        "form": form, "result": result, "error": error, "token": token,
        "error_anchor": anchor,
        "scenarios": SCENARIOS, "categories": tuple(c for c in BudgetCategory
                                                if c is not BudgetCategory.GOAL),
        "entry_options": tuple((kind.value, LABELS.get(kind.value, kind.value))
                               for kind in EntryKind), "labels": LABELS,
    }, status_code=code)
    if fresh:
        response.set_cookie("budget_csrf", token, httponly=True, samesite="strict",
                            secure=False, path="/", max_age=3600)
    return response


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return _page(request, empty_form())


@app.get("/examples/{scenario}", response_class=HTMLResponse)
async def example(request: Request, scenario: str):
    if scenario not in SCENARIOS:
        return PlainTextResponse("알 수 없는 가상 예제입니다.", status_code=404)
    return _page(request, from_budget(sample_input(scenario), scenario))


@app.post("/calculate", response_class=HTMLResponse)
async def calculate(request: Request):
    if request.headers.get("content-type", "").split(";", 1)[0].lower() != \
            "application/x-www-form-urlencoded":
        return PlainTextResponse("HTML 폼 전송만 허용합니다.", status_code=415)
    declared = request.headers.get("content-length", "")
    if declared and (not declared.isdecimal() or int(declared) > MAX_BODY):
        return PlainTextResponse("입력 본문 크기 제한을 초과했습니다.", status_code=413)
    body = await request.body()
    if len(body) > MAX_BODY:
        return PlainTextResponse("입력 본문 크기 제한을 초과했습니다.", status_code=413)
    try:
        pairs = parse_qsl(body.decode("utf-8", errors="strict"), keep_blank_values=True,
                          max_num_fields=MAX_FIELDS, errors="strict")
        values = dict(pairs)
        if len(values) != len(pairs):
            raise FormError("form", "중복 전송 필드가 있습니다.")
        if any(len(key) > 80 or len(value) > 200 for key, value in pairs):
            raise FormError("form", "필드 길이 제한을 초과했습니다.")
        cookie = request.cookies.get("budget_csrf", "")
        submitted = values.get("csrf_token", "")
        if not _valid_token(cookie) or not submitted or not secrets.compare_digest(cookie, submitted):
            return PlainTextResponse("CSRF 확인에 실패했습니다.", status_code=403)
        form = form_from_values(values)
        if form["example_id"] and form["example_id"] not in SCENARIOS:
            raise FormError("example_id", "알 수 없는 가상 예제 식별자입니다.")
        data = to_budget(form)
        result = calculate_month(data)
        return _page(request, form, result=result)
    except FormError as exc:
        try:
            form = form_from_values(values, strict=False)
        except (UnboundLocalError, FormError):
            form = empty_form()
        return _page(request, form, error=exc, code=422)
    except (ValueError, UnicodeError) as exc:
        try:
            form = form_from_values(values, strict=False)
        except (UnboundLocalError, FormError):
            form = empty_form()
        return _page(request, form, error=FormError("form", str(exc)), code=422)


def main() -> None:
    import uvicorn
    uvicorn.run("asset_copilot.web.app:app", host="127.0.0.1", port=8765,
                access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
