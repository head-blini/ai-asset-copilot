"""Provider parsing and transport behavior are tested entirely with fake HTTP."""

import json
from datetime import datetime, timezone
from decimal import Decimal
from http.client import IncompleteRead
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

import pytest

from asset_copilot.domain.models import Asset, AssetType, Currency
from asset_copilot.market.twelve_data import (
    AuthenticationError, InstrumentError, NetworkError, RateLimitError,
    RequestTimeoutError, ResponseError, TwelveDataInstrument,
    TwelveDataMarketDataProvider,
)


NOW = datetime(2026, 9, 22, tzinfo=timezone.utc)


def asset(asset_id="us:voo", ticker="VOO", kind=AssetType.ETF):
    return Asset(id=asset_id, ticker=ticker, name="Example", asset_type=kind,
                 market="US", exchange="NYSE ARCA", currency=Currency.USD)


class FakeHttp:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def __call__(self, request, timeout):
        self.calls.append((urlparse(request.full_url), timeout))
        if isinstance(self.response, Exception):
            raise self.response
        if isinstance(self.response, bytes):
            return self.response
        return json.dumps(self.response).encode()


def provider(response, instruments=None):
    http = FakeHttp(response)
    adapter = TwelveDataMarketDataProvider(
        instruments or {"us:voo": TwelveDataInstrument("VOO", "NYSE ARCA")},
        api_key="test-only-placeholder", http_get=http, clock=lambda: NOW,
    )
    return adapter, http


@pytest.mark.parametrize("kind,ticker", [(AssetType.STOCK, "AMAT"), (AssetType.ETF, "VOO")])
def test_stock_and_etf_quote_parsing_and_symbol_mapping(kind, ticker):
    response = {"symbol": ticker, "currency": "USD", "close": "630.12345678901234567890",
                "timestamp": 1789999200, "last_quote_at": 1789999200}
    adapter, http = provider(response, {"id:1": TwelveDataInstrument(ticker, "NASDAQ")})
    quote = adapter.get_quotes([asset("id:1", "IGNORED-TICKER", kind)])["id:1"]
    assert quote.price == Decimal("630.12345678901234567890")
    assert quote.asset_id == "id:1" and quote.currency is Currency.USD
    assert quote.as_of == datetime(2026, 9, 21, 14, tzinfo=timezone.utc)
    assert quote.fetched_at == NOW and quote.source == "twelve_data"
    assert http.calls[0][0].path == "/quote"
    assert parse_qs(http.calls[0][0].query)["symbol"] == [ticker]
    assert parse_qs(http.calls[0][0].query)["exchange"] == ["NASDAQ"]
    assert parse_qs(http.calls[0][0].query)["interval"] == ["1min"]
    assert http.calls[0][1] == 5.0


def test_missing_or_mismatched_minute_time_has_unknown_as_of():
    adapter, _ = provider({"symbol": "VOO", "currency": "USD", "close": "630", "timestamp": 1})
    assert adapter.get_quotes([asset()])["us:voo"].as_of is None
    adapter, _ = provider({"symbol": "VOO", "currency": "USD", "close": "630",
                           "timestamp": 1789999200, "last_quote_at": 1789999260})
    assert adapter.get_quotes([asset()])["us:voo"].as_of is None


def test_same_ticker_different_asset_ids_use_explicit_mapping():
    seen = []

    def get(request, timeout):
        params = parse_qs(urlparse(request.full_url).query)
        seen.append(params["exchange"][0])
        return json.dumps({"symbol": "ABC", "currency": "USD",
                           "close": "10" if seen[-1] == "NYSE" else "20"}).encode()

    adapter = TwelveDataMarketDataProvider(
        {"nyse:abc": TwelveDataInstrument("ABC", "NYSE"),
         "nasdaq:abc": TwelveDataInstrument("ABC", "NASDAQ")},
        api_key="test-only-placeholder", http_get=get, clock=lambda: NOW)
    quotes = adapter.get_quotes([asset("nyse:abc", "ABC"), asset("nasdaq:abc", "ABC")])
    assert quotes["nyse:abc"].price == Decimal("10")
    assert quotes["nasdaq:abc"].price == Decimal("20")
    assert seen == ["NYSE", "NASDAQ"]


def test_fx_pair_direction_timestamp_and_json_decimal_number():
    adapter, http = provider(b'{"symbol":"USD/KRW","rate":1370.1234567890123456789,"timestamp":1789999200}')
    fx = adapter.get_fx_rate(Currency.USD, Currency.KRW)
    assert fx.rate == Decimal("1370.1234567890123456789")
    assert fx.as_of == datetime(2026, 9, 21, 14, tzinfo=timezone.utc)
    assert fx.fetched_at == NOW and fx.source == "twelve_data"
    assert parse_qs(http.calls[0][0].query)["symbol"] == ["USD/KRW"]


@pytest.mark.parametrize("value", [None, "", "0", "-1", "NaN", "Infinity", True,
                                          "1" * 65, "1e999999", "1e31"])
def test_invalid_missing_or_unbounded_price(value):
    adapter, _ = provider({"symbol": "VOO", "currency": "USD", "close": value})
    with pytest.raises(ResponseError, match="price"):
        adapter.get_quotes([asset()])


