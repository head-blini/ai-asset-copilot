"""Portfolio policy decisions from immutable current-state analysis facts."""

from dataclasses import FrozenInstanceError, replace
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal, Inexact, ROUND_DOWN, localcontext
from pathlib import Path

import pytest

from asset_copilot.application.policy_config import load_portfolio_policy_config
from asset_copilot.application.us_portfolio_analytics import (
    AnalysisError, DirectSectorExposure, PortfolioAnalysis, PositionAnalysis,
    USPortfolioAnalyzer,
)
from asset_copilot.application.us_portfolio_policy import PortfolioPolicyEngine
from asset_copilot.domain.models import (
    Account, AccountType, Asset, AssetType, Currency, Portfolio, Transaction, TransactionType,
)
from asset_copilot.domain.policy import (
    CashRangeThresholds, PolicyKind, PolicyReason, PolicyStatus, PolicyTargetKind,
    PortfolioPolicyConfig,
)
from asset_copilot.market.models import FxQuote, MarketQuote
from asset_copilot.portfolio.calculator import _add, _div
from asset_copilot.storage.sqlite import SQLiteStore


D = Decimal
NOW = datetime(2026, 9, 22, 15, tzinfo=timezone.utc)
CONFIG_FILE = Path(__file__).resolve().parents[1] / "config/us_portfolio_policy.toml"


def config(**changes):
    values = dict(policy_version="test-v1", individual_stock_warn_ratio=D("0.30"),
                  individual_stock_breach_ratio=D("0.40"), direct_sector_warn_ratio=D("0.30"),
                  direct_sector_breach_ratio=D("0.40"), min_cash_ratio=D("0.05"),
                  max_cash_ratio=D("0.30"), individual_stocks_total_max_ratio=D("0.80"))
    values.update(changes)
    return PortfolioPolicyConfig(**values)


def position(asset_id, value, total, *, kind=AssetType.STOCK, sector="Technology", weight=None):
    value, total = D(value), D(total)
    return PositionAnalysis(asset_id, asset_id.upper(), kind, sector if kind is AssetType.STOCK else None,
                            D("1"), value, value, value, value,
                            _div(value, total) if weight is None and total else weight,
                            D("0"), "fixture", NOW, NOW)


def analysis(*, total="100", cash="20", positions=(), sectors=(), unclassified="0"):
    total, cash, unclassified = D(total), D(cash), D(unclassified)
    stock_value = D("0")
    for item in positions:
        if item.asset_type is AssetType.STOCK:
            stock_value = _add(stock_value, item.market_value)
    return PortfolioAnalysis(
        account_id="account", evaluated_at=NOW, max_quote_age=timedelta(minutes=10),
        max_fx_age=timedelta(minutes=10), all_quotes_fresh=True, fx_fresh=True,
        currency=Currency.USD, cash_balance=cash,
        invested_market_value=total - cash, total_value_usd=total,
        invested_cost_basis=D("0"), trading_realized_pnl=D("0"),
        unrealized_pnl=D("0"), trading_pnl=D("0"), positions=tuple(positions),
        cash_ratio=_div(cash, total) if total else None,
        stock_exposure=_div(stock_value, total) if total else None, etf_exposure=None, usd_exposure=D("1") if total else None,
        direct_sector_exposure=tuple(sectors), sector_classified_market_value=D("0"),
        unclassified_stock_market_value=unclassified, etf_market_value=D("0"),
        reporting_currency=Currency.KRW, usd_krw_rate=D("1300"),
        total_value_krw=total * D("1300"), fx_source="fixture", fx_as_of=NOW,
        fx_fetched_at=NOW,
    )


def decision(report, policy, target_kind=None, identifier=None):
    matches = [item for item in report.evaluations if item.policy is policy
               and (target_kind is None or item.target.kind is target_kind)
               and (identifier is None or item.target.identifier == identifier)]
    assert len(matches) == 1
    return matches[0]


