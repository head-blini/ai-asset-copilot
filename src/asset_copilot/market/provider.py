"""The application-facing contract does not expose provider request symbols."""

from typing import Protocol, Sequence

from asset_copilot.domain.models import Asset, Currency

from .models import FxQuote, MarketQuote


class MarketDataProvider(Protocol):
    def get_quotes(self, assets: Sequence[Asset]) -> dict[str, MarketQuote]:
        """Return observations keyed by canonical asset ID or raise a market-data error."""

    def get_fx_rate(self, base: Currency, quote: Currency) -> FxQuote:
        """Return quote-currency units per one base-currency unit."""
