"""Derive account state exclusively from ordered transaction events."""

from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from typing import Iterable, Mapping

from asset_copilot.domain.models import Account, Asset, Currency, Transaction, TransactionType


ZERO = Decimal("0")


def _precision(*values: Decimal) -> int:
    """Give finite additions/products enough digits independent of caller context."""
    return max(80, sum(len(v.as_tuple().digits) + abs(v.as_tuple().exponent) for v in values) + 16)


def _add(left: Decimal, right: Decimal) -> Decimal:
    with localcontext(Context(prec=_precision(left, right), rounding=ROUND_HALF_EVEN)):
        return left + right


def _sub(left: Decimal, right: Decimal) -> Decimal:
    with localcontext(Context(prec=_precision(left, right), rounding=ROUND_HALF_EVEN)):
        return left - right


def _mul(left: Decimal, right: Decimal) -> Decimal:
    with localcontext(Context(prec=_precision(left, right), rounding=ROUND_HALF_EVEN)):
        return left * right


def _div(left: Decimal, right: Decimal) -> Decimal:
    with localcontext(Context(prec=_precision(left, right), rounding=ROUND_HALF_EVEN)):
        return left / right


def _valid_price(price: Decimal) -> None:
    if not isinstance(price, Decimal) or not price.is_finite() or price <= 0:
        raise ValueError("market price must be a positive finite Decimal")


@dataclass(frozen=True, slots=True)
class Position:
    asset_id: str
    ticker: str
    quantity: Decimal
    average_cost: Decimal
    cost_basis: Decimal


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    account_id: str
    currency: Currency
    cash_balance: Decimal
    positions: tuple[Position, ...]
    total_invested_cost: Decimal
    realized_pnl: Decimal


@dataclass(frozen=True, slots=True)
class ValuedPosition:
    position: Position
    market_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    weight: Decimal


@dataclass(frozen=True, slots=True)
class AccountValuation:
    snapshot: AccountSnapshot
    positions: tuple[ValuedPosition, ...]
    total_account_value: Decimal
    unrealized_pnl: Decimal
    cash_ratio: Decimal | None


def replay(
    account: Account,
    transactions: Iterable[Transaction],
    assets: Mapping[str, Asset],
) -> AccountSnapshot:
    """Replay one account by contiguous sequence; reject invalid ledger history."""
    cash = ZERO
    realized = ZERO
    holdings: dict[str, tuple[Decimal, Decimal]] = {}
    seen_ids: set[str] = set()
    previous_time = None

    for expected_sequence, event in enumerate(sorted(transactions, key=lambda item: item.sequence), 1):
        if event.sequence != expected_sequence:
            raise ValueError("account ledger sequence must start at 1 and be contiguous")
        if event.id in seen_ids:
            raise ValueError("duplicate transaction id in ledger")
        seen_ids.add(event.id)
        if event.account_id != account.id:
            raise ValueError("transaction belongs to another account")
        if event.currency is not account.currency:
            raise ValueError("transaction currency differs from account currency")
        if previous_time is not None and event.executed_at < previous_time:
            raise ValueError("executed_at must not precede an earlier sequence")
        previous_time = event.executed_at

        asset = None
        if event.asset_id is not None:
            asset = assets.get(event.asset_id)
            if asset is None:
                raise ValueError("transaction asset is unknown")
            if asset.currency is not account.currency:
                raise ValueError("asset currency differs from account currency")

        if event.transaction_type is TransactionType.DEPOSIT:
            cash = _add(cash, event.amount)
        elif event.transaction_type is TransactionType.WITHDRAW:
            if event.amount > cash:
                raise ValueError("insufficient cash for withdrawal")
            cash = _sub(cash, event.amount)
        elif event.transaction_type is TransactionType.DIVIDEND:
            cash = _add(cash, event.amount)
        elif event.transaction_type is TransactionType.BUY:
            required = _add(_mul(event.quantity, event.price), event.fee)
            if required > cash:
                raise ValueError("insufficient cash for purchase")
            cash = _sub(cash, required)
            quantity, basis = holdings.get(event.asset_id, (ZERO, ZERO))
            holdings[event.asset_id] = (_add(quantity, event.quantity), _add(basis, required))
        elif event.transaction_type is TransactionType.SELL:
            quantity, basis = holdings.get(event.asset_id, (ZERO, ZERO))
            if event.quantity > quantity:
                raise ValueError("cannot sell more than owned")
            if event.quantity == quantity:
                disposed_basis = basis
                del holdings[event.asset_id]
            else:
                disposed_basis = _div(_mul(basis, event.quantity), quantity)
                holdings[event.asset_id] = (_sub(quantity, event.quantity), _sub(basis, disposed_basis))
            proceeds = _mul(event.quantity, event.price)
            cash = _add(cash, _sub(proceeds, event.fee))
            if cash < 0:
                raise ValueError("sale fee exceeds available cash and proceeds")
            realized = _add(realized, _sub(_sub(proceeds, disposed_basis), event.fee))

    positions = tuple(
        Position(asset_id, assets[asset_id].ticker, quantity, _div(basis, quantity), basis)
        for asset_id, (quantity, basis) in sorted(holdings.items())
    )
    total_invested_cost = ZERO
    for position in positions:
        total_invested_cost = _add(total_invested_cost, position.cost_basis)
    return AccountSnapshot(account.id, account.currency, cash, positions, total_invested_cost, realized)


def value_at_prices(snapshot: AccountSnapshot, prices: Mapping[str, Decimal]) -> AccountValuation:
    """Value every open position from an explicit ticker-to-price mapping."""
    expected = {position.ticker for position in snapshot.positions}
    if len(expected) != len(snapshot.positions):
        raise ValueError("ambiguous ticker in account; unique price key is required")
    if set(prices) != expected:
        raise ValueError("prices must cover exactly the open position tickers")

    priced: list[tuple[Position, Decimal, Decimal, Decimal]] = []
    invested_value = ZERO
    unrealized = ZERO
    for position in snapshot.positions:
        price = prices[position.ticker]
        _valid_price(price)
        market_value = _mul(position.quantity, price)
        position_unrealized = _sub(market_value, position.cost_basis)
        priced.append((position, price, market_value, position_unrealized))
        invested_value = _add(invested_value, market_value)
        unrealized = _add(unrealized, position_unrealized)

    total = _add(snapshot.cash_balance, invested_value)
    if total == 0:
        cash_ratio = None
        positions = tuple(ValuedPosition(position, price, market_value, position_unrealized, ZERO)
                          for position, price, market_value, position_unrealized in priced)
    else:
        cash_ratio = _div(snapshot.cash_balance, total)
        positions = tuple(ValuedPosition(position, price, market_value, position_unrealized,
                                         _div(market_value, total))
                          for position, price, market_value, position_unrealized in priced)
    return AccountValuation(snapshot, positions, total, unrealized, cash_ratio)
