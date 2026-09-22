"""SQLite repositories; Decimal values are serialized as TEXT, never REAL."""

import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from asset_copilot.domain.models import (
    Account,
    AccountType,
    Asset,
    AssetType,
    Currency,
    Portfolio,
    Transaction,
    TransactionType,
)
from asset_copilot.portfolio.calculator import replay


SCHEMA = """
CREATE TABLE IF NOT EXISTS portfolios (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL REFERENCES portfolios(id),
    name TEXT NOT NULL,
    account_type TEXT NOT NULL,
    currency TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assets (
    id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    name TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    market TEXT NOT NULL,
    exchange TEXT NOT NULL,
    currency TEXT NOT NULL,
    sector TEXT
);
CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id),
    sequence INTEGER NOT NULL CHECK (sequence > 0),
    transaction_type TEXT NOT NULL,
    currency TEXT NOT NULL,
    executed_at TEXT NOT NULL,
    asset_id TEXT REFERENCES assets(id),
    quantity TEXT,
    price TEXT,
    fee TEXT NOT NULL,
    amount TEXT,
    UNIQUE (account_id, sequence)
);
CREATE INDEX IF NOT EXISTS transactions_by_account ON transactions(account_id, sequence);
CREATE TRIGGER IF NOT EXISTS transactions_no_update
BEFORE UPDATE ON transactions BEGIN SELECT RAISE(ABORT, 'ledger events are immutable'); END;
CREATE TRIGGER IF NOT EXISTS transactions_no_delete
BEFORE DELETE ON transactions BEGIN SELECT RAISE(ABORT, 'ledger events are immutable'); END;
"""


def _write(connection: sqlite3.Connection, statement: str, values: tuple[object, ...]) -> None:
    try:
        connection.execute(statement, values)
    except sqlite3.IntegrityError as error:
        raise ValueError(f"repository constraint failed: {error}") from error


class SQLitePortfolioRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def add(self, portfolio: Portfolio) -> None:
        _write(self._connection, "INSERT INTO portfolios (id, name) VALUES (?, ?)", (portfolio.id, portfolio.name))

    def get(self, portfolio_id: str) -> Portfolio | None:
        row = self._connection.execute("SELECT * FROM portfolios WHERE id = ?", (portfolio_id,)).fetchone()
        return None if row is None else Portfolio(id=row["id"], name=row["name"])


class SQLiteAccountRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def add(self, account: Account) -> None:
        _write(
            self._connection,
            "INSERT INTO accounts (id, portfolio_id, name, account_type, currency) VALUES (?, ?, ?, ?, ?)",
            (account.id, account.portfolio_id, account.name, account.account_type.value, account.currency.value),
        )

    def get(self, account_id: str) -> Account | None:
        row = self._connection.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        return None if row is None else Account(
            id=row["id"], portfolio_id=row["portfolio_id"], name=row["name"],
            account_type=AccountType(row["account_type"]), currency=Currency(row["currency"]),
        )


class SQLiteAssetRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def add(self, asset: Asset) -> None:
        _write(
            self._connection,
            "INSERT INTO assets (id, ticker, name, asset_type, market, exchange, currency, sector) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (asset.id, asset.ticker, asset.name, asset.asset_type.value, asset.market,
             asset.exchange, asset.currency.value, asset.sector),
        )

    def get(self, asset_id: str) -> Asset | None:
        row = self._connection.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
        return None if row is None else Asset(
            id=row["id"], ticker=row["ticker"], name=row["name"],
            asset_type=AssetType(row["asset_type"]), market=row["market"],
            exchange=row["exchange"], currency=Currency(row["currency"]), sector=row["sector"],
        )


class SQLiteTransactionRepository:
    def __init__(self, connection: sqlite3.Connection, accounts: SQLiteAccountRepository,
                 assets: SQLiteAssetRepository) -> None:
        self._connection = connection
        self._accounts = accounts
        self._assets = assets

    def list_for_account(self, account_id: str) -> list[Transaction]:
        rows = self._connection.execute(
            "SELECT * FROM transactions WHERE account_id = ? ORDER BY sequence", (account_id,)
        ).fetchall()
        return [Transaction(
            id=row["id"], account_id=row["account_id"], sequence=row["sequence"],
            transaction_type=TransactionType(row["transaction_type"]),
            currency=Currency(row["currency"]), executed_at=datetime.fromisoformat(row["executed_at"]),
            asset_id=row["asset_id"],
            quantity=None if row["quantity"] is None else Decimal(row["quantity"]),
            price=None if row["price"] is None else Decimal(row["price"]),
            fee=Decimal(row["fee"]), amount=None if row["amount"] is None else Decimal(row["amount"]),
        ) for row in rows]

    def append(self, transaction: Transaction) -> None:
        # Lock before reading: two writers cannot both validate against the same balance.
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            account = self._accounts.get(transaction.account_id)
            if account is None:
                raise ValueError("transaction account does not exist")
            history = self.list_for_account(account.id)
            if transaction.sequence != len(history) + 1:
                raise ValueError("new transaction sequence must be the next account sequence")
            asset_ids = {event.asset_id for event in history + [transaction] if event.asset_id is not None}
            assets = {asset_id: self._assets.get(asset_id) for asset_id in asset_ids}
            # replay validates cash, holdings, currencies and event chronology.
            replay(account, history + [transaction], assets)
            _write(
                self._connection,
                "INSERT INTO transactions (id, account_id, sequence, transaction_type, currency, "
                "executed_at, asset_id, quantity, price, fee, amount) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (transaction.id, transaction.account_id, transaction.sequence,
                 transaction.transaction_type.value, transaction.currency.value,
                 transaction.executed_at.isoformat(), transaction.asset_id,
                 None if transaction.quantity is None else str(transaction.quantity),
                 None if transaction.price is None else str(transaction.price),
                 str(transaction.fee), None if transaction.amount is None else str(transaction.amount)),
            )
        except Exception:
            self._connection.rollback()
            raise
        else:
            self._connection.commit()


class SQLiteStore:
    """Own one connection and expose four repository implementations."""

    def __init__(self, path: str | Path) -> None:
        self.connection = sqlite3.connect(str(path), isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            self.connection.close()
            raise ValueError(f"unsupported SQLite schema version: {version}")
        self.connection.executescript(SCHEMA)
        self.connection.execute("PRAGMA user_version = 1")
        self.portfolios = SQLitePortfolioRepository(self.connection)
        self.accounts = SQLiteAccountRepository(self.connection)
        self.assets = SQLiteAssetRepository(self.connection)
        self.transactions = SQLiteTransactionRepository(self.connection, self.accounts, self.assets)

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "SQLiteStore":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