@pytest.mark.parametrize("change", [
    {"individual_stock_warn_ratio": D("-0.01")},
    {"individual_stock_breach_ratio": D("1.01")},
    {"direct_sector_warn_ratio": D("NaN")},
    {"direct_sector_breach_ratio": D("Infinity")},
    {"min_cash_ratio": D("-0.01")},
    {"max_cash_ratio": D("1.01")},
    {"individual_stock_warn_ratio": D("0.41")},
    {"direct_sector_warn_ratio": D("0.41")},
    {"min_cash_ratio": D("0.31")},
    {"individual_stock_warn_ratio": 0.2},
    {"individual_stocks_total_max_ratio": D("-0.01")},
    {"individual_stocks_total_max_ratio": D("1.01")},
    {"individual_stocks_total_max_ratio": D("NaN")},
    {"individual_stocks_total_max_ratio": D("0.39")},
    {"individual_stocks_total_max_ratio": 0.8},
    {"policy_version": ""},
])
def test_invalid_config_is_rejected(change):
    with pytest.raises(ValueError):
        config(**change)


def test_config_is_immutable_and_existing_toml_is_loaded():
    configured = load_portfolio_policy_config(CONFIG_FILE)
    assert configured == config(
        policy_version="initial-v1", individual_stock_warn_ratio=D("0.12"),
        individual_stock_breach_ratio=D("0.15"), direct_sector_warn_ratio=None,
        direct_sector_breach_ratio=D("0.35"), max_cash_ratio=D("0.20"),
        individual_stocks_total_max_ratio=D("0.30"),
    )
    with pytest.raises(FrozenInstanceError):
        configured.min_cash_ratio = D("0")


@pytest.mark.parametrize("original,replacement", [
    ("cash = 10", "cash = 11"),
    ("cash = 10", "cash = -1"),
    ("max = 20", "max = 4"),
    ("individual_position_max = 15", "individual_position_max = 31"),
    ("concentration_warning = 12", "concentration_warning = 16"),
])
def test_loader_rejects_inconsistent_or_invalid_human_policy(tmp_path, original, replacement):
    path = tmp_path / "policy.toml"
    path.write_text(CONFIG_FILE.read_text().replace(original, replacement, 1))
    with pytest.raises(ValueError):
        load_portfolio_policy_config(path)


def test_loader_reads_optional_sector_warning_without_changing_declared_limit(tmp_path):
    path = tmp_path / "policy.toml"
    path.write_text(CONFIG_FILE.read_text().replace("sector_max = 35", "sector_warning = 30\nsector_max = 35"))
    configured = load_portfolio_policy_config(path)
    assert configured.direct_sector_warn_ratio == D("0.30")
    assert configured.direct_sector_breach_ratio == D("0.35")


@pytest.mark.parametrize("table,key", [
    ("", "policy_verison"),
    ("target_percent", "core_etff"),
    ("range_percent.core_etf", "maxx"),
    ("range_percent.growth_etf", "minn"),
    ("range_percent.individual_stocks", "maximum"),
    ("range_percent.cash", "cash_max"),
    ("risk_percent", "sector_warnning"),
    ("risk_percent", "enforcement_enabled"),
])
def test_loader_rejects_unknown_keys_at_every_level(tmp_path, table, key):
    source = CONFIG_FILE.read_text()
    addition = f'{key} = 10\n'
    if table:
        source = source.replace(f"[{table}]\n", f"[{table}]\n{addition}")
    else:
        source = addition + source
    path = tmp_path / "policy.toml"
    path.write_text(source)
    with pytest.raises(ValueError, match="unknown keys"):
        load_portfolio_policy_config(path)


@pytest.mark.parametrize("addition", [
    "\n[range_percent.core_etff]\nmin = 40\nmax = 60\n",
    "\n[unrecognized_policy]\nlimit = 10\n",
])
def test_loader_rejects_unknown_tables(tmp_path, addition):
    path = tmp_path / "policy.toml"
    path.write_text(CONFIG_FILE.read_text() + addition)
    with pytest.raises(ValueError, match="unknown keys"):
        load_portfolio_policy_config(path)


