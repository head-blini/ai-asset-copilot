"""Validated market observations. An unknown market time is represented by None."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from asset_copilot.domain.models import Currency


def _utc(value: datetime | None, field: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _required_utc(value: datetime, field: str) -> datetime:
    result = _utc(value, field)
    if result is None:
        raise ValueError(f"{field} must be timezone-aware")
    return result


def _positive_decimal(value: Decimal, field: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise ValueError(f"{field} must be a positive finite Decimal")


@dataclass(frozen=True, slots=True)
class MarketQuote:
    asset_id: str
    price: Decimal
    currency: Currency
    as_of: datetime | None
    fetched_at: datetime
    source: str

    def __post_init__(self) -> None:
        if not isinstance(self.asset_id, str) or not self.asset_id.strip():
            raise ValueError("asset_id is required")
        _positive_decimal(self.price, "price")
        if not isinstance(self.currency, Currency):
            raise ValueError("unsupported quote currency")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source is required")
        object.__setattr__(self, "as_of", _utc(self.as_of, "as_of"))
        object.__setattr__(self, "fetched_at", _required_utc(self.fetched_at, "fetched_at"))


@dataclass(frozen=True, slots=True)
class FxQuote:
    """rate units of quote_currency per one unit of base_currency."""

    base_currency: Currency
    quote_currency: Currency
    rate: Decimal
    as_of: datetime | None
    fetched_at: datetime
    source: str

    def __post_init__(self) -> None:
        if not isinstance(self.base_currency, Currency) or not isinstance(self.quote_currency, Currency):
            raise ValueError("unsupported FX currency")
        if self.base_currency is self.quote_currency:
            raise ValueError("FX pair must have different currencies")
        _positive_decimal(self.rate, "rate")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source is required")
        object.__setattr__(self, "as_of", _utc(self.as_of, "as_of"))
        object.__setattr__(self, "fetched_at", _required_utc(self.fetched_at, "fetched_at"))


def is_stale(quote: MarketQuote | FxQuote, reference_time: datetime, max_age: timedelta) -> bool:
    """Unknown or future market times are unusable; callers supply their own age policy."""
    reference = _required_utc(reference_time, "reference_time")
    if not isinstance(max_age, timedelta) or max_age < timedelta(0):
        raise ValueError("max_age must be a nonnegative timedelta")
    if quote.as_of is None:
        return True
    age = reference - quote.as_of
    return age < timedelta(0) or age > max_age
