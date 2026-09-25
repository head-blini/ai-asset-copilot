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
        mobile.goto(URL + "examples/overspend")
        calculate(mobile)
        mobile.screenshot(path=str(OUT / "budget-web-mobile.png"), full_page=True)
        mobile.goto(URL + "examples/normal")
        calculate(mobile)
        browser.close()
    print("Chromium desktop 1440px: direct input, calculation, edit and recalculation passed")
    print("Chromium mobile 390px: direct input, calculation and horizontal layout passed")
    print("Screenshots:", OUT / "budget-web-desktop.png", OUT / "budget-web-mobile.png")


if __name__ == "__main__":
    main()