@pytest.mark.parametrize("original,replacement", [
    ('policy_version = "initial-v1"', ''),
    ('individual_stocks_total_max = 30', ''),
    ('individual_position_max = 15', 'individual_position_max = true'),
    ('individual_position_max = 15', 'individual_position_max = "15"'),
    ('sector_max = 35', 'sector_max = nan'),
    ('sector_max = 35', 'sector_max = inf'),
    ('sector_max = 35', 'sector_max = 35\nsector_max = 36'),
    ('policy_version = "initial-v1"', 'policy_version = 1'),
    ('[target_percent]', 'target_percent = 1\n[wrong_target_table]'),
])
def test_loader_rejects_missing_or_malformed_configuration(tmp_path, original, replacement):
    path = tmp_path / "policy.toml"
    path.write_text(CONFIG_FILE.read_text().replace(original, replacement))
    with pytest.raises(ValueError):
        load_portfolio_policy_config(path)


def test_loader_decimal_percentages_do_not_depend_on_context(tmp_path):
    path = tmp_path / "policy.toml"
    path.write_text(CONFIG_FILE.read_text().replace("concentration_warning = 12",
                                                   "concentration_warning = 12.123456789"))
    with localcontext() as context:
        context.prec = 4
        context.traps[Inexact] = True
        configured = load_portfolio_policy_config(path)
    assert configured.individual_stock_warn_ratio == D("0.12123456789")


def test_unknown_injected_config_field_is_rejected():
    with pytest.raises(TypeError):
        config(individual_stocks_totl_max_ratio=D("0.30"))


@pytest.mark.parametrize("stock_value,status", [
    ("29.999999999999999999999999999999", PolicyStatus.PASS),
    ("30", PolicyStatus.BREACH),
    ("30.000000000000000000000000000001", PolicyStatus.BREACH),
])
def test_total_stock_limit_exact_boundaries(stock_value, status):
    data = analysis(total="100", cash="20", positions=(position("stock", stock_value, "100"),))
    result = PortfolioPolicyEngine(load_portfolio_policy_config(CONFIG_FILE)).evaluate(data)
    item = decision(result, PolicyKind.TOTAL_STOCK_EXPOSURE)
    assert item.status is status
    assert item.actual_ratio == _div(D(stock_value), D("100"))
    assert item.thresholds.warn_ratio is None
    assert item.thresholds.breach_ratio == D("0.30")
    assert item.target.kind is PolicyTargetKind.PORTFOLIO
    assert item.target.identifier == "account"


def test_total_stock_limit_includes_unclassified_stocks_and_excludes_etfs():
    data = analysis(cash="20", unclassified="13", positions=(
        position("known", "17", "100"),
        position("unknown", "13", "100", sector=None),
        position("fund", "50", "100", kind=AssetType.ETF),
    ))
    result = PortfolioPolicyEngine(load_portfolio_policy_config(CONFIG_FILE)).evaluate(data)
    total = decision(result, PolicyKind.TOTAL_STOCK_EXPOSURE)
    assert total.actual_ratio == D("0.30")
    assert total.status is PolicyStatus.BREACH
    assert decision(result, PolicyKind.DIRECT_SECTOR, PolicyTargetKind.UNCLASSIFIED_STOCK).status is PolicyStatus.UNKNOWN
    assert not any(item.target.identifier == "fund" for item in result.evaluations)


def test_etf_at_core_target_does_not_breach_an_individual_stock_cap():
    data = analysis(cash="25", positions=(
        position("stock", "25", "100"),
        position("fund", "50", "100", kind=AssetType.ETF),
    ))
    report = PortfolioPolicyEngine(load_portfolio_policy_config(CONFIG_FILE)).evaluate(data)
    stocks = [item for item in report.evaluations if item.policy is PolicyKind.INDIVIDUAL_STOCK]
    assert len(stocks) == 1
    assert stocks[0].target.identifier == "stock"
    assert stocks[0].status is PolicyStatus.BREACH
    assert decision(report, PolicyKind.TOTAL_STOCK_EXPOSURE).actual_ratio == D("0.25")


