"""Current account analytics from a real ledger and an offline market-data fake."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext

import pytest

from asset_copilot.application.us_portfolio_analytics import AnalysisError, USPortfolioAnalyzer
from asset_copilot.domain.models import (
    Account, AccountType, Asset, AssetType, Currency, Portfolio, Transaction, TransactionType,
)
from asset_copilot.market.models import FxQuote, MarketQuote
from asset_copilot.storage.sqlite import SQLiteStore


D = Decimal
NOW = datetime(2026, 9, 22, 15, tzinfo=timezone.utc)
TRADED = NOW - timedelta(days=1)
ACCOUNT_ID = "fixture-account"


class FakeMarketDataProvider:
    def __init__(self, quotes: dict[str, MarketQuote], fx: FxQuote) -> None:
        self.quotes = quotes
        self.fx = fx
        self.requested: list[str] | None = None
        self.fx_request: tuple[Currency, Currency] | None = None

    def get_quotes(self, assets: list[Asset]) -> dict[str, MarketQuote]:
        self.requested = [asset.id for asset in assets]
        return self.quotes

    def get_fx_rate(self, base: Currency, quote: Currency) -> FxQuote:
        self.fx_request = (base, quote)
        return self.fx


def security(asset_id: str, ticker: str, kind: AssetType, sector: str | None) -> Asset:
    return Asset(id=asset_id, ticker=ticker, name="Fictional security", asset_type=kind,
                 market="US", exchange="TEST", currency=Currency.USD, sector=sector)


def event(sequence: int, kind: TransactionType, **values: object) -> Transaction:
    return Transaction(id=f"fixture-event-{sequence}", account_id=ACCOUNT_ID, sequence=sequence,
                       transaction_type=kind, currency=Currency.USD, executed_at=TRADED, **values)


def quote(asset_id: str, price: str, minutes_old: int) -> MarketQuote:
    return MarketQuote(asset_id, D(price), Currency.USD, NOW - timedelta(minutes=minutes_old),
                       NOW, "fixture_feed")


def fx_quote(rate: str = "1370") -> FxQuote:
    return FxQuote(Currency.USD, Currency.KRW, D(rate), NOW - timedelta(minutes=1),
                   NOW, "fixture_fx")


def analyze(analyzer: USPortfolioAnalyzer, **changes: object):
    inputs = dict(evaluated_at=NOW, max_quote_age=timedelta(minutes=10),
                  max_fx_age=timedelta(minutes=10))
    inputs.update(changes)
    return analyzer.analyze(ACCOUNT_ID, **inputs)


@pytest.fixture
def scenario(tmp_path):
    with SQLiteStore(tmp_path / "fictional.sqlite") as store:
        store.portfolios.add(Portfolio(id="fixture-portfolio", name="Fictional"))
        store.accounts.add(Account(id=ACCOUNT_ID, portfolio_id="fixture-portfolio", name="Example",
                                   account_type=AccountType.REAL, currency=Currency.USD))
        assets = {
            "asset-aaa": security("asset-aaa", "AAA", AssetType.STOCK, "Technology"),
            "asset-bbb": security("asset-bbb", "BBB", AssetType.STOCK, None),
            # This ETF sector label must not be interpreted as look-through exposure.
            "asset-fund": security("asset-fund", "FUND", AssetType.ETF, "Technology"),
        }
        for asset in assets.values():
            store.assets.add(asset)
        for tx in (
            event(1, TransactionType.DEPOSIT, amount=D("2000")),
            event(2, TransactionType.BUY, asset_id="asset-aaa", quantity=D("2"), price=D("100")),
            event(3, TransactionType.BUY, asset_id="asset-bbb", quantity=D("0.5"), price=D("200")),
            event(4, TransactionType.BUY, asset_id="asset-fund", quantity=D("1"), price=D("500")),
        ):
            store.transactions.append(tx)
        feed = FakeMarketDataProvider({
            "asset-aaa": quote("asset-aaa", "100", 2),
            "asset-bbb": quote("asset-bbb", "200", 3),
            "asset-fund": quote("asset-fund", "500", 4),
        }, fx_quote())
        analyzer = USPortfolioAnalyzer(store.accounts, store.assets, store.transactions, feed)
        yield store, assets, feed, analyzer


def test_current_usd_valuation_and_ledger_orchestration(scenario):
    _, _, feed, analyzer = scenario
    result = analyze(analyzer)
    assert result.account_id == ACCOUNT_ID
    assert result.currency is Currency.USD
    assert result.evaluated_at == NOW
    assert result.max_quote_age == result.max_fx_age == timedelta(minutes=10)
    assert result.all_quotes_fresh and result.fx_fresh
    assert result.cash_balance == D("1200")
    assert result.invested_market_value == D("800")
    assert result.total_value_usd == D("2000")
    assert result.invested_cost_basis == D("800")
    assert result.trading_realized_pnl == result.unrealized_pnl == result.trading_pnl == D("0")
    assert feed.requested == ["asset-aaa", "asset-bbb", "asset-fund"]
    assert feed.fx_request == (Currency.USD, Currency.KRW)


def test_positions_exposures_sector_coverage_and_provenance(scenario):
    _, _, _, analyzer = scenario
    result = analyze(analyzer)
    by_id = {position.asset_id: position for position in result.positions}
    assert set(by_id) == {"asset-aaa", "asset-bbb", "asset-fund"}
    assert by_id["asset-bbb"].quantity == D("0.5")
    assert by_id["asset-bbb"].average_cost == D("200")
    assert by_id["asset-bbb"].cost_basis == D("100")
    assert by_id["asset-bbb"].market_price == D("200")
    assert by_id["asset-bbb"].market_value == D("100")
    assert by_id["asset-bbb"].weight == D("0.05")
    assert by_id["asset-aaa"].ticker == "AAA"
    assert by_id["asset-aaa"].asset_type is AssetType.STOCK
    assert by_id["asset-aaa"].sector == "Technology"
    assert by_id["asset-fund"].sector is None
    assert by_id["asset-aaa"].quote_source == "fixture_feed"
    assert by_id["asset-aaa"].quote_as_of == NOW - timedelta(minutes=2)
    assert by_id["asset-bbb"].quote_as_of == NOW - timedelta(minutes=3)
    assert by_id["asset-fund"].quote_as_of == NOW - timedelta(minutes=4)
    assert all(position.quote_fetched_at == NOW for position in result.positions)
    assert result.cash_ratio == D("0.6")
    assert result.stock_exposure == D("0.15")
    assert result.etf_exposure == D("0.25")
    assert result.cash_ratio + result.stock_exposure + result.etf_exposure == D("1")
    assert result.usd_exposure == D("1")
    assert result.sector_classified_market_value == D("200")
    assert result.unclassified_stock_market_value == D("100")
    assert result.etf_market_value == D("500")
    assert (result.sector_classified_market_value + result.unclassified_stock_market_value
            + result.etf_market_value) == result.invested_market_value
    assert len(result.direct_sector_exposure) == 1
    assert result.direct_sector_exposure[0].sector == "Technology"
    assert result.direct_sector_exposure[0].market_value == D("200")
    assert result.direct_sector_exposure[0].account_weight == D("0.1")


def test_krw_conversion_is_reporting_only(scenario):
    _, _, _, analyzer = scenario
    result = analyze(analyzer)
    assert result.reporting_currency is Currency.KRW
    assert result.usd_krw_rate == D("1370")
    assert result.total_value_krw == D("2740000")
    assert result.invested_cost_basis == D("800")  # still USD
    assert result.fx_source == "fixture_fx"
    assert result.fx_as_of == NOW - timedelta(minutes=1)
    assert result.fx_fetched_at == NOW


def test_realized_unrealized_and_dividend_are_not_conflated(scenario):
    store, _, feed, analyzer = scenario
    store.transactions.append(event(5, TransactionType.SELL, asset_id="asset-aaa",
                                    quantity=D("1"), price=D("150"), fee=D("5")))
    store.transactions.append(event(6, TransactionType.DIVIDEND, asset_id="asset-fund", amount=D("10")))
    feed.quotes["asset-aaa"] = quote("asset-aaa", "160", 2)
    feed.quotes["asset-bbb"] = quote("asset-bbb", "220", 3)
    feed.quotes["asset-fund"] = quote("asset-fund", "550", 4)
    result = analyze(analyzer)
    assert result.cash_balance == D("1355")
    assert result.invested_market_value == D("820")
    assert result.total_value_usd == D("2175")
    assert result.invested_cost_basis == D("700")
    assert result.trading_realized_pnl == D("45")  # 150 - 100 - 5
    assert result.unrealized_pnl == D("120")  # 60 + 10 + 50
    assert result.trading_pnl == D("165")  # excludes the 10 dividend
    assert {position.asset_id: position.unrealized_pnl for position in result.positions} == {
        "asset-aaa": D("60"), "asset-bbb": D("10"), "asset-fund": D("50"),
    }


def test_same_ticker_distinct_asset_ids_keep_independent_prices(scenario):
    store, _, feed, analyzer = scenario
    other = security("asset-aaa-other", "AAA", AssetType.STOCK, "Industrials")
    store.assets.add(other)
    store.transactions.append(event(5, TransactionType.BUY, asset_id=other.id,
                                    quantity=D("1"), price=D("50")))
    feed.quotes[other.id] = quote(other.id, "70", 2)
    result = analyze(analyzer)
    assert {position.asset_id: position.market_value for position in result.positions} == {
        "asset-aaa": D("200"), "asset-aaa-other": D("70"),
        "asset-bbb": D("100"), "asset-fund": D("500"),
    }
    assert result.total_value_usd == D("2020")


def test_multiple_stocks_in_one_direct_sector_are_aggregated(scenario):
    store, _, feed, analyzer = scenario
    other = security("asset-tech-two", "CCC", AssetType.STOCK, "Technology")
    store.assets.add(other)
    store.transactions.append(event(5, TransactionType.BUY, asset_id=other.id,
                                    quantity=D("1"), price=D("50")))
    feed.quotes[other.id] = quote(other.id, "60", 2)
    result = analyze(analyzer)
    assert result.sector_classified_market_value == D("260")
    assert result.direct_sector_exposure[0].market_value == D("260")
    assert result.unclassified_stock_market_value == D("100")
    assert result.etf_market_value == D("500")


@pytest.mark.parametrize("problem,match", [
    ("missing", "missing quote"),
    ("asset_id", "asset_id mismatch"),
    ("currency", "currency mismatch"),
    ("unknown_time", "as_of is unknown"),
    ("stale", "stale quote"),
    ("future", "as_of is in the future"),
])
def test_bad_position_quote_fails_strict_analysis(scenario, problem, match):
    _, _, feed, analyzer = scenario
    current = feed.quotes["asset-aaa"]
    if problem == "missing":
        del feed.quotes["asset-aaa"]
    elif problem == "asset_id":
        feed.quotes["asset-aaa"] = replace(current, asset_id="wrong")
    elif problem == "currency":
        feed.quotes["asset-aaa"] = replace(current, currency=Currency.KRW)
    elif problem == "unknown_time":
        feed.quotes["asset-aaa"] = replace(current, as_of=None)
    elif problem == "stale":
        feed.quotes["asset-aaa"] = replace(current, as_of=NOW - timedelta(minutes=11))
    else:
        feed.quotes["asset-aaa"] = replace(current, as_of=NOW + timedelta(minutes=1),
                                           fetched_at=NOW + timedelta(minutes=1))
    with pytest.raises(AnalysisError, match=match):
        analyze(analyzer)


@pytest.mark.parametrize("problem,match", [
    ("direction", "direction"),
    ("unknown_time", "as_of is unknown"),
    ("stale", "stale FX"),
    ("future", "as_of is in the future"),
])
def test_bad_fx_fails_strict_analysis(scenario, problem, match):
    _, _, feed, analyzer = scenario
    if problem == "direction":
        feed.fx = FxQuote(Currency.KRW, Currency.USD, D("0.001"), NOW, NOW, "fixture_fx")
    elif problem == "unknown_time":
        feed.fx = replace(feed.fx, as_of=None)
    elif problem == "stale":
        feed.fx = replace(feed.fx, as_of=NOW - timedelta(minutes=11))
    else:
        feed.fx = replace(feed.fx, as_of=NOW + timedelta(minutes=1),
                          fetched_at=NOW + timedelta(minutes=1))
    with pytest.raises(AnalysisError, match=match):
        analyze(analyzer)


def test_observation_cannot_precede_its_claimed_market_time(scenario):
    _, _, feed, analyzer = scenario
    feed.quotes["asset-aaa"] = replace(feed.quotes["asset-aaa"],
                                        fetched_at=NOW - timedelta(minutes=3))
    with pytest.raises(AnalysisError, match="future"):
        analyze(analyzer)
    feed.quotes["asset-aaa"] = quote("asset-aaa", "100", 2)
    feed.fx = replace(feed.fx, fetched_at=NOW - timedelta(minutes=2))
    with pytest.raises(AnalysisError, match="future"):
        analyze(analyzer)


def test_unknown_and_non_usd_accounts_are_rejected(scenario):
    store, _, feed, analyzer = scenario
    with pytest.raises(AnalysisError, match="unknown account_id"):
        analyzer.analyze("missing", evaluated_at=NOW,
                         max_quote_age=timedelta(minutes=10), max_fx_age=timedelta(minutes=10))
    store.accounts.add(Account(id="krw-fixture", portfolio_id="fixture-portfolio", name="KRW",
                               account_type=AccountType.PAPER, currency=Currency.KRW))
    with pytest.raises(AnalysisError, match="USD account"):
        analyzer.analyze("krw-fixture", evaluated_at=NOW,
                         max_quote_age=timedelta(minutes=10), max_fx_age=timedelta(minutes=10))
    assert feed.requested is None


def test_evaluated_at_normalization_and_input_validation(scenario):
    store, _, _, analyzer = scenario
    local = datetime(2026, 9, 22, 11, tzinfo=timezone(timedelta(hours=-4)))
    assert analyze(analyzer, evaluated_at=local).evaluated_at == NOW
    with pytest.raises(AnalysisError, match="evaluated_at"):
        analyze(analyzer, evaluated_at=datetime(2026, 9, 22, 15))
    with pytest.raises(AnalysisError, match="max_quote_age"):
        analyze(analyzer, max_quote_age=timedelta(seconds=-1))
    with pytest.raises(AnalysisError, match="max_fx_age"):
        analyze(analyzer, max_fx_age=timedelta(seconds=-1))
    store.transactions.append(replace(event(5, TransactionType.DEPOSIT, amount=D("1")),
                                      executed_at=NOW + timedelta(minutes=1)))
    with pytest.raises(AnalysisError, match="after evaluated_at"):
        analyze(analyzer)


def test_exact_freshness_boundary_is_accepted(scenario):
    _, _, feed, analyzer = scenario
    feed.quotes["asset-aaa"] = replace(feed.quotes["asset-aaa"], as_of=NOW - timedelta(minutes=10))
    feed.fx = replace(feed.fx, as_of=NOW - timedelta(minutes=10))
    assert analyze(analyzer).total_value_usd == D("2000")


def test_all_cash_and_empty_account_require_only_fx(tmp_path):
    with SQLiteStore(tmp_path / "cash-only.sqlite") as store:
        store.portfolios.add(Portfolio(id="fixture", name="Fictional"))
        store.accounts.add(Account(id=ACCOUNT_ID, portfolio_id="fixture", name="Fictional",
                                   account_type=AccountType.REAL, currency=Currency.USD))
        feed = FakeMarketDataProvider({}, fx_quote())
        analyzer = USPortfolioAnalyzer(store.accounts, store.assets, store.transactions, feed)
        empty = analyze(analyzer)
        assert empty.total_value_usd == empty.total_value_krw == D("0")
        assert empty.positions == () and empty.cash_ratio is None
        assert empty.stock_exposure is None and empty.etf_exposure is None
        assert empty.usd_exposure is None and empty.direct_sector_exposure == ()
        assert feed.requested is None
        store.transactions.append(event(1, TransactionType.DEPOSIT, amount=D("500")))
        cash_only = analyze(analyzer)
        assert cash_only.cash_balance == cash_only.total_value_usd == D("500")
        assert cash_only.invested_market_value == D("0")
        assert cash_only.cash_ratio == D("1")
        assert cash_only.stock_exposure == cash_only.etf_exposure == D("0")
        assert cash_only.total_value_krw == D("685000")
        assert feed.requested is None


def test_analysis_result_is_immutable(scenario):
    _, _, _, analyzer = scenario
    result = analyze(analyzer)
    with pytest.raises(FrozenInstanceError):
        result.total_value_usd = D("1")
    with pytest.raises(FrozenInstanceError):
        result.positions[0].market_price = D("1")


def test_financial_totals_ignore_caller_decimal_context(scenario):
    _, _, feed, analyzer = scenario
    feed.fx = fx_quote("1370.1234567890123456789")
    with localcontext() as context:
        context.prec = 4
        result = analyze(analyzer)
    assert result.total_value_usd == D("2000")
    assert result.total_value_krw == D("2740246.9135780246913578000")
