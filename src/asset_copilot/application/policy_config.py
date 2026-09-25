"""Read a human-owned TOML policy into the validated, immutable policy input."""

from decimal import Decimal
from pathlib import Path
import tomllib

from asset_copilot.domain.policy import AllocationBand, AllocationBucket, PortfolioPolicyConfig
from asset_copilot.portfolio.calculator import _add, _div


_BUCKETS = (
    (AllocationBucket.CORE_ETF, "core_etf"),
    (AllocationBucket.GROWTH_ETF, "growth_etf"),
    (AllocationBucket.INDIVIDUAL_STOCKS, "individual_stocks"),
    (AllocationBucket.CASH, "cash"),
)
ZERO = Decimal("0")
ONE = Decimal("1")
HUNDRED = Decimal("100")


def _keys(data: dict, required: set[str], *, path: str,
          optional: frozenset[str] = frozenset()) -> None:
    missing = required - data.keys()
    unknown = data.keys() - required - optional
    if missing or unknown:
        raise ValueError(f"invalid policy schema at {path}: "
                         f"missing keys {sorted(missing)}, unknown keys {sorted(unknown)}")


def _table(data: dict, name: str) -> dict:
    value = data.get(name)
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a TOML table")
    return value


def _percent(data: dict, name: str) -> Decimal:
    value = data.get(name)
    if type(value) is not int and not isinstance(value, Decimal):
        raise ValueError(f"{name} must be a decimal percentage")
    percent = Decimal(value) if type(value) is int else value
    if not percent.is_finite() or not ZERO <= percent <= HUNDRED:
        raise ValueError(f"{name} must be between 0 and 100 percent")
    return _div(percent, HUNDRED)


def load_portfolio_policy_config(path: str | Path) -> PortfolioPolicyConfig:
    """Load the closed percentage-point schema; reject unrecognized keys at every level.

    All allocation targets/ranges are retained for evaluation. Policy change
    authorization and history remain separate open Phase 4 criteria.
    """
    with Path(path).open("rb") as source:
        data = tomllib.load(source, parse_float=Decimal)
    if not isinstance(data, dict):
        raise ValueError("policy must be a TOML table")
    _keys(data, {"policy_version", "target_percent", "range_percent", "risk_percent"}, path="root")
    targets = _table(data, "target_percent")
    ranges = _table(data, "range_percent")
    risk = _table(data, "risk_percent")
    _keys(targets, {name for _, name in _BUCKETS}, path="target_percent")
    _keys(ranges, {name for _, name in _BUCKETS}, path="range_percent")
    _keys(risk, {"individual_position_max", "concentration_warning", "sector_max",
                 "individual_stocks_total_max"}, path="risk_percent",
          optional=frozenset({"sector_warning"}))
    total_target = ZERO
    allocation_bands: list[AllocationBand] = []
    for bucket, name in _BUCKETS:
        target = _percent(targets, name)
        band = _table(ranges, name)
        _keys(band, {"min", "max"}, path=f"range_percent.{name}")
        minimum, maximum = _percent(band, "min"), _percent(band, "max")
        allocation_bands.append(AllocationBand(bucket, target, minimum, maximum))
        total_target = _add(total_target, target)
    if total_target != ONE:
        raise ValueError("allocation targets must sum to 100 percent")

    stock_breach = _percent(risk, "individual_position_max")
    stock_total_max = _percent(risk, "individual_stocks_total_max")
    if stock_breach > stock_total_max:
        raise ValueError("individual position max exceeds individual stocks total max")
    if _percent(targets, "individual_stocks") > stock_total_max:
        raise ValueError("individual stocks target exceeds its total max")
    sector_warn = (_percent(risk, "sector_warning")
                   if "sector_warning" in risk else None)
    return PortfolioPolicyConfig(
        policy_version=data.get("policy_version"),
        individual_stock_warn_ratio=_percent(risk, "concentration_warning"),
        individual_stock_breach_ratio=stock_breach,
        individual_stocks_total_max_ratio=stock_total_max,
        direct_sector_warn_ratio=sector_warn,
        direct_sector_breach_ratio=_percent(risk, "sector_max"),
        min_cash_ratio=_percent(_table(ranges, "cash"), "min"),
        max_cash_ratio=_percent(_table(ranges, "cash"), "max"),
        allocation_bands=tuple(allocation_bands),
    )
