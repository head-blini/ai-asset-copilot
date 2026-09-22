"""Hand-calculated examples for account ledger replay and manual valuation."""

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_UP, localcontext

import pytest

from asset_copilot.domain.models import (
    Account, AccountType, Asset, AssetType, Currency, Portfolio, Transaction, TransactionType,
)
from asset_copilot.portfolio.calculator import replay, value_at_prices


AT = datetime(2026, 1, 2, 15, 0, tzinfo=timezone.utc)
D = Decimal


def account(account_id: str = "acct-us", currency: Currency = Currency.USD) -> Account:
    return Account(id=account_id, portfolio_id="user-choice", name="Main", account_type=AccountType.REAL,
                   currency=currency)


def asset(asset_id: str = "voo", ticker: str = "VOO", currency: Currency = Currency.USD) -> Asset:
    return Asset(id=asset_id, ticker=ticker, name="Example", asset_type=AssetType.ETF,
                 market="US", exchange="NYSE", currency=currency)


def event(sequence: int, kind: TransactionType, **fields: object) -> Transaction:
    return Transaction(id=f"tx-{sequence}", account_id="acct-us", sequence=sequence,
                       transaction_type=kind, currency=Currency.USD, executed_at=AT, **fields)


def test_minimal_domain_records_are_immutable_and_have_no_persisted_balances() -> None:
    portfolio = Portfolio(id="custom-portfolio", name="Long term")
    owner = account()
    security = asset()
    assert portfolio.id == "custom-portfolio"
    assert owner.portfolio_id == "user-choice"
    assert owner.account_type is AccountType.REAL
    assert security.ticker == "VOO"
    assert security.sector is None
    assert not hasattr(owner, "cash_balance")
    with pytest.raises(FrozenInstanceError):
        owner.name = "Changed"


def test_deposit_and_single_buy_cash_and_basis() -> None:
    events = [event(1, TransactionType.DEPOSIT, amount=D("1000")),
              event(2, TransactionType.BUY, asset_id="voo", quantity=D("2"), price=D("100"))]
    snapshot = replay(account(), events, {"voo": asset()})
    assert snapshot.cash_balance == D("800")
    assert snapshot.positions[0].quantity == D("2")
    assert snapshot.positions[0].average_cost == D("100")
    assert snapshot.positions[0].cost_basis == D("200")
    assert snapshot.total_invested_cost == D("200")
    assert snapshot.realized_pnl == D("0")


def test_weighted_average_buy_fee_and_fractional_shares() -> None:
    events = [event(1, TransactionType.DEPOSIT, amount=D("10000")),
              event(2, TransactionType.BUY, asset_id="voo", quantity=D("10"), price=D("100"), fee=D("10")),
              event(3, TransactionType.BUY, asset_id="voo", quantity=D("10"), price=D("120")),
              event(4, TransactionType.BUY, asset_id="voo", quantity=D("0.5"), price=D("100"))]
    position = replay(account(), events, {"voo": asset()}).positions[0]
    assert position.quantity == D("20.5")
    assert position.cost_basis == D("2260")
    assert position.average_cost.quantize(D("0.000000000001")) == D("110.243902439024")


def test_partial_sell_uses_average_basis_and_deducts_sell_fee_once() -> None:
    events = [event(1, TransactionType.DEPOSIT, amount=D("3000")),
              event(2, TransactionType.BUY, asset_id="voo", quantity=D("10"), price=D("100"), fee=D("10")),
              event(3, TransactionType.BUY, asset_id="voo", quantity=D("10"), price=D("120")),
              event(4, TransactionType.SELL, asset_id="voo", quantity=D("5"), price=D("130"), fee=D("5"))]
    snapshot = replay(account(), events, {"voo": asset()})
    assert snapshot.positions[0].quantity == D("15")
    assert snapshot.positions[0].cost_basis == D("1657.5")
    assert snapshot.positions[0].average_cost == D("110.5")
    assert snapshot.cash_balance == D("1435")
    assert snapshot.realized_pnl == D("92.5")  # 650 - (5 * 110.5) - 5


def test_full_sell_removes_position_and_all_remaining_basis() -> None:
    events = [event(1, TransactionType.DEPOSIT, amount=D("10")),
              event(2, TransactionType.BUY, asset_id="voo", quantity=D("3"), price=D("1")),
              event(3, TransactionType.SELL, asset_id="voo", quantity=D("1"), price=D("2")),
              event(4, TransactionType.SELL, asset_id="voo", quantity=D("2"), price=D("2"))]
    snapshot = replay(account(), events, {"voo": asset()})
    assert snapshot.positions == ()
    assert snapshot.total_invested_cost == D("0")
    assert snapshot.realized_pnl == D("3")
    assert snapshot.cash_balance == D("13")