def test_total_stock_decision_uses_amounts_not_a_rounded_exposure():
    data = analysis(total="100", cash="20", positions=(position("stock", "29.999", "100"),))
    data = replace(data, stock_exposure=D("0.30"))
    report = PortfolioPolicyEngine(load_portfolio_policy_config(CONFIG_FILE)).evaluate(data)
    item = decision(report, PolicyKind.TOTAL_STOCK_EXPOSURE)
    assert item.status is PolicyStatus.PASS
    assert item.actual_ratio == D("0.29999")


def test_total_stock_sum_and_boundary_ignore_caller_decimal_context():
    data = analysis(total="100", cash="20", positions=(
        position("a", "19.999999999999999999999999999999", "100"),
        position("b", "10", "100"),
    ))
    engine = PortfolioPolicyEngine(load_portfolio_policy_config(CONFIG_FILE))
    ordinary = engine.evaluate(data)
    with localcontext() as context:
        context.prec = 4
        context.rounding = ROUND_DOWN
        context.traps[Inexact] = True
        result = engine.evaluate(data)
    assert result == ordinary
    assert decision(result, PolicyKind.TOTAL_STOCK_EXPOSURE).status is PolicyStatus.PASS


@pytest.mark.parametrize("exposure", [None, D("NaN"), D("-0.1"), D("1.1")])
def test_missing_or_invalid_total_stock_ratio_is_unknown(exposure):
    data = analysis(positions=(position("a", "10", "100"),))
    result = PortfolioPolicyEngine(config()).evaluate(replace(data, stock_exposure=exposure))
    item = decision(result, PolicyKind.TOTAL_STOCK_EXPOSURE)
    assert item.status is PolicyStatus.UNKNOWN
    assert item.reason_code is PolicyReason.INVALID_EXPOSURE


@pytest.mark.parametrize("amount", [D("NaN"), D("-1"), D("101")])
def test_invalid_stock_amount_cannot_produce_a_total_stock_pass(amount):
    data = analysis(positions=(position("a", "10", "100"),))
    data = replace(data, positions=(replace(data.positions[0], market_value=amount),))
    report = PortfolioPolicyEngine(config()).evaluate(data)
    assert decision(report, PolicyKind.INDIVIDUAL_STOCK).status is PolicyStatus.UNKNOWN
    assert decision(report, PolicyKind.TOTAL_STOCK_EXPOSURE).status is PolicyStatus.UNKNOWN


def test_unknown_asset_type_is_not_silently_excluded_from_total_stocks():
    data = analysis(positions=(position("a", "10", "100"),))
    data = replace(data, positions=(replace(data.positions[0], asset_type="UNKNOWN"),))
    report = PortfolioPolicyEngine(config()).evaluate(data)
    assert decision(report, PolicyKind.TOTAL_STOCK_EXPOSURE).status is PolicyStatus.UNKNOWN
    assert all(item.status is PolicyStatus.UNKNOWN for item in report.evaluations)


@pytest.mark.parametrize("value,status,code", [
    ("29.999", PolicyStatus.PASS, PolicyReason.BELOW_WARNING),
    ("30", PolicyStatus.WARN, PolicyReason.WARNING_LIMIT),
    ("35", PolicyStatus.WARN, PolicyReason.WARNING_LIMIT),
    ("40", PolicyStatus.BREACH, PolicyReason.BREACH_LIMIT),
    ("41", PolicyStatus.BREACH, PolicyReason.BREACH_LIMIT),
])
def test_individual_stock_thresholds_and_equality(value, status, code):
    item = position("asset-a", value, "100")
    result = PortfolioPolicyEngine(config()).evaluate(analysis(cash="20", positions=(item,)))
    actual = decision(result, PolicyKind.INDIVIDUAL_STOCK)
    assert (actual.status, actual.reason_code, actual.actual_ratio) == (status, code, D(value) / 100)
    assert actual.target.kind is PolicyTargetKind.ASSET
    assert actual.target.identifier == "asset-a"
    assert actual.thresholds.warn_ratio == D("0.30")
    assert actual.thresholds.breach_ratio == D("0.40")


