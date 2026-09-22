"""Provider-neutral failures at the market data boundary."""


class MarketDataError(Exception):
    """Base error for market data acquisition or normalization."""


class AuthenticationError(MarketDataError):
    pass


class RateLimitError(MarketDataError):
    pass


class InstrumentError(MarketDataError):
    pass


class ResponseError(MarketDataError):
    pass


class NetworkError(MarketDataError):
    pass


class RequestTimeoutError(NetworkError):
    pass