def test_withdrawal_and_dividend_change_cash_without_changing_basis() -> None:
    events = [event(1, TransactionType.DEPOSIT, amount=D("1000")),
              event(2, TransactionType.BUY, asset_id="voo", quantity=D("2"), price=D("100")),
              event(3, TransactionType.WITHDRAW, amount=D("50")),
              event(4, TransactionType.DIVIDEND, asset_id="voo", amount=D("5.25"))]
    snapshot = replay(account(), events, {"voo": asset()})
    assert snapshot.cash_balance == D("755.25")
    assert snapshot.positions[0].cost_basis == D("200")
    assert snapshot.realized_pnl == D("0")


@pytest.mark.parametrize("events,reason", [
    ([event(1, TransactionType.DEPOSIT, amount=D("100")),
      event(2, TransactionType.BUY, asset_id="voo", quantity=D("2"), price=D("60"))], "insufficient cash"),
    ([event(1, TransactionType.DEPOSIT, amount=D("100")),
      event(2, TransactionType.WITHDRAW, amount=D("101"))], "insufficient cash"),
    ([event(1, TransactionType.DEPOSIT, amount=D("100")),
      event(2, TransactionType.BUY, asset_id="voo", quantity=D("1"), price=D("50")),
      event(3, TransactionType.SELL, asset_id="voo", quantity=D("2"), price=D("50"))], "cannot sell"),
])
def test_insufficient_funds_and_short_sales_are_rejected(events: list[Transaction], reason: str) -> None:
    with pytest.raises(ValueError, match=reason):
        replay(account(), events, {"voo": asset()})


def test_currency_asset_and_account_boundaries() -> None:
    deposit = event(1, TransactionType.DEPOSIT, amount=D("100"))
    with pytest.raises(ValueError, match="transaction currency"):
        replay(account(currency=Currency.KRW), [deposit], {})
    with pytest.raises(ValueError, match="another account"):
        replay(account("other"), [deposit], {})
    buy = event(2, TransactionType.BUY, asset_id="voo", quantity=D("1"), price=D("10"))
    with pytest.raises(ValueError, match="asset currency"):
        replay(account(), [deposit, buy], {"voo": asset(currency=Currency.KRW)})


def test_krw_account_can_be_funded_only_by_its_own_ledger() -> None:
    paper = Account(id="paper-account", portfolio_id="strategy-purpose", name="Paper",
                    account_type=AccountType.PAPER, currency=Currency.KRW)
    seed = Transaction(id="seed", account_id=paper.id, sequence=1,
                       transaction_type=TransactionType.DEPOSIT, currency=Currency.KRW,
                       executed_at=AT, amount=D("10000000"))
    assert replay(paper, [seed], {}).cash_balance == D("10000000")
    assert replay(account(), [], {}).cash_balance == D("0")


def test_ordering_is_by_sequence_even_at_identical_timestamp() -> None:
    deposit = event(1, TransactionType.DEPOSIT, amount=D("100"))
    buy = event(2, TransactionType.BUY, asset_id="voo", quantity=D("1"), price=D("40"))
    expected = replay(account(), [deposit, buy], {"voo": asset()})
    assert replay(account(), [buy, deposit], {"voo": asset()}) == expected
    assert replay(account(), [deposit, buy], {"voo": asset()}) == expected
    with pytest.raises(ValueError, match="contiguous"):
        replay(account(), [deposit, event(3, TransactionType.DEPOSIT, amount=D("1"))], {})
    with pytest.raises(ValueError, match="precede"):
        replay(account(), [deposit, Transaction(id="late", account_id="acct-us", sequence=2,
               transaction_type=TransactionType.DEPOSIT, currency=Currency.USD,
               executed_at=AT - timedelta(seconds=1), amount=D("1"))], {})


def test_manual_prices_produce_market_value_unrealized_pnl_weights_and_cash_ratio() -> None:
    events = [event(1, TransactionType.DEPOSIT, amount=D("700")),
              event(2, TransactionType.BUY, asset_id="voo", quantity=D("2"), price=D("100"))]
    snapshot = replay(account(), events, {"voo": asset()})
    valuation = value_at_prices(snapshot, {"VOO": D("150")})
    assert valuation.positions[0].market_value == D("300")
    assert valuation.positions[0].unrealized_pnl == D("100")
    assert valuation.unrealized_pnl == D("100")
    assert valuation.total_account_value == D("800")
    assert valuation.positions[0].weight == D("0.375")
    assert valuation.cash_ratio == D("0.625")
    assert valuation.snapshot.realized_pnl == D("0")