def test_direct_stocks_are_evaluated_independently_and_etfs_are_excluded():
    items = (position("z", "40", "100"), position("a", "31", "100"),
             position("m", "10", "100", kind=AssetType.ETF))
    result = PortfolioPolicyEngine(config()).evaluate(analysis(cash="19", positions=items))
    assets = [item for item in result.evaluations if item.policy is PolicyKind.INDIVIDUAL_STOCK]
    assert [(item.target.identifier, item.status) for item in assets] == [
        ("a", PolicyStatus.WARN), ("z", PolicyStatus.BREACH),
    ]
    assert all(item.target.identifier != "m" for item in assets)
    assert decision(result, PolicyKind.TOTAL_STOCK_EXPOSURE).actual_ratio == D("0.71")


def test_cash_is_in_denominator_and_display_rounding_does_not_decide():
    # The displayed 40% is rounded upward; exact 3.999 / 10 is below breach.
    item = position("a", "3.999", "10", weight=D("0.40"))
    result = PortfolioPolicyEngine(config()).evaluate(analysis(total="10", cash="6.001", positions=(item,)))
    assert decision(result, PolicyKind.INDIVIDUAL_STOCK).status is PolicyStatus.WARN
    assert decision(result, PolicyKind.INDIVIDUAL_STOCK).actual_ratio == D("0.3999")
    assert decision(result, PolicyKind.CASH_RATIO).status is PolicyStatus.BREACH


def test_repeating_ratio_comparison_is_context_independent():
    threshold = D("0.3333333333333333333333333333333333333333")
    configured = config(individual_stock_warn_ratio=threshold,
                        individual_stock_breach_ratio=threshold)
    data = analysis(total="3", cash="2", positions=(position("a", "1", "3"),))
    ordinary = PortfolioPolicyEngine(configured).evaluate(data)
    with localcontext() as context:
        context.prec = 4
        context.rounding = ROUND_DOWN
        context.traps[Inexact] = True
        constrained = PortfolioPolicyEngine(configured).evaluate(data)
    assert ordinary == constrained
    assert decision(ordinary, PolicyKind.INDIVIDUAL_STOCK).status is PolicyStatus.BREACH


@pytest.mark.parametrize("value,status", [
    ("29", PolicyStatus.PASS), ("30", PolicyStatus.WARN),
    ("40", PolicyStatus.BREACH),
])
def test_direct_sector_thresholds(value, status):
    sector = DirectSectorExposure("Technology", D(value), D(value) / 100)
    result = PortfolioPolicyEngine(config()).evaluate(analysis(sectors=(sector,)))
    item = decision(result, PolicyKind.DIRECT_SECTOR, PolicyTargetKind.DIRECT_SECTOR)
    assert item.status is status
    assert item.target.identifier == "Technology"


def test_declared_sector_limit_has_no_invented_warning_band():
    engine = PortfolioPolicyEngine(load_portfolio_policy_config(CONFIG_FILE))
    below = analysis(sectors=(DirectSectorExposure("Technology", D("34.99"), D("0.3499")),))
    at_limit = analysis(sectors=(DirectSectorExposure("Technology", D("35"), D("0.35")),))
    assert decision(engine.evaluate(below), PolicyKind.DIRECT_SECTOR).status is PolicyStatus.PASS
    assert decision(engine.evaluate(below), PolicyKind.DIRECT_SECTOR).reason_code is PolicyReason.BELOW_LIMIT
    assert decision(engine.evaluate(at_limit), PolicyKind.DIRECT_SECTOR).status is PolicyStatus.BREACH


