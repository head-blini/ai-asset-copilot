"""Strict current-state analytics for a single USD account."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from asset_copilot.domain.models import Asset, AssetType, Currency
from asset_copilot.domain.repositories import AccountRepository, AssetRepository, TransactionRepository
from asset_copilot.market.models import FxQuote, MarketQuote, is_stale
from asset_copilot.market.provider import MarketDataProvider
from asset_copilot.portfolio.calculator import _add, _div, _mul, _sub, replay, value_at_prices


ZERO = Decimal("0")
ONE = Decimal("1")


class AnalysisError(ValueError):
    """Required account, price, or FX evidence is missing or unsuitable."""


@dataclass(frozen=True, slots=True)
class PositionAnalysis:
    asset_id: str
    ticker: str
    asset_type: AssetType
    sector: str | None
    quantity: Decimal
    average_cost: Decimal
    cost_basis: Decimal
    market_price: Decimal
    market_value: Decimal
    weight: Decimal
    unrealized_pnl: Decimal
    quote_source: str
    quote_as_of: datetime
    quote_fetched_at: datetime


@dataclass(frozen=True, slots=True)
class DirectSectorExposure:
    sector: str
    market_value: Decimal
    account_weight: Decimal | None


@dataclass(frozen=True, slots=True)
class PortfolioAnalysis:
    account_id: str
    evaluated_at: datetime
    max_quote_age: timedelta
    max_fx_age: timedelta
    all_quotes_fresh: bool
    fx_fresh: bool
    currency: Currency
    cash_balance: Decimal
    invested_market_value: Decimal
    total_value_usd: Decimal
    invested_cost_basis: Decimal
    trading_realized_pnl: Decimal
    unrealized_pnl: Decimal
    trading_pnl: Decimal
    positions: tuple[PositionAnalysis, ...]
    cash_ratio: Decimal | None
    stock_exposure: Decimal | None
    etf_exposure: Decimal | None
    usd_exposure: Decimal | None
    direct_sector_exposure: tuple[DirectSectorExposure, ...]
    sector_classified_market_value: Decimal
    unclassified_stock_market_value: Decimal
    etf_market_value: Decimal
    reporting_currency: Currency
    usd_krw_rate: Decimal
    total_value_krw: Decimal
    fx_source: str
    fx_as_of: datetime
    fx_fetched_at: datetime


def _evaluated_at(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise AnalysisError("evaluated_at must be timezone-aware")
    return value.astimezone(timezone.utc)


def _max_age(value: timedelta, field: str) -> None:
    if not isinstance(value, timedelta) or value < timedelta(0):
        raise AnalysisError(f"{field} must be a nonnegative timedelta")


def _validate_quote(quote: MarketQuote, asset: Asset, evaluated_at: datetime,
                    max_age: timedelta) -> None:
    if not isinstance(quote, MarketQuote):
        raise AnalysisError(f"invalid quote for asset_id {asset.id}")
    if quote.asset_id != asset.id:
        raise AnalysisError(f"quote asset_id mismatch for {asset.id}")
    if quote.currency is not asset.currency:
        raise AnalysisError(f"quote currency mismatch for {asset.id}")
    if not isinstance(quote.price, Decimal) or not quote.price.is_finite() or quote.price <= 0:
        raise AnalysisError(f"invalid quote price for {asset.id}")
    if not isinstance(quote.source, str) or not quote.source.strip():
        raise AnalysisError(f"missing quote source for {asset.id}")
    if quote.as_of is None:
        raise AnalysisError(f"quote as_of is unknown for {asset.id}")
    if quote.as_of > evaluated_at or quote.as_of > quote.fetched_at:
        raise AnalysisError(f"quote as_of is in the future for {asset.id}")
    if is_stale(quote, evaluated_at, max_age):
        raise AnalysisError(f"stale quote for {asset.id}")


def _validate_fx(fx: FxQuote, evaluated_at: datetime, max_age: timedelta) -> None:
    if not isinstance(fx, FxQuote):
        raise AnalysisError("invalid FX quote")
    if fx.base_currency is not Currency.USD or fx.quote_currency is not Currency.KRW:
        raise AnalysisError("FX direction must be USD/KRW")
    if not isinstance(fx.rate, Decimal) or not fx.rate.is_finite() or fx.rate <= 0:
        raise AnalysisError("invalid FX rate")
    if not isinstance(fx.source, str) or not fx.source.strip():
        raise AnalysisError("missing FX source")
    if fx.as_of is None:
        raise AnalysisError("FX as_of is unknown")
    if fx.as_of > evaluated_at or fx.as_of > fx.fetched_at:
        raise AnalysisError("FX as_of is in the future")
    if is_stale(fx, evaluated_at, max_age):
        raise AnalysisError("stale FX quote")


class USPortfolioAnalyzer:
    """Read an account ledger; never mutate account state or fetch data from the calculator."""

    def __init__(self, accounts: AccountRepository, assets: AssetRepository,
                 transactions: TransactionRepository, market_data: MarketDataProvider) -> None:
        self._accounts = accounts
        self._assets = assets
        self._transactions = transactions
        self._market_data = market_data

    def analyze(self, account_id: str, *, evaluated_at: datetime,
                max_quote_age: timedelta, max_fx_age: timedelta) -> PortfolioAnalysis:
        evaluation_time = _evaluated_at(evaluated_at)
        _max_age(max_quote_age, "max_quote_age")
        _max_age(max_fx_age, "max_fx_age")
        account = self._accounts.get(account_id)
        if account is None:
            raise AnalysisError(f"unknown account_id: {account_id}")
        if account.id != account_id or account.currency is not Currency.USD:
            raise AnalysisError("US analysis requires the requested USD account")

        ledger = self._transactions.list_for_account(account_id)
        if any(event.executed_at.astimezone(timezone.utc) > evaluation_time for event in ledger):
            raise AnalysisError("ledger contains a transaction after evaluated_at")
        asset_ids = {event.asset_id for event in ledger if event.asset_id is not None}
        assets: dict[str, Asset] = {}
        for asset_id in asset_ids:
            asset = self._assets.get(asset_id)
            if asset is None or asset.id != asset_id:
                raise AnalysisError(f"unknown ledger asset_id: {asset_id}")
            assets[asset_id] = asset
        snapshot = replay(account, ledger, assets)

        open_assets = [assets[position.asset_id] for position in snapshot.positions]
        quotes = self._market_data.get_quotes(open_assets) if open_assets else {}
        if not isinstance(quotes, Mapping):
            raise AnalysisError("market data provider returned invalid quotes")
        prices: dict[str, Decimal] = {}
        for asset in open_assets:
            quote = quotes.get(asset.id)
            if quote is None:
                raise AnalysisError(f"missing quote for asset_id {asset.id}")
            _validate_quote(quote, asset, evaluation_time, max_quote_age)
            prices[asset.id] = quote.price
        valuation = value_at_prices(snapshot, prices)

        fx = self._market_data.get_fx_rate(Currency.USD, Currency.KRW)
        _validate_fx(fx, evaluation_time, max_fx_age)

        positions: list[PositionAnalysis] = []
        stock_value = ZERO
        etf_value = ZERO
        classified_value = ZERO
        unclassified_stock_value = ZERO
        sector_values: dict[str, Decimal] = {}
        for valued in valuation.positions:
            asset = assets[valued.position.asset_id]
            quote = quotes[asset.id]
            positions.append(PositionAnalysis(
                asset_id=asset.id, ticker=valued.position.ticker,
                asset_type=asset.asset_type, sector=asset.sector if asset.asset_type is AssetType.STOCK else None,
                quantity=valued.position.quantity, average_cost=valued.position.average_cost,
                cost_basis=valued.position.cost_basis, market_price=valued.market_price,
                market_value=valued.market_value, weight=valued.weight,
                unrealized_pnl=valued.unrealized_pnl, quote_source=quote.source,
                quote_as_of=quote.as_of, quote_fetched_at=quote.fetched_at,
            ))
            if asset.asset_type is AssetType.STOCK:
                stock_value = _add(stock_value, valued.market_value)
                if asset.sector is None:
                    unclassified_stock_value = _add(unclassified_stock_value, valued.market_value)
                else:
                    classified_value = _add(classified_value, valued.market_value)
                    sector_values[asset.sector] = _add(sector_values.get(asset.sector, ZERO), valued.market_value)
            else:
                etf_value = _add(etf_value, valued.market_value)

        total = valuation.total_account_value
        sectors = tuple(DirectSectorExposure(name, market_value,
                                             _div(market_value, total) if total else None)
                        for name, market_value in sorted(sector_values.items()))
        return PortfolioAnalysis(
            account_id=account.id, evaluated_at=evaluation_time,
            max_quote_age=max_quote_age, max_fx_age=max_fx_age,
            all_quotes_fresh=True, fx_fresh=True, currency=Currency.USD,
            cash_balance=snapshot.cash_balance,
            invested_market_value=_sub(total, snapshot.cash_balance),
            total_value_usd=total, invested_cost_basis=snapshot.total_invested_cost,
            trading_realized_pnl=snapshot.realized_pnl, unrealized_pnl=valuation.unrealized_pnl,
            trading_pnl=_add(snapshot.realized_pnl, valuation.unrealized_pnl),
            positions=tuple(positions), cash_ratio=valuation.cash_ratio,
            stock_exposure=_div(stock_value, total) if total else None,
            etf_exposure=_div(etf_value, total) if total else None,
            usd_exposure=ONE if total else None,
            direct_sector_exposure=sectors,
            sector_classified_market_value=classified_value,
            unclassified_stock_market_value=unclassified_stock_value,
            etf_market_value=etf_value, reporting_currency=Currency.KRW,
            usd_krw_rate=fx.rate, total_value_krw=_mul(total, fx.rate),
            fx_source=fx.source, fx_as_of=fx.as_of, fx_fetched_at=fx.fetched_at,
        )