def test_zero_value_and_missing_or_invalid_manual_prices() -> None:
    empty = replay(account(), [], {})
    valuation = value_at_prices(empty, {})
    assert valuation.total_account_value == D("0")
    assert valuation.cash_ratio is None
    funded = replay(account(), [event(1, TransactionType.DEPOSIT, amount=D("10")),
                                event(2, TransactionType.BUY, asset_id="voo", quantity=D("1"), price=D("5"))],
                    {"voo": asset()})
    with pytest.raises(ValueError, match="exactly"):
        value_at_prices(funded, {})
    with pytest.raises(ValueError, match="positive finite Decimal"):
        value_at_prices(funded, {"VOO": D("0")})
    with pytest.raises(ValueError, match="ambiguous ticker"):
        duplicate = replay(account(), [event(1, TransactionType.DEPOSIT, amount=D("20")),
                     event(2, TransactionType.BUY, asset_id="voo", quantity=D("1"), price=D("5")),
                     event(3, TransactionType.BUY, asset_id="other", quantity=D("1"), price=D("5"))],
                     {"voo": asset(), "other": asset("other", "VOO")})
        value_at_prices(duplicate, {"VOO": D("10")})


@pytest.mark.parametrize("kind,fields", [
    (TransactionType.BUY, {"asset_id": "voo", "quantity": D("0"), "price": D("1")}),
    (TransactionType.BUY, {"asset_id": "voo", "quantity": D("1"), "price": D("0")}),
    (TransactionType.SELL, {"asset_id": "voo", "quantity": D("1"), "price": D("1"), "fee": D("-1")}),
    (TransactionType.BUY, {"asset_id": "voo", "quantity": 1.0, "price": D("1")}),
    (TransactionType.DEPOSIT, {"amount": D("0")}),
    (TransactionType.DEPOSIT, {"amount": D("1"), "asset_id": "voo"}),
    (TransactionType.DIVIDEND, {"amount": D("1")}),
    (TransactionType.DIVIDEND, {"asset_id": "voo", "amount": D("1"), "quantity": D("1")}),
    (TransactionType.BUY, {"asset_id": "voo", "quantity": D("1"), "price": D("1"), "amount": D("1")}),
])
def test_invalid_transaction_field_combinations(kind: TransactionType, fields: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        event(1, kind, **fields)


def test_invalid_domain_identifiers_currencies_and_timestamps() -> None:
    with pytest.raises(ValueError, match="ticker"):
        asset(ticker="  ")
    with pytest.raises(ValueError, match="currency"):
        account(currency="EUR")
    with pytest.raises(ValueError, match="currency"):
        Transaction(id="bad-currency", account_id="acct-us", sequence=1,
                    transaction_type=TransactionType.DEPOSIT, currency="EUR",
                    executed_at=AT, amount=D("1"))
    with pytest.raises(ValueError, match="timezone-aware"):
        Transaction(id="naive", account_id="acct-us", sequence=1, transaction_type=TransactionType.DEPOSIT,
                    currency=Currency.USD, executed_at=datetime(2026, 1, 1), amount=D("1"))


def test_decimal_calculation_is_independent_of_caller_precision() -> None:
    events = [event(1, TransactionType.DEPOSIT, amount=D("1.000000000000000000000000000000000001")),
              event(2, TransactionType.BUY, asset_id="voo", quantity=D("0.000000000000000001"),
                    price=D("0.000000000000000001"))]
    with localcontext() as context:
        context.prec = 6
        snapshot = replay(account(), events, {"voo": asset()})
    assert snapshot.positions[0].cost_basis == D("0.000000000000000000000000000000000001")
    assert snapshot.cash_balance == D("1")


def test_nonterminating_average_is_independent_of_caller_rounding() -> None:
    events = [event(1, TransactionType.DEPOSIT, amount=D("100")),
              event(2, TransactionType.BUY, asset_id="voo", quantity=D("3"), price=D("1"), fee=D("1")),
              event(3, TransactionType.SELL, asset_id="voo", quantity=D("1"), price=D("2"))]
    with localcontext() as context:
        context.prec = 6
        context.rounding = ROUND_DOWN
        first = replay(account(), events, {"voo": asset()})
    with localcontext() as context:
        context.prec = 32
        context.rounding = ROUND_UP
        second = replay(account(), events, {"voo": asset()})
    assert first == second
    assert first.positions[0].quantity == D("2")
    assert first.positions[0].cost_basis.quantize(D("0.000001")) == D("2.666667")