def test_unclassified_stock_sector_is_explicit_unknown_not_breach():
    result = PortfolioPolicyEngine(config()).evaluate(analysis(unclassified="50"))
    item = decision(result, PolicyKind.DIRECT_SECTOR, PolicyTargetKind.UNCLASSIFIED_STOCK)
    assert item.status is PolicyStatus.UNKNOWN
    assert item.reason_code is PolicyReason.UNCLASSIFIED_STOCK
    assert item.actual_ratio == D("0.5")
    assert PolicyKind.DIRECT_SECTOR not in result.not_applicable


def test_invalid_unclassified_exposure_cannot_disappear():
    result = PortfolioPolicyEngine(config()).evaluate(analysis(unclassified="-1"))
    item = decision(result, PolicyKind.DIRECT_SECTOR, PolicyTargetKind.UNCLASSIFIED_STOCK)
    assert item.status is PolicyStatus.UNKNOWN
    assert item.reason_code is PolicyReason.INVALID_EXPOSURE


@pytest.mark.parametrize("cash,status,reason", [
    ("4", PolicyStatus.BREACH, PolicyReason.BELOW_MINIMUM),
    ("5", PolicyStatus.PASS, PolicyReason.WITHIN_RANGE),
    ("20", PolicyStatus.PASS, PolicyReason.WITHIN_RANGE),
    ("30", PolicyStatus.PASS, PolicyReason.WITHIN_RANGE),
    ("31", PolicyStatus.BREACH, PolicyReason.ABOVE_MAXIMUM),
])
def test_cash_range_inclusive_boundaries(cash, status, reason):
    result = PortfolioPolicyEngine(config()).evaluate(analysis(cash=cash))
    item = decision(result, PolicyKind.CASH_RATIO)
    assert (item.status, item.reason_code, item.actual_ratio) == (status, reason, D(cash) / 100)
    assert item.thresholds == CashRangeThresholds(D("0.05"), D("0.30"))


def test_zero_value_and_no_applicable_positions_are_explicit():
    result = PortfolioPolicyEngine(config()).evaluate(analysis(total="0", cash="0"))
    assert result.not_applicable == (PolicyKind.INDIVIDUAL_STOCK, PolicyKind.DIRECT_SECTOR)
    item = decision(result, PolicyKind.CASH_RATIO)
    assert item.status is PolicyStatus.UNKNOWN
    assert item.reason_code is PolicyReason.ZERO_TOTAL_VALUE
    assert item.actual_ratio is None
    stock_total = decision(result, PolicyKind.TOTAL_STOCK_EXPOSURE)
    assert stock_total.status is PolicyStatus.UNKNOWN
    assert stock_total.reason_code is PolicyReason.ZERO_TOTAL_VALUE
    assert stock_total.actual_ratio is None


def test_cash_only_and_etf_only_have_no_direct_sector_evaluation():
    engine = PortfolioPolicyEngine(config())
    cash_only = engine.evaluate(analysis(total="100", cash="100"))
    assert cash_only.not_applicable == (PolicyKind.INDIVIDUAL_STOCK, PolicyKind.DIRECT_SECTOR)
    assert decision(cash_only, PolicyKind.CASH_RATIO).status is PolicyStatus.BREACH
    assert decision(cash_only, PolicyKind.TOTAL_STOCK_EXPOSURE).status is PolicyStatus.PASS
    assert decision(cash_only, PolicyKind.TOTAL_STOCK_EXPOSURE).actual_ratio == D("0")
    etf_only = engine.evaluate(analysis(total="100", cash="20",
                                        positions=(position("fund", "80", "100", kind=AssetType.ETF),)))
    assert etf_only.not_applicable == (PolicyKind.INDIVIDUAL_STOCK, PolicyKind.DIRECT_SECTOR)
    assert not any(item.policy is PolicyKind.INDIVIDUAL_STOCK for item in etf_only.evaluations)
    assert decision(etf_only, PolicyKind.TOTAL_STOCK_EXPOSURE).status is PolicyStatus.PASS
    assert decision(etf_only, PolicyKind.TOTAL_STOCK_EXPOSURE).actual_ratio == D("0")


