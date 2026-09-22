"""Read a human-owned TOML policy into the validated, immutable policy input."""

from decimal import Decimal
from pathlib import Path
import tomllib

from asset_copilot.domain.policy import PortfolioPolicyConfig
from asset_copilot.portfolio.calculator import _add, _div


_BUCKETS = ("core_etf", "growth_etf", "individual_stocks", "cash")
ZERO = Decimal("0")
ONE = Decimal("1")
HUNDRED = Decimal("100")


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
    """Load the declared percentage-point policy; no implicit path or defaults."""
    with Path(path).open("rb") as source:
        data = tomllib.load(source, parse_float=Decimal)
    if not isinstance(data, dict):
        raise ValueError("policy must be a TOML table")
    targets = _table(data, "target_percent")
    ranges = _table(data, "range_percent")
    risk = _table(data, "risk_percent")
    total_target = ZERO
    for bucket in _BUCKETS:
        target = _percent(targets, bucket)
        band = _table(ranges, bucket)
        minimum, maximum = _percent(band, "min"), _percent(band, "max")
        if not minimum <= target <= maximum:
            raise ValueError(f"{bucket} target must lie within its range")
        total_target = _add(total_target, target)
    if total_target != ONE:
        raise ValueError("allocation targets must sum to 100 percent")

    single_breach = _percent(risk, "individual_position_max")
    stock_total_max = _percent(risk, "individual_stocks_total_max")
    if single_breach > stock_total_max:
        raise ValueError("individual position max exceeds individual stocks total max")
    if _percent(targets, "individual_stocks") > stock_total_max:
        raise ValueError("individual stocks target exceeds its total max")
    sector_warn = (_percent(risk, "sector_warning")
                   if "sector_warning" in risk else None)
    return PortfolioPolicyConfig(
        policy_version=data.get("policy_version"),
        single_asset_warn_ratio=_percent(risk, "concentration_warning"),
        single_asset_breach_ratio=single_breach,
        direct_sector_warn_ratio=sector_warn,
        direct_sector_breach_ratio=_percent(risk, "sector_max"),
        min_cash_ratio=_percent(_table(ranges, "cash"), "min"),
        max_cash_ratio=_percent(_table(ranges, "cash"), "max"),
    )
