"""Storage contracts; domain code does not depend on SQLite."""

from typing import Protocol

from .models import Account, Asset, Portfolio, Transaction


class PortfolioRepository(Protocol):
    def add(self, portfolio: Portfolio) -> None: ...

    def get(self, portfolio_id: str) -> Portfolio | None: ...


class AccountRepository(Protocol):
    def add(self, account: Account) -> None: ...

    def get(self, account_id: str) -> Account | None: ...


class AssetRepository(Protocol):
    def add(self, asset: Asset) -> None: ...

    def get(self, asset_id: str) -> Asset | None: ...


class TransactionRepository(Protocol):
    def append(self, transaction: Transaction) -> None: ...

    def list_for_account(self, account_id: str) -> list[Transaction]: ...