def test_invalid_fx_rate_and_malformed_json():
    adapter, _ = provider({"symbol": "USD/KRW", "rate": "NaN"})
    with pytest.raises(ResponseError, match="FX rate"):
        adapter.get_fx_rate(Currency.USD, Currency.KRW)
    for response in (b"{", b"[]", b'{"symbol":"VOO","currency":"USD"}'):
        adapter, _ = provider(response)
        with pytest.raises(ResponseError):
            adapter.get_quotes([asset()])


def test_numeric_token_and_response_size_are_bounded_before_full_parsing():
    adapter, _ = provider(b'{"symbol":"VOO","currency":"USD","close":' + b"1" * 65 + b"}")
    with pytest.raises(ResponseError, match="numeric token"):
        adapter.get_quotes([asset()])
    adapter, _ = provider(b" " * 65537)
    with pytest.raises(ResponseError, match="size limit"):
        adapter.get_quotes([asset()])
    adapter, _ = provider(b"[" * 1000 + b"0" + b"]" * 1000)
    with pytest.raises(ResponseError, match="malformed"):
        adapter.get_quotes([asset()])


@pytest.mark.parametrize("code,error", [(400, InstrumentError), (401, AuthenticationError), (403, AuthenticationError),
                                          (429, RateLimitError), (404, InstrumentError), (500, ResponseError)])
def test_http_errors_are_normalized(code, error):
    adapter, _ = provider(HTTPError("https://example.test", code, "error", {}, None))
    with pytest.raises(error):
        adapter.get_quotes([asset()])


@pytest.mark.parametrize("code,error", [(401, AuthenticationError), (429, RateLimitError),
                                          (400, InstrumentError), (500, ResponseError)])
def test_provider_error_payload_is_normalized(code, error):
    adapter, _ = provider({"status": "error", "code": code, "message": "secret-free error"})
    with pytest.raises(error):
        adapter.get_quotes([asset()])


@pytest.mark.parametrize("failure,error", [(TimeoutError(), RequestTimeoutError),
                                             (URLError("offline"), NetworkError),
                                             (IncompleteRead(b"partial"), NetworkError)])
def test_transport_failures_are_normalized(failure, error):
    adapter, _ = provider(failure)
    with pytest.raises(error):
        adapter.get_quotes([asset()])


def test_missing_mapping_invalid_symbol_currency_and_key(monkeypatch):
    adapter, _ = provider({"symbol": "OTHER", "currency": "USD", "close": "1"})
    with pytest.raises(ResponseError, match="symbol"):
        adapter.get_quotes([asset()])
    with pytest.raises(InstrumentError, match="mapping"):
        adapter.get_quotes([asset("unknown")])
    adapter, _ = provider({"symbol": "VOO", "currency": "KRW", "close": "1"})
    with pytest.raises(ResponseError, match="currency"):
        adapter.get_quotes([asset()])
    adapter, _ = provider({"symbol": "VOO", "exchange": "OTHER", "currency": "USD", "close": "1"})
    with pytest.raises(ResponseError, match="exchange"):
        adapter.get_quotes([asset()])
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)
    with pytest.raises(AuthenticationError, match="required"):
        TwelveDataMarketDataProvider({})


def test_fx_pair_mismatch_and_invalid_timestamp_are_rejected():
    adapter, _ = provider({"symbol": "KRW/USD", "rate": "0.001", "timestamp": 1789999200})
    with pytest.raises(ResponseError, match="FX pair"):
        adapter.get_fx_rate(Currency.USD, Currency.KRW)
    adapter, _ = provider({"symbol": "VOO", "currency": "USD", "close": "1", "last_quote_at": "bad"})
    with pytest.raises(ResponseError, match="timestamp"):
        adapter.get_quotes([asset()])


def test_missing_fx_timestamp_and_duplicate_asset_ids():
    adapter, _ = provider({"symbol": "USD/KRW", "rate": "1370"})
    assert adapter.get_fx_rate(Currency.USD, Currency.KRW).as_of is None
    adapter, _ = provider({"symbol": "VOO", "currency": "USD", "close": "630"})
    with pytest.raises(ValueError, match="duplicate asset_id"):
        adapter.get_quotes([asset(), asset()])


def test_api_key_is_trimmed_without_exposing_it_in_transport_error():
    def failed(request, timeout):
        assert "apikey" not in parse_qs(urlparse(request.full_url).query)
        assert request.get_header("Authorization") == "apikey test-only-placeholder"
        raise URLError("request failed for " + request.full_url)

    adapter = TwelveDataMarketDataProvider(
        {"us:voo": TwelveDataInstrument("VOO", "NYSE ARCA")},
        api_key="  test-only-placeholder  ", http_get=failed)
    with pytest.raises(NetworkError) as captured:
        adapter.get_quotes([asset()])
    assert "test-only-placeholder" not in str(captured.value)


def test_batch_error_never_returns_partial_quotes():
    seen = []

    def get(request, timeout):
        seen.append(parse_qs(urlparse(request.full_url).query)["symbol"][0])
        if len(seen) == 2:
            raise HTTPError(request.full_url, 429, "rate limited", {}, None)
        return b'{"symbol":"VOO","currency":"USD","close":"630"}'

    adapter = TwelveDataMarketDataProvider(
        {"us:voo": TwelveDataInstrument("VOO", "NYSE ARCA"),
         "us:amat": TwelveDataInstrument("AMAT", "NASDAQ")},
        api_key="test-only-placeholder", http_get=get)
    with pytest.raises(RateLimitError):
        adapter.get_quotes([asset(), asset("us:amat", "AMAT", AssetType.STOCK)])
    assert seen == ["VOO", "AMAT"]
