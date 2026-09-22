"""Small, immutable domain records shared by real and virtual accounts."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


class Currency(str, Enum):
    USD = "USD"
    KRW = "KRW"


class AccountType(str, Enum):
    REAL = "REAL"
    SHADOW = "SHADOW"
    PAPER = "PAPER"
    BENCHMARK = "BENCHMARK"


class AssetType(str, Enum):
    STOCK = "STOCK"
    ETF = "ETF"


class TransactionType(str, Enum):
    DEPOSIT = "DEPOSIT"
    WITHDRAW = "WITHDRAW"
    BUY = "BUY"
    SELL = "SELL"
    DIVIDEND = "DIVIDEND"


def _nonempty(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")


def _decimal(value: Decimal, field: str, *, positive: bool = False) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{field} must be a finite Decimal")
    if positive and value <= 0:
        raise ValueError(f"{field} must be positive")


@dataclass(frozen=True, slots=True, kw_only=True)
class Portfolio:
    id: str
    name: str

    def __post_init__(self) -> None:
        _nonempty(self.id, "portfolio id")
        _nonempty(self.name, "portfolio name")


@dataclass(frozen=True, slots=True, kw_only=True)
class Account:
    id: str
    portfolio_id: str
    name: str
    account_type: AccountType
    currency: Currency

    def __post_init__(self) -> None:
        for field in ("id", "portfolio_id", "name"):
            _nonempty(getattr(self, field), f"account {field}")
        if not isinstance(self.account_type, AccountType):
            raise ValueError("unsupported account type")
        if not isinstance(self.currency, Currency):
            raise ValueError("unsupported account currency")


@dataclass(frozen=True, slots=True, kw_only=True)
class Asset:
    id: str
    ticker: str
    name: str
    asset_type: AssetType
    market: str
    exchange: str
    currency: Currency
    sector: str | None = None

    def __post_init__(self) -> None:
        for field in ("id", "ticker", "name", "market", "exchange"):
            _nonempty(getattr(self, field), f"asset {field}")
        if not isinstance(self.asset_type, AssetType):
            raise ValueError("unsupported asset type")
        if not isinstance(self.currency, Currency):
            raise ValueError("unsupported asset currency")
        if self.sector is not None:
            _nonempty(self.sector, "asset sector")


@dataclass(frozen=True, slots=True, kw_only=True)
class Transaction:
    id: str
    account_id: str
    sequence: int
    transaction_type: TransactionType
    currency: Currency
    executed_at: datetime
    asset_id: str | None = None
    quantity: Decimal | None = None
    price: Decimal | None = None
    fee: Decimal = Decimal("0")
    amount: Decimal | None = None

    def __post_init__(self) -> None:
        _nonempty(self.id, "transaction id")
        _nonempty(self.account_id, "transaction account_id")
        if type(self.sequence) is not int or self.sequence < 1:
            raise ValueError("sequence must be a positive integer")
        if not isinstance(self.transaction_type, TransactionType):
            raise ValueError("unsupported transaction type")
        if not isinstance(self.currency, Currency):
            raise ValueError("unsupported transaction currency")
        if not isinstance(self.executed_at, datetime) or self.executed_at.utcoffset() is None:
            raise ValueError("executed_at must be timezone-aware")
        _decimal(self.fee, "fee")
        if self.fee < 0:
            raise ValueError("fee cannot be negative")

        if self.transaction_type in (TransactionType.BUY, TransactionType.SELL):
            _nonempty(self.asset_id, "trade asset_id")
            _decimal(self.quantity, "trade quantity", positive=True)
            _decimal(self.price, "trade price", positive=True)
            if self.amount is not None:
                raise ValueError("trade amount must be omitted")
        else:
            if self.transaction_type is TransactionType.DIVIDEND:
                _nonempty(self.asset_id, "dividend asset_id")
            elif self.asset_id is not None:
                raise ValueError("cash transfer asset_id must be omitted")
            _decimal(self.amount, "cash event amount", positive=True)
            if self.quantity is not None or self.price is not None or self.fee != 0:
                raise ValueError("cash event cannot have quantity, price or fee")
