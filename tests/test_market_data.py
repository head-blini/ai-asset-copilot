"""Domain validation and freshness require neither credentials nor internet."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from asset_copilot.domain.models import Currency
from asset_copilot.market import FxQuote, MarketQuote, is_stale


NOW = datetime(2026, 9, 22, 15, tzinfo=timezone.utc)


def test_market_quote_keeps_asset_identity_and_normalizes_utc():
    local = datetime(2026, 9, 22, 11, tzinfo=timezone(timedelta(hours=-4)))
    quote = MarketQuote("us:voo", Decimal("630.123456789"), Currency.USD,
                        local, NOW, "twelve_data")
    assert quote.asset_id == "us:voo"
    assert quote.price == Decimal("630.123456789")
    assert quote.as_of == NOW
    assert quote.as_of.tzinfo is timezone.utc


@pytest.mark.parametrize("price", [0, -1, 1.1, Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_market_quote_rejects_invalid_price(price):
    with pytest.raises(ValueError, match="price"):
        MarketQuote("asset", price, Currency.USD, NOW, NOW, "source")


@pytest.mark.parametrize("field", ["as_of", "fetched_at"])
def test_quotes_require_aware_times(field):
    args = dict(asset_id="asset", price=Decimal("1"), currency=Currency.USD,
                as_of=NOW, fetched_at=NOW, source="source")
    args[field] = datetime(2026, 9, 22)
    with pytest.raises(ValueError, match=field):
        MarketQuote(**args)


def test_quotes_validate_currency_and_optional_market_time():
    with pytest.raises(ValueError, match="currency"):
        MarketQuote("asset", Decimal("1"), "USD", NOW, NOW, "source")
    quote = MarketQuote("asset", Decimal("1"), Currency.USD, None, NOW, "source")
    assert quote.as_of is None
    assert is_stale(quote, NOW, timedelta(minutes=5))


def test_fx_direction_and_validation():
    fx = FxQuote(Currency.USD, Currency.KRW, Decimal("1370.25"), NOW, NOW, "source")
    assert fx.base_currency is Currency.USD
    assert fx.quote_currency is Currency.KRW
    assert fx.rate == Decimal("1370.25")  # 1 USD = 1370.25 KRW
    with pytest.raises(ValueError, match="different"):
        FxQuote(Currency.USD, Currency.USD, Decimal("1"), NOW, NOW, "source")
    for rate in (Decimal("0"), Decimal("-1"), Decimal("NaN"), Decimal("Infinity"), 1.2):
        with pytest.raises(ValueError, match="rate"):
            FxQuote(Currency.USD, Currency.KRW, rate, NOW, NOW, "source")


def test_staleness_boundary_future_time_and_policy_input():
    quote = MarketQuote("asset", Decimal("1"), Currency.USD,
                        NOW - timedelta(minutes=5), NOW, "source")
    assert not is_stale(quote, NOW, timedelta(minutes=5))
    assert is_stale(quote, NOW + timedelta(seconds=1), timedelta(minutes=5))
    assert is_stale(quote, NOW - timedelta(minutes=6), timedelta(minutes=5))
    with pytest.raises(ValueError, match="max_age"):
        is_stale(quote, NOW, timedelta(seconds=-1))
    with pytest.raises(ValueError, match="reference_time"):
        is_stale(quote, datetime(2026, 9, 22), timedelta(minutes=5))