@pytest.mark.parametrize("flag", ["all_quotes_fresh", "fx_fresh"])
def test_unreliable_analysis_never_falls_back_to_pass(flag):
    data = analysis(total="100", cash="20", positions=(position("a", "10", "100"),),
                    sectors=(DirectSectorExposure("Technology", D("10"), D("0.1")),))
    result = PortfolioPolicyEngine(config()).evaluate(replace(data, **{flag: False}))
    assert {item.status for item in result.evaluations} == {PolicyStatus.UNKNOWN}
    assert {item.reason_code for item in result.evaluations} == {PolicyReason.UNRELIABLE_ANALYSIS}


def test_missing_exposure_is_unknown_and_input_and_report_are_immutable():
    data = analysis(total="100", cash="20", positions=(replace(position("a", "10", "100"), weight=None),))
    before = deepcopy(data)
    report = PortfolioPolicyEngine(config()).evaluate(data)
    assert data == before
    assert decision(report, PolicyKind.INDIVIDUAL_STOCK).status is PolicyStatus.UNKNOWN
    with pytest.raises(FrozenInstanceError):
        report.policy_version = "rewritten"
    with pytest.raises(FrozenInstanceError):
        report.evaluations[0].status = PolicyStatus.PASS


def test_same_analysis_and_config_produce_identical_report_without_clock():
    data = analysis(total="100", cash="20", positions=(position("a", "40", "100"),),
                    sectors=(DirectSectorExposure("Technology", D("40"), D("0.4")),))
    engine = PortfolioPolicyEngine(config())
    first = engine.evaluate(data)
    assert engine.evaluate(data) == first
    assert first.evaluated_at == NOW
    assert first.account_id == "account"
    assert first.policy_version == "test-v1"
    assert [item.status for item in first.evaluations] == [
        PolicyStatus.BREACH, PolicyStatus.PASS, PolicyStatus.BREACH, PolicyStatus.PASS,
    ]


