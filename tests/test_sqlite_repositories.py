"""Persistence, isolation and replay after an SQLite reopen."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from threading import Barrier
from zoneinfo import ZoneInfo

import pytest

from asset_copilot.domain.models import (
    Account, AccountType, Asset, AssetType, Currency, Portfolio, Transaction, TransactionType,
)
from asset_copilot.portfolio.calculator import replay
from asset_copilot.storage.sqlite import SQLiteStore


D = Decimal
AT = datetime(2026, 1, 2, 15, 0, tzinfo=timezone.utc)


def setup_store(store: SQLiteStore) -> tuple[Account, Account, Asset]:
    store.portfolios.add(Portfolio(id="real-purpose", name="Real"))
    store.portfolios.add(Portfolio(id="shadow-purpose", name="Shadow"))
    real = Account(id="real-account", portfolio_id="real-purpose", name="Real account",
                   account_type=AccountType.REAL, currency=Currency.USD)
    shadow = Account(id="shadow-account", portfolio_id="shadow-purpose", name="Virtual account",
                     account_type=AccountType.SHADOW, currency=Currency.USD)
    store.accounts.add(real)
    store.accounts.add(shadow)
    security = Asset(id="asset-1", ticker="VOO", name="Vanguard S&P 500 ETF",
                     asset_type=AssetType.ETF, market="US", exchange="NYSE ARCA",
                     currency=Currency.USD, sector=None)
    store.assets.add(security)
    return real, shadow, security


def tx(transaction_id: str, account_id: str, sequence: int, kind: TransactionType, **fields: object) -> Transaction:
    return Transaction(id=transaction_id, account_id=account_id, sequence=sequence,
                       transaction_type=kind, currency=Currency.USD, executed_at=AT, **fields)


def test_repositories_create_and_retrieve_records(tmp_path) -> None:
    with SQLiteStore(tmp_path / "foundation.sqlite") as store:
        real, shadow, security = setup_store(store)
        assert store.portfolios.get("real-purpose") == Portfolio(id="real-purpose", name="Real")
        assert store.accounts.get(real.id) == real
        assert store.accounts.get(shadow.id) == shadow
        assert store.assets.get(security.id) == security
        assert store.accounts.get("missing") is None
        peer = replace(real, id="another-account", name="Second real account")
        store.accounts.add(peer)
        assert store.accounts.get(peer.id).portfolio_id == real.portfolio_id
        with pytest.raises(ValueError, match="constraint"):
            store.accounts.add(replace(real, id="orphan", portfolio_id="missing"))


def test_account_ledgers_are_isolated_and_replay_after_reopen(tmp_path) -> None:
    path = tmp_path / "foundation.sqlite"
    with SQLiteStore(path) as store:
        real, shadow, security = setup_store(store)
        store.transactions.append(tx("real-deposit", real.id, 1, TransactionType.DEPOSIT, amount=D("1000")))
        store.transactions.append(tx("real-buy", real.id, 2, TransactionType.BUY,
                                     asset_id=security.id, quantity=D("2"), price=D("100")))
        store.transactions.append(tx("shadow-deposit", shadow.id, 1, TransactionType.DEPOSIT, amount=D("500")))
        real_ledger = store.transactions.list_for_account(real.id)
        shadow_ledger = store.transactions.list_for_account(shadow.id)
        real_before = replay(real, real_ledger, {security.id: security})
        shadow_before = replay(shadow, shadow_ledger, {security.id: security})
        assert real_before.cash_balance == D("800")
        assert real_before.positions[0].quantity == D("2")
        assert shadow_before.cash_balance == D("500")
        assert shadow_before.positions == ()

    with SQLiteStore(path) as store:
        real_after = store.accounts.get(real.id)
        shadow_after = store.accounts.get(shadow.id)
        asset_after = store.assets.get(security.id)
        assert store.transactions.list_for_account(real.id) == real_ledger
        assert store.transactions.list_for_account(shadow.id) == shadow_ledger
        assert replay(real_after, store.transactions.list_for_account(real.id),
                      {security.id: asset_after}) == real_before
        assert replay(shadow_after, store.transactions.list_for_account(shadow.id),
                      {security.id: asset_after}) == shadow_before


def test_valid_historical_backfill_replays_by_time_after_sqlite_reopen(tmp_path) -> None:
    path = tmp_path / "backfill.sqlite"
    sep10 = datetime(2026, 9, 10, tzinfo=timezone.utc)
    sep20 = datetime(2026, 9, 20, tzinfo=timezone.utc)
    sep21 = datetime(2026, 9, 21, tzinfo=timezone.utc)
    with SQLiteStore(path) as store:
        real, _, security = setup_store(store)
        store.transactions.append(replace(tx("sep20-deposit", real.id, 1, TransactionType.DEPOSIT,
                                             amount=D("100")), executed_at=sep20))
        store.transactions.append(replace(tx("sep21-buy", real.id, 2, TransactionType.BUY,
                                             asset_id=security.id, quantity=D("1"), price=D("60")),
                                          executed_at=sep21))
        store.transactions.append(replace(tx("sep10-deposit", real.id, 3, TransactionType.DEPOSIT,
                                             amount=D("25")), executed_at=sep10))
        ledger = store.transactions.list_for_account(real.id)
        assert [event.id for event in ledger] == ["sep20-deposit", "sep21-buy", "sep10-deposit"]
        before = replay(real, ledger, {security.id: security})
        assert before.cash_balance == D("65")
        assert before.positions[0].cost_basis == D("60")

    with SQLiteStore(path) as store:
        assert store.transactions.list_for_account(real.id) == ledger
        assert replay(store.accounts.get(real.id), store.transactions.list_for_account(real.id),
                      {security.id: store.assets.get(security.id)}) == before


def test_invalid_backfill_rolls_back_entire_ledger(tmp_path) -> None:
    sep10 = datetime(2026, 9, 10, tzinfo=timezone.utc)
    sep15 = datetime(2026, 9, 15, tzinfo=timezone.utc)
    sep20 = datetime(2026, 9, 20, tzinfo=timezone.utc)
    with SQLiteStore(tmp_path / "backfill.sqlite") as store:
        real, _, security = setup_store(store)
        store.transactions.append(replace(tx("opening", real.id, 1, TransactionType.DEPOSIT,
                                             amount=D("100")), executed_at=sep10))
        store.transactions.append(replace(tx("existing-buy", real.id, 2, TransactionType.BUY,
                                             asset_id=security.id, quantity=D("1"), price=D("80")),
                                          executed_at=sep20))
        before = store.transactions.list_for_account(real.id)
        # The withdrawal itself is affordable on Sep 15; the Sep 20 buy becomes invalid.
        with pytest.raises(ValueError, match="insufficient cash"):
            store.transactions.append(replace(tx("late-withdraw", real.id, 3, TransactionType.WITHDRAW,
                                                 amount=D("50")), executed_at=sep15))
        assert store.transactions.list_for_account(real.id) == before
        with pytest.raises(ValueError, match="cannot sell"):
            store.transactions.append(replace(tx("early-sell", real.id, 3, TransactionType.SELL,
                                                 asset_id=security.id, quantity=D("1"), price=D("90")),
                                              executed_at=sep15))
        assert store.transactions.list_for_account(real.id) == before
        assert replay(real, before, {security.id: security}).cash_balance == D("20")


def test_decimal_text_round_trip_preserves_exponents_and_long_fraction(tmp_path) -> None:
    path = tmp_path / "precision.sqlite"
    deposit_amount = D("1.000000000000000000000000000000000001")
    quantity = D("0.000000000000000001")
    price = D("0.000000000000000001")
    fee = D("0E-36")
    with SQLiteStore(path) as store:
        real, _, security = setup_store(store)
        store.transactions.append(tx("precision-deposit", real.id, 1, TransactionType.DEPOSIT,
                                     amount=deposit_amount))
        store.transactions.append(tx("precision-buy", real.id, 2, TransactionType.BUY,
                                     asset_id=security.id, quantity=quantity, price=price, fee=fee))
        row = store.connection.execute("SELECT typeof(quantity), typeof(price), typeof(fee), "
                                       "typeof(amount) FROM transactions WHERE id = 'precision-buy'").fetchone()
        assert tuple(row) == ("text", "text", "text", "null")
        assert store.connection.execute("SELECT typeof(amount) FROM transactions WHERE id = 'precision-deposit'").fetchone()[0] == "text"

    with SQLiteStore(path) as store:
        stored_deposit, stored_buy = store.transactions.list_for_account(real.id)
        assert stored_deposit.amount.as_tuple() == deposit_amount.as_tuple()
        assert stored_buy.quantity.as_tuple() == quantity.as_tuple()
        assert stored_buy.price.as_tuple() == price.as_tuple()
        assert stored_buy.fee.as_tuple() == fee.as_tuple()
        snapshot = replay(store.accounts.get(real.id), [stored_buy, stored_deposit],
                          {security.id: store.assets.get(security.id)})
        assert snapshot.cash_balance == D("1")
        assert snapshot.positions[0].cost_basis == D("0.000000000000000000000000000000000001")


def test_append_rejects_invalid_event_without_partial_ledger_change(tmp_path) -> None:
    with SQLiteStore(tmp_path / "foundation.sqlite") as store:
        real, shadow, security = setup_store(store)
        store.transactions.append(tx("deposit", real.id, 1, TransactionType.DEPOSIT, amount=D("100")))
        bad_events = [
            tx("too-much", real.id, 2, TransactionType.BUY, asset_id=security.id,
               quantity=D("2"), price=D("60")),
            tx("withdraw-too-much", real.id, 2, TransactionType.WITHDRAW, amount=D("101")),
            tx("wrong-sequence", real.id, 3, TransactionType.DEPOSIT, amount=D("1")),
            tx("wrong-currency", real.id, 2, TransactionType.DEPOSIT, amount=D("1")),
        ]
        bad_events[-1] = replace(bad_events[-1], currency=Currency.KRW)
        for bad in bad_events:
            with pytest.raises(ValueError):
                store.transactions.append(bad)
            assert [event.id for event in store.transactions.list_for_account(real.id)] == ["deposit"]
        with pytest.raises(ValueError, match="next account sequence"):
            store.transactions.append(tx("cross-account-seq", shadow.id, 2,
                                         TransactionType.DEPOSIT, amount=D("1")))
        with pytest.raises(ValueError, match="does not exist"):
            store.transactions.append(tx("missing-account", "missing", 1,
                                         TransactionType.DEPOSIT, amount=D("1")))
        store.transactions.append(tx("valid", real.id, 2, TransactionType.BUY,
                                     asset_id=security.id, quantity=D("1"), price=D("60")))
        assert replay(real, store.transactions.list_for_account(real.id),
                      {security.id: security}).cash_balance == D("40")


def test_committed_ledger_events_cannot_be_updated_or_deleted(tmp_path) -> None:
    with SQLiteStore(tmp_path / "foundation.sqlite") as store:
        real, _, _ = setup_store(store)
        store.transactions.append(tx("deposit", real.id, 1, TransactionType.DEPOSIT, amount=D("100")))
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            store.connection.execute("UPDATE transactions SET amount = '1000' WHERE id = 'deposit'")
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            store.connection.execute("DELETE FROM transactions WHERE id = 'deposit'")
        assert store.transactions.list_for_account(real.id)[0].amount == D("100")


def test_two_store_connections_cannot_spend_the_same_cash_twice(tmp_path) -> None:
    path = tmp_path / "foundation.sqlite"
    with SQLiteStore(path) as first, SQLiteStore(path) as second:
        real, _, security = setup_store(first)
        first.transactions.append(tx("deposit", real.id, 1, TransactionType.DEPOSIT, amount=D("100")))
        first.transactions.append(tx("first-buy", real.id, 2, TransactionType.BUY,
                                     asset_id=security.id, quantity=D("1"), price=D("60")))
        with pytest.raises(ValueError, match="insufficient cash"):
            second.transactions.append(tx("second-buy", real.id, 3, TransactionType.BUY,
                                          asset_id=security.id, quantity=D("1"), price=D("60")))
        assert len(second.transactions.list_for_account(real.id)) == 2


def test_commit_busy_rolls_back_and_connection_can_be_reused(tmp_path) -> None:
    path = tmp_path / "commit-busy.sqlite"
    with SQLiteStore(path) as store:
        real, _, _ = setup_store(store)
        reader = sqlite3.connect(path, isolation_level=None)
        try:
            reader.execute("BEGIN")
            reader.execute("SELECT * FROM transactions").fetchall()
            store.connection.execute("PRAGMA busy_timeout = 0")
            deposit = tx("deposit", real.id, 1, TransactionType.DEPOSIT, amount=D("100"))
            # A rollback-journal reader allows INSERT but prevents COMMIT.
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                store.transactions.append(deposit)
            assert not store.connection.in_transaction
            assert store.transactions.list_for_account(real.id) == []
        finally:
            reader.rollback()
            reader.close()
        store.transactions.append(deposit)
        assert store.transactions.list_for_account(real.id) == [deposit]
    with SQLiteStore(path) as store:
        assert store.transactions.list_for_account(real.id) == [deposit]


def test_interrupted_append_releases_transaction(tmp_path, monkeypatch) -> None:
    import asset_copilot.storage.sqlite as adapter

    def interrupted(*args):
        raise KeyboardInterrupt

    with SQLiteStore(tmp_path / "interrupt.sqlite") as store:
        real, _, _ = setup_store(store)
        monkeypatch.setattr(adapter, "replay", interrupted)
        with pytest.raises(KeyboardInterrupt):
            store.transactions.append(tx("deposit", real.id, 1, TransactionType.DEPOSIT, amount=D("100")))
        assert not store.connection.in_transaction
        assert store.transactions.list_for_account(real.id) == []


def test_sqlite_replace_cannot_rewrite_existing_ledger_event(tmp_path) -> None:
    with SQLiteStore(tmp_path / "immutable.sqlite") as store:
        real, _, _ = setup_store(store)
        deposit = tx("deposit", real.id, 1, TransactionType.DEPOSIT, amount=D("100"))
        store.transactions.append(deposit)
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            store.connection.execute(
                "INSERT OR REPLACE INTO transactions "
                "SELECT id, account_id, sequence, transaction_type, currency, executed_at, "
                "asset_id, quantity, price, fee, '999' FROM transactions WHERE id = 'deposit'"
            )
        assert store.transactions.list_for_account(real.id) == [deposit]


def test_dst_fold_replay_matches_sqlite_round_trip(tmp_path) -> None:
    path = tmp_path / "dst.sqlite"
    zone = ZoneInfo("America/New_York")
    with SQLiteStore(path) as store:
        real, _, security = setup_store(store)
        ledger = [
            replace(tx("deposit", real.id, 1, TransactionType.DEPOSIT, amount=D("100")),
                    executed_at=datetime(2025, 11, 2, 1, 45, tzinfo=zone, fold=0)),
            replace(tx("buy", real.id, 2, TransactionType.BUY, asset_id=security.id,
                       quantity=D("1"), price=D("60")),
                    executed_at=datetime(2025, 11, 2, 1, 30, tzinfo=zone, fold=1)),
        ]
        before = replay(real, ledger, {security.id: security})
        assert before.cash_balance == D("40")
        for transaction in ledger:
            store.transactions.append(transaction)
    with SQLiteStore(path) as store:
        assert replay(store.accounts.get(real.id), store.transactions.list_for_account(real.id),
                      {security.id: store.assets.get(security.id)}) == before


def test_simultaneous_connections_cannot_both_append_next_sequence(tmp_path) -> None:
    path = tmp_path / "concurrent.sqlite"
    with SQLiteStore(path) as store:
        real, _, _ = setup_store(store)
        store.transactions.append(tx("deposit", real.id, 1, TransactionType.DEPOSIT, amount=D("100")))
    ready = Barrier(2)

    def withdraw(transaction_id: str) -> str:
        with SQLiteStore(path) as store:
            ready.wait(timeout=5)
            try:
                store.transactions.append(tx(transaction_id, real.id, 2, TransactionType.WITHDRAW, amount=D("80")))
            except ValueError as error:
                assert "next account sequence" in str(error)
                return "rejected"
            return "committed"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(withdraw, ["first", "second"]))
    assert sorted(outcomes) == ["committed", "rejected"]
    with SQLiteStore(path) as store:
        ledger = store.transactions.list_for_account(real.id)
        assert len(ledger) == 2
        assert replay(real, ledger, {}).cash_balance == D("20")
