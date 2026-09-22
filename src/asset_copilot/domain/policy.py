"""Immutable portfolio policy inputs and decisions."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


ZERO = Decimal("0")
ONE = Decimal("1")


class PolicyStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    BREACH = "BREACH"
    UNKNOWN = "UNKNOWN"


class PolicyKind(str, Enum):
    SINGLE_ASSET = "SINGLE_ASSET"
    DIRECT_SECTOR = "DIRECT_SECTOR"
    CASH_RATIO = "CASH_RATIO"


class PolicyTargetKind(str, Enum):
    ASSET = "ASSET"
    DIRECT_SECTOR = "DIRECT_SECTOR"
    UNCLASSIFIED_STOCK = "UNCLASSIFIED_STOCK"
    PORTFOLIO = "PORTFOLIO"


class PolicyReason(str, Enum):
    BELOW_WARNING = "BELOW_WARNING"
    BELOW_LIMIT = "BELOW_LIMIT"
    WARNING_LIMIT = "WARNING_LIMIT"
    BREACH_LIMIT = "BREACH_LIMIT"
    WITHIN_RANGE = "WITHIN_RANGE"
    BELOW_MINIMUM = "BELOW_MINIMUM"
    ABOVE_MAXIMUM = "ABOVE_MAXIMUM"
    UNCLASSIFIED_STOCK = "UNCLASSIFIED_STOCK"
    UNRELIABLE_ANALYSIS = "UNRELIABLE_ANALYSIS"
    ZERO_TOTAL_VALUE = "ZERO_TOTAL_VALUE"
    INVALID_EXPOSURE = "INVALID_EXPOSURE"


def _ratio(value: Decimal, field: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or not ZERO <= value <= ONE:
        raise ValueError(f"{field} must be a finite Decimal between 0 and 1")


@dataclass(frozen=True, slots=True, kw_only=True)
class PortfolioPolicyConfig:
    policy_version: str
    single_asset_warn_ratio: Decimal
    single_asset_breach_ratio: Decimal
    direct_sector_warn_ratio: Decimal | None
    direct_sector_breach_ratio: Decimal
    min_cash_ratio: Decimal
    max_cash_ratio: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.policy_version, str) or not self.policy_version.strip():
            raise ValueError("policy_version must be a nonempty string")
        for name in ("single_asset_warn_ratio", "single_asset_breach_ratio",
                     "direct_sector_breach_ratio", "min_cash_ratio", "max_cash_ratio"):
            _ratio(getattr(self, name), name)
        if self.direct_sector_warn_ratio is not None:
            _ratio(self.direct_sector_warn_ratio, "direct_sector_warn_ratio")
            if self.direct_sector_warn_ratio > self.direct_sector_breach_ratio:
                raise ValueError("direct sector warning exceeds breach")
        if self.single_asset_warn_ratio > self.single_asset_breach_ratio:
            raise ValueError("single asset warning exceeds breach")
        if self.min_cash_ratio > self.max_cash_ratio:
            raise ValueError("minimum cash exceeds maximum cash")


@dataclass(frozen=True, slots=True)
class PolicyTarget:
    kind: PolicyTargetKind
    identifier: str | None = None


@dataclass(frozen=True, slots=True)
class ConcentrationThresholds:
    warn_ratio: Decimal | None
    breach_ratio: Decimal


@dataclass(frozen=True, slots=True)
class CashRangeThresholds:
    min_ratio: Decimal
    max_ratio: Decimal


@dataclass(frozen=True, slots=True)
class PolicyEvaluation:
    policy: PolicyKind
    target: PolicyTarget
    status: PolicyStatus
    actual_ratio: Decimal | None
    thresholds: ConcentrationThresholds | CashRangeThresholds
    reason_code: PolicyReason
    reason: str


@dataclass(frozen=True, slots=True)
class PortfolioPolicyReport:
    account_id: str
    evaluated_at: datetime
    policy_version: str
    evaluations: tuple[PolicyEvaluation, ...]
    not_applicable: tuple[PolicyKind, ...]