def test_real_analyzer_output_preserves_direct_stock_scope_and_needs_no_io_during_policy(tmp_path):
    with SQLiteStore(tmp_path / "policy.sqlite") as store:
        store.portfolios.add(Portfolio(id="portfolio", name="Portfolio"))
        store.accounts.add(Account(id="account", portfolio_id="portfolio", name="Account",
                                   account_type=AccountType.REAL, currency=Currency.USD))
        assets = (
            Asset(id="stock", ticker="STK", name="Stock", asset_type=AssetType.STOCK,
                  market="US", exchange="TEST", currency=Currency.USD, sector="Technology"),
            Asset(id="unclassified", ticker="UNC", name="Unclassified", asset_type=AssetType.STOCK,
                  market="US", exchange="TEST", currency=Currency.USD),
            Asset(id="etf", ticker="ETF", name="Fund", asset_type=AssetType.ETF,
                  market="US", exchange="TEST", currency=Currency.USD, sector="Technology"),
        )
        for asset in assets:
            store.assets.add(asset)
        for sequence, event in enumerate((
            (TransactionType.DEPOSIT, None, D("100")),
            (TransactionType.BUY, "stock", D("20")),
            (TransactionType.BUY, "unclassified", D("10")),
            (TransactionType.BUY, "etf", D("50")),
        ), 1):
            kind, asset_id, amount = event
            kwargs = (dict(amount=amount) if kind is TransactionType.DEPOSIT
                      else dict(asset_id=asset_id, quantity=D("1"), price=amount))
            store.transactions.append(Transaction(
                id=f"event-{sequence}", account_id="account", sequence=sequence,
                transaction_type=kind, currency=Currency.USD,
                executed_at=NOW - timedelta(days=1), **kwargs))

        class Feed:
            def get_quotes(self, requested):
                return {asset.id: MarketQuote(asset.id, D({"stock": "20", "unclassified": "10",
                    "etf": "50"}[asset.id]), Currency.USD, NOW, NOW, "fixture") for asset in requested}

            def get_fx_rate(self, base, quote):
                return FxQuote(Currency.USD, Currency.KRW, D("1300"), NOW, NOW, "fixture")

        feed = Feed()
        analyzer = USPortfolioAnalyzer(store.accounts, store.assets, store.transactions, feed)
        result = analyzer.analyze("account", evaluated_at=NOW,
                                  max_quote_age=timedelta(minutes=1),
                                  max_fx_age=timedelta(minutes=1))
        assert result.total_value_usd == D("100")
        assert result.cash_balance == D("20")
        assert result.direct_sector_exposure == (DirectSectorExposure("Technology", D("20"), D("0.2")),)
        assert result.unclassified_stock_market_value == D("10")
        # If policy tries to read repositories or a provider, these fail.
        class Forbidden:
            def __getattr__(self, name):
                raise AssertionError(f"policy attempted I/O: {name}")

        analyzer._accounts = analyzer._assets = analyzer._transactions = analyzer._market_data = Forbidden()
        report = PortfolioPolicyEngine(load_portfolio_policy_config(CONFIG_FILE)).evaluate(result)
        assert decision(report, PolicyKind.DIRECT_SECTOR, PolicyTargetKind.DIRECT_SECTOR).actual_ratio == D("0.2")
        assert decision(report, PolicyKind.DIRECT_SECTOR, PolicyTargetKind.UNCLASSIFIED_STOCK).status is PolicyStatus.UNKNOWN
        assert len([item for item in report.evaluations if item.policy is PolicyKind.DIRECT_SECTOR]) == 2
        assert not any(item.target.identifier == "etf" for item in report.evaluations)
        stock_total = decision(report, PolicyKind.TOTAL_STOCK_EXPOSURE)
        assert stock_total.actual_ratio == D("0.30")
        assert stock_total.status is PolicyStatus.BREACH
        assert stock_total.thresholds.breach_ratio == D("0.30")


def test_stale_quote_is_rejected_before_policy_analysis_exists(tmp_path):
    with SQLiteStore(tmp_path / "empty.sqlite") as store:
        store.portfolios.add(Portfolio(id="portfolio", name="Portfolio"))
        store.accounts.add(Account(id="account", portfolio_id="portfolio", name="Account",
                                   account_type=AccountType.REAL, currency=Currency.USD))

        class StaleFxFeed:
            as_of = NOW

            def get_quotes(self, requested):
                raise AssertionError("no positions require prices")

            def get_fx_rate(self, base, quote):
                return FxQuote(Currency.USD, Currency.KRW, D("1300"),
                               self.as_of, NOW, "fixture")

        feed = StaleFxFeed()
        analyzer = USPortfolioAnalyzer(store.accounts, store.assets, store.transactions, feed)
        empty = analyzer.analyze("account", evaluated_at=NOW,
                                 max_quote_age=timedelta(minutes=1),
                                 max_fx_age=timedelta(minutes=1))
        report = PortfolioPolicyEngine(config()).evaluate(empty)
        assert report.not_applicable == (PolicyKind.INDIVIDUAL_STOCK, PolicyKind.DIRECT_SECTOR)
        assert decision(report, PolicyKind.CASH_RATIO).status is PolicyStatus.UNKNOWN
        feed.as_of = NOW - timedelta(hours=1)
        with pytest.raises(AnalysisError, match="stale FX"):
            analyzer.analyze("account", evaluated_at=NOW,
                             max_quote_age=timedelta(minutes=1),
                             max_fx_age=timedelta(minutes=1))
