"""Offline P4-05 walk-through: SQLite ledger -> analytics -> allocation decisions.

Run with ``.venv/bin/python examples/p4_allocation_offline.py``. All account,
price, and FX facts are synthetic. This does not approve a policy or place orders.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from asset_copilot.application.policy_config import load_portfolio_policy_config
from asset_copilot.application.us_portfolio_analytics import USPortfolioAnalyzer
from asset_copilot.application.us_portfolio_policy import PortfolioPolicyEngine
from asset_copilot.domain.models import (
    Account, AccountType, Asset, AssetType, Currency, Portfolio, Transaction, TransactionType,
)
from asset_copilot.domain.policy import ETFClassification, ETFGroup, PortfolioPolicyReport
from asset_copilot.market.models import FxQuote, MarketQuote
from asset_copilot.storage.sqlite import SQLiteStore


D = Decimal
NOW = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
POLICY_FILE = Path(__file__).resolve().parents[1] / "config/us_portfolio_policy.toml"


class SyntheticFeed:
    def get_quotes(self, requested):
        prices = {"core": D("50"), "growth": D("15"), "stock": D("25")}
        return {asset.id: MarketQuote(asset.id, prices[asset.id], Currency.USD,
                                      NOW, NOW, "offline fixture") for asset in requested}

    def get_fx_rate(self, base, quote):
        assert (base, quote) == (Currency.USD, Currency.KRW)
        return FxQuote(base, quote, D("1300"), NOW, NOW, "offline fixture")


def synthetic_analysis(database: Path):
    """Build one synthetic account and return its completed analysis."""
    with SQLiteStore(database) as store:
        store.portfolios.add(Portfolio(id="demo", name="Synthetic portfolio"))
        store.accounts.add(Account(id="us-account", portfolio_id="demo", name="Synthetic USD",
                                   account_type=AccountType.REAL, currency=Currency.USD))
        for asset_id, ticker, kind, sector in (
            ("core", "FUND", AssetType.ETF, None),
            ("growth", "FUND", AssetType.ETF, None),
            ("stock", "STK", AssetType.STOCK, "Technology"),
        ):
            store.assets.add(Asset(id=asset_id, ticker=ticker, name=asset_id,
                                   asset_type=kind, market="US", exchange="TEST",
                                   currency=Currency.USD, sector=sector))
        events = (
            (TransactionType.DEPOSIT, None, D("100")),
            (TransactionType.BUY, "core", D("50")),
            (TransactionType.BUY, "growth", D("15")),
            (TransactionType.BUY, "stock", D("25")),
        )
        for sequence, (kind, asset_id, amount) in enumerate(events, 1):
            fields = (dict(amount=amount) if kind is TransactionType.DEPOSIT else
                      dict(asset_id=asset_id, quantity=D("1"), price=amount))
            store.transactions.append(Transaction(
                id=f"demo-{sequence}", account_id="us-account", sequence=sequence,
                transaction_type=kind, currency=Currency.USD,
                executed_at=NOW - timedelta(days=1), **fields))

        analysis = USPortfolioAnalyzer(store.accounts, store.assets, store.transactions,
                                       SyntheticFeed()).analyze(
            "us-account", evaluated_at=NOW, max_quote_age=timedelta(minutes=1),
            max_fx_age=timedelta(minutes=1))
        return analysis


def run_example(database: Path) -> tuple[PortfolioPolicyReport, PortfolioPolicyReport]:
    """Return complete and missing-classification reports over the same analysis."""
    analysis = synthetic_analysis(database)
    engine = PortfolioPolicyEngine(load_portfolio_policy_config(POLICY_FILE))
    complete = engine.evaluate(analysis, etf_classifications=(
        ETFClassification("core", ETFGroup.CORE),
        ETFClassification("growth", ETFGroup.GROWTH),
    ))
    missing = engine.evaluate(analysis, etf_classifications=(
        ETFClassification("core", ETFGroup.CORE),
    ))
    return complete, missing


if __name__ == "__main__":
    with TemporaryDirectory() as directory:
        classified, unclassified = run_example(Path(directory) / "synthetic.sqlite")
    for label, report in (("complete", classified), ("missing classification", unclassified)):
        print(label)
        for item in report.allocation_evaluations:
            print(f"  {item.bucket.value}: {item.status.value} ({item.reason_code.value})")
