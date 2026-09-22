"""Twelve Data HTTP adapter. No provider wire format escapes this module."""

import json
import os
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from http.client import HTTPException
from typing import Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from asset_copilot.domain.models import Asset, Currency

from .errors import (
    AuthenticationError, InstrumentError, NetworkError, RateLimitError,
    RequestTimeoutError, ResponseError,
)
from .models import FxQuote, MarketQuote


@dataclass(frozen=True, slots=True)
class TwelveDataInstrument:
    symbol: str
    exchange: str

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise ValueError("provider symbol is required")
        if not isinstance(self.exchange, str) or not self.exchange.strip():
            raise ValueError("provider exchange is required")


def _http_get(request: Request, timeout: float) -> bytes:
    with urlopen(request, timeout=timeout) as response:
        return response.read(65537)


def _number(value: object, field: str) -> Decimal:
    # Bound both input length and exponent before Decimal arithmetic can consume resources.
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ResponseError(f"invalid {field}")
    raw = str(value).strip()
    if not raw or len(raw) > 64:
        raise ResponseError(f"invalid {field}")
    try:
        result = Decimal(raw)
    except InvalidOperation as exc:
        raise ResponseError(f"invalid {field}") from exc
    if (not result.is_finite() or result <= 0 or len(result.as_tuple().digits) > 40
            or abs(result.as_tuple().exponent) > 100 or result.adjusted() > 30):
        raise ResponseError(f"invalid {field}")
    return result


def _json_decimal(raw: str) -> Decimal:
    if len(raw) > 64:
        raise ResponseError("provider numeric token exceeds limit")
    return Decimal(raw)


def _json_int(raw: str) -> int:
    if len(raw) > 64:
        raise ResponseError("provider numeric token exceeds limit")
    return int(raw)


def _timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ResponseError("invalid provider timestamp")
    raw = str(value)
    if not raw.isascii() or not raw.isdigit() or len(raw) > 12:
        raise ResponseError("invalid provider timestamp")
    try:
        return datetime.fromtimestamp(int(raw), timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise ResponseError("invalid provider timestamp") from exc


class TwelveDataMarketDataProvider:
    """Explicit asset-ID mapping prevents ticker collisions and implicit symbol guesses."""

    def __init__(
        self,
        instruments: Mapping[str, TwelveDataInstrument],
        *,
        api_key: str | None = None,
        http_get: Callable[[Request, float], bytes] = _http_get,
        timeout: float = 5.0,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        raw_key = api_key if api_key is not None else os.environ.get("TWELVE_DATA_API_KEY")
        if not isinstance(raw_key, str) or not raw_key.strip():
            raise AuthenticationError("TWELVE_DATA_API_KEY is required")
        self._api_key = raw_key.strip()
        if not isinstance(timeout, (int, float)) or not 0 < timeout <= 120:
            raise ValueError("timeout must be positive and at most 120 seconds")
        self._instruments = dict(instruments)
        if any(not isinstance(key, str) or not key.strip() or not isinstance(value, TwelveDataInstrument)
               for key, value in self._instruments.items()):
            raise ValueError("invalid provider instrument mapping")
        self._http_get = http_get
        self._timeout = timeout
        self._clock = clock

    def _request(self, endpoint: str, **params: str) -> dict:
        url = "https://api.twelvedata.com/" + endpoint + "?" + urlencode(params)
        request = Request(url, headers={"Accept": "application/json",
                                        "Authorization": "apikey " + self._api_key})
        try:
            body = self._http_get(request, self._timeout)
        except HTTPError as exc:
            if exc.code in (401, 403):
                raise AuthenticationError("market data authentication failed") from None
            if exc.code == 429:
                raise RateLimitError("market data rate limit exceeded") from None
            if exc.code in (400, 404):
                raise InstrumentError("invalid provider instrument or request") from None
            raise ResponseError(f"provider HTTP error {exc.code}") from None
        except (TimeoutError, socket.timeout):
            raise RequestTimeoutError("market data request timed out") from None
        except URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise RequestTimeoutError("market data request timed out") from None
            raise NetworkError("market data network failure") from None
        except (OSError, HTTPException):
            raise NetworkError("market data network failure") from None
        if not isinstance(body, bytes) or len(body) > 65536:
            raise ResponseError("provider response exceeds size limit")
        try:
            payload = json.loads(body, parse_float=_json_decimal, parse_int=_json_int)
        except (TypeError, ValueError, UnicodeError, InvalidOperation, RecursionError):
            raise ResponseError("malformed provider JSON") from None
        if not isinstance(payload, dict):
            raise ResponseError("provider response must be an object")
        if payload.get("status") == "error" or "code" in payload and "message" in payload:
            code = payload.get("code")
            if code in (401, 403):
                raise AuthenticationError("market data authentication failed")
            if code == 429:
                raise RateLimitError("market data rate limit exceeded")
            if code in (400, 404):
                raise InstrumentError("invalid provider symbol or request")
            raise ResponseError("provider rejected market data request")
        return payload

    def get_quotes(self, assets: Sequence[Asset]) -> dict[str, MarketQuote]:
        results: dict[str, MarketQuote] = {}
        for asset in assets:
            if asset.id in results:
                raise ValueError("duplicate asset_id in quote request")
            if asset.currency is not Currency.USD or asset.market.upper() not in ("US", "USA"):
                raise InstrumentError("Twelve Data adapter supports US USD assets only")
            instrument = self._instruments.get(asset.id)
            if instrument is None:
                raise InstrumentError(f"no provider instrument mapping for asset_id {asset.id}")
            payload = self._request("quote", symbol=instrument.symbol,
                                    exchange=instrument.exchange, interval="1min")
            if payload.get("symbol") != instrument.symbol:
                raise ResponseError("provider returned a different symbol")
            if (payload.get("exchange") is not None
                    and (not isinstance(payload["exchange"], str)
                         or payload["exchange"].casefold() != instrument.exchange.casefold())):
                raise ResponseError("provider returned a different exchange")
            if payload.get("currency") != asset.currency.value:
                raise ResponseError("provider quote currency differs from asset currency")
            # Both fields must identify the same minute bar. Its opening time is a
            # conservative reference for close, not a last-trade timestamp.
            bar_start = _timestamp(payload.get("timestamp"))
            last_minute = _timestamp(payload.get("last_quote_at"))
            as_of = bar_start if bar_start is not None and bar_start == last_minute else None
            fetched_at = self._clock()
            try:
                results[asset.id] = MarketQuote(
                    asset.id, _number(payload.get("close"), "price"), asset.currency,
                    as_of, fetched_at, "twelve_data",
                )
            except ValueError as exc:
                raise ResponseError("invalid provider quote metadata") from exc
        return results

    def get_fx_rate(self, base: Currency, quote: Currency) -> FxQuote:
        if not isinstance(base, Currency) or not isinstance(quote, Currency) or base is quote:
            raise ValueError("FX pair requires different supported currencies")
        pair = f"{base.value}/{quote.value}"
        payload = self._request("exchange_rate", symbol=pair)
        if payload.get("symbol") != pair:
            raise ResponseError("provider returned a different FX pair")
        try:
            return FxQuote(base, quote, _number(payload.get("rate"), "FX rate"),
                           _timestamp(payload.get("timestamp")), self._clock(), "twelve_data")
        except ValueError as exc:
            raise ResponseError("invalid provider FX metadata") from exc
