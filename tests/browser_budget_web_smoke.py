"""Real Chromium smoke; run against the loopback server with web-test extra installed.

    python tests/browser_budget_web_smoke.py

Uses only synthetic values. Writes desktop/mobile screenshots to docs/images.
"""

from pathlib import Path
import re

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "images"
URL = "http://127.0.0.1:8765/"
CATEGORIES = ("FIXED", "LIVING", "FREEDOM", "DEBT_PRINCIPAL", "DEBT_COST",
              "EMERGENCY", "US_INVEST", "KR_STRATEGY")


def fill_direct(page):
    page.goto(URL)
    for name, value in {
        "month": "2026-09", "evaluated_at": "2026-09-25T18:00:00+09:00",
        "balance_date": "2026-09-25", "cash_balance": "1000",
        "existing_protected": "0", "protected_floor": "0",
    }.items():
        page.locator(f'[name="{name}"]').fill(value)
    for name, value in {
        "income_complete": "yes", "obligations_complete": "yes",
        "entries_mode": "none", "goals_mode": "none", "policy_mode": "rows",
    }.items():
        page.locator(f'[name="{name}"]').select_option(value)
    for category in CATEGORIES:
        page.locator(f'[name="allocation.{category}.state"]').select_option(
            "amount" if category in ("LIVING", "US_INVEST") else "none")
    page.locator('[name="allocation.LIVING.amount"]').fill("200")
    page.locator('[name="allocation.US_INVEST.amount"]').fill("500")


def calculate(page):
    page.get_by_role("button", name="월간 예산 계산").click()
    page.wait_for_load_state("networkidle")
    assert page.locator("#result").count() == 1, page.locator("body").inner_text()[:400]
    assert page.locator("#form-error").count() == 0
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")


def compact(text):
    return re.sub(r"\s+", "", text)


def goal_selection_path(page):
    fill_direct(page)
    page.locator('[name="goals_mode"]').select_option("rows")
    page.locator("details.detail-panel").nth(1).locator("summary").click()
    page.locator('.add-row[data-kind="goal"]').click()
    for name, value in {
        "id": "home", "target_amount": "300", "deadline": "2026-09-30",
        "saved_amount": "0", "contribution_day": "28", "priority": "1",
    }.items():
        page.locator(f'[name="goal.0.{name}"]').fill(value)
    page.locator('[name="goal.0.kind"]').select_option("HOME")
    state = page.locator('[name="goal.0.allocation_state"]')
    state.select_option("unset")
    calculate(page)
    assert "목표home의이번달배정확인필요" in compact(page.locator("#result").inner_text())
    assert state.input_value() == "unset"

    state.select_option("none")
    assert page.locator("#result").count() == 0
    calculate(page)
    assert "목표home의이번달배정확인필요" not in compact(page.locator("#result").inner_text())
    allocation_row = page.locator("#result table").first.locator("tr").filter(has_text="home")
    assert allocation_row.locator("td").first.inner_text() == "0"
    zero_goal = page.locator(".goal-results article").first.inner_text()
    zero_metrics = page.locator(".metrics").inner_text()

    state.select_option("amount")
    page.locator('[name="goal.0.allocation_amount"]').fill("0")
    calculate(page)
    assert page.locator(".goal-results article").first.inner_text() == zero_goal
    assert page.locator(".metrics").inner_text() == zero_metrics
    assert allocation_row.locator("td").first.inner_text() == "0"

    page.locator('[name="goal.0.allocation_amount"]').fill("100")
    assert page.locator("#result").count() == 0
    calculate(page)
    assert allocation_row.locator("td").first.inner_text() == "100"
    assert "200" in page.locator(".goal-results article").first.inner_text()

    page.locator('[name="goal.0.allocation_amount"]').fill("")
    assert page.locator("#result").count() == 0
    page.get_by_role("button", name="월간 예산 계산").click()
    page.wait_for_load_state("networkidle")
    assert page.locator("#form-error").count() == 1
    assert page.locator("#result").count() == 0
    assert state.input_value() == "amount"
    assert page.locator('[name="goal.0.allocation_amount"]').input_value() == ""
    page.locator('[name="goal.0.allocation_amount"]').fill("100")
    calculate(page)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        desktop = browser.new_page(viewport={"width": 1440, "height": 900})
        requests = []
        desktop.on("request", lambda req: requests.append(req.url))
        fill_direct(desktop)
        desktop.locator("details.detail-panel").first.locator("summary").click()
        desktop.locator('.add-row[data-kind="entry"]').click()
        assert desktop.locator('[name="entry.0.id"]').count() == 1
        desktop.locator('#entry-rows .remove-row').click()
        assert desktop.locator('[name="entry.0.id"]').count() == 0
        calculate(desktop)
        assert "현재배정여력300원" in compact(desktop.locator(".metrics").inner_text())
        desktop.locator('[name="cash_balance"]').fill("800")
        assert desktop.locator("#result").count() == 0
        assert not desktop.locator("#dirty-message").is_hidden()
        calculate(desktop)
        assert "현재배정여력100원" in compact(desktop.locator(".metrics").inner_text())
        desktop.locator('[name="cash_balance"]').fill("bad")
        assert desktop.locator("#result").count() == 0
        desktop.get_by_role("button", name="월간 예산 계산").click()
        desktop.wait_for_load_state("networkidle")
        assert desktop.locator("#form-error").count() == 1
        assert desktop.locator('[name="cash_balance"]').input_value() == "bad"
        desktop.locator('[name="cash_balance"]').fill("800")
        calculate(desktop)
        goal_selection_path(desktop)
        desktop.once("dialog", lambda dialog: dialog.accept())
        desktop.locator('.example-link[href="/examples/normal"]').click()
        desktop.wait_for_load_state("networkidle")
        assert desktop.locator('[name="evaluated_at"]').input_value() == "2026-09-25T09:00:00+00:00"
        assert "가상 예제 기반" in desktop.locator(".example-badge").inner_text()
        calculate(desktop)
        desktop.once("dialog", lambda dialog: dialog.accept())
        desktop.locator('.example-link[href="/examples/overspend"]').click()
        desktop.wait_for_load_state("networkidle")
        calculate(desktop)
        desktop.screenshot(path=str(OUT / "budget-web-desktop.png"), full_page=True)
        assert all(url.startswith(URL) for url in requests), requests
        mobile = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True,
                                  has_touch=True)
        fill_direct(mobile)
        calculate(mobile)
        assert "현재배정여력300원" in compact(mobile.locator(".metrics").inner_text())
        mobile.locator('[name="cash_balance"]').fill("800")
        assert mobile.locator("#result").count() == 0
        calculate(mobile)
        assert "현재배정여력100원" in compact(mobile.locator(".metrics").inner_text())
        goal_selection_path(mobile)
        mobile.goto(URL + "examples/overspend")
        calculate(mobile)
        mobile.screenshot(path=str(OUT / "budget-web-mobile.png"), full_page=True)
        mobile.goto(URL + "examples/normal")
        calculate(mobile)
        browser.close()
    print("Chromium desktop 1440px: direct input, edit, goal states and recalculation passed")
    print("Chromium mobile 390px: direct input, edit, goal states and recalculation passed")
    print("Screenshots:", OUT / "budget-web-desktop.png", OUT / "budget-web-mobile.png")


if __name__ == "__main__":
    main()
