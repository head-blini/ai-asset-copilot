"""Immutable portfolio policy inputs and decisions."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from fractions import Fraction


ZERO = Decimal("0")
ONE = Decimal("1")


class PolicyStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    BREACH = "BREACH"
    UNKNOWN = "UNKNOWN"


class PolicyKind(str, Enum):
    INDIVIDUAL_STOCK = "INDIVIDUAL_STOCK"
    TOTAL_STOCK_EXPOSURE = "TOTAL_STOCK_EXPOSURE"
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
    UNCLASSIFIED_ETF = "UNCLASSIFIED_ETF"
    DUPLICATE_POSITION = "DUPLICATE_POSITION"
    INVALID_ANALYSIS = "INVALID_ANALYSIS"


class AllocationBucket(str, Enum):
    CORE_ETF = "CORE_ETF"
    GROWTH_ETF = "GROWTH_ETF"
    INDIVIDUAL_STOCKS = "INDIVIDUAL_STOCKS"
    CASH = "CASH"


ALLOCATION_BUCKETS = tuple(AllocationBucket)


class ETFGroup(str, Enum):
    CORE = "CORE"
    GROWTH = "GROWTH"


def _ratio(value: Decimal, field: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or not ZERO <= value <= ONE:
        raise ValueError(f"{field} must be a finite Decimal between 0 and 1")


@dataclass(frozen=True, slots=True)
class AllocationBand:
    bucket: AllocationBucket
    target_ratio: Decimal
    min_ratio: Decimal
    max_ratio: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.bucket, AllocationBucket):
            raise ValueError("allocation bucket must be an AllocationBucket")
        for name in ("target_ratio", "min_ratio", "max_ratio"):
            _ratio(getattr(self, name), name)
        if not self.min_ratio <= self.target_ratio <= self.max_ratio:
            raise ValueError("allocation target must lie within its inclusive range")


@dataclass(frozen=True, slots=True)
class ETFClassification:
    asset_id: str
    group: ETFGroup

    def __post_init__(self) -> None:
        if not isinstance(self.asset_id, str) or not self.asset_id.strip():
            raise ValueError("ETF classification needs a nonempty asset_id")
        if not isinstance(self.group, ETFGroup):
            raise ValueError("ETF classification must be CORE or GROWTH")


@dataclass(frozen=True, slots=True, kw_only=True)
class PortfolioPolicyConfig:
    policy_version: str
    individual_stock_warn_ratio: Decimal
    individual_stock_breach_ratio: Decimal
    individual_stocks_total_max_ratio: Decimal
    direct_sector_warn_ratio: Decimal | None
    direct_sector_breach_ratio: Decimal
    min_cash_ratio: Decimal
    max_cash_ratio: Decimal
    allocation_bands: tuple[AllocationBand, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.policy_version, str) or not self.policy_version.strip():
            raise ValueError("policy_version must be a nonempty string")
        for name in ("individual_stock_warn_ratio", "individual_stock_breach_ratio",
                     "individual_stocks_total_max_ratio",
                     "direct_sector_breach_ratio", "min_cash_ratio", "max_cash_ratio"):
            _ratio(getattr(self, name), name)
        if self.direct_sector_warn_ratio is not None:
            _ratio(self.direct_sector_warn_ratio, "direct_sector_warn_ratio")
            if self.direct_sector_warn_ratio > self.direct_sector_breach_ratio:
                raise ValueError("direct sector warning exceeds breach")
        if self.individual_stock_warn_ratio > self.individual_stock_breach_ratio:
            raise ValueError("individual stock warning exceeds breach")
        if self.individual_stock_breach_ratio > self.individual_stocks_total_max_ratio:
            raise ValueError("individual stock breach exceeds total stock limit")
        if self.min_cash_ratio > self.max_cash_ratio:
            raise ValueError("minimum cash exceeds maximum cash")
        if not isinstance(self.allocation_bands, tuple) or len(self.allocation_bands) != len(ALLOCATION_BUCKETS) \
                or not all(isinstance(band, AllocationBand) for band in self.allocation_bands):
            raise ValueError("all four allocation bands are required")
        by_bucket = {band.bucket: band for band in self.allocation_bands}
        if len(by_bucket) != len(ALLOCATION_BUCKETS) or set(by_bucket) != set(ALLOCATION_BUCKETS):
            raise ValueError("allocation bands must cover each bucket exactly once")
        if sum((Fraction(band.target_ratio) for band in self.allocation_bands), Fraction(0)) != 1:
            raise ValueError("allocation targets must sum to one")
        cash = by_bucket[AllocationBucket.CASH]
        if (self.min_cash_ratio, self.max_cash_ratio) != (cash.min_ratio, cash.max_ratio):
            raise ValueError("cash allocation range conflicts with cash policy range")
        if by_bucket[AllocationBucket.INDIVIDUAL_STOCKS].target_ratio > self.individual_stocks_total_max_ratio:
            raise ValueError("individual stocks target exceeds total stock limit")


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
class AllocationEvaluation:
    bucket: AllocationBucket
    market_value_usd: Decimal | None
    actual_ratio: Decimal | None
    target_ratio: Decimal
    min_ratio: Decimal
    max_ratio: Decimal
    target_delta_ratio: Decimal | None
    status: PolicyStatus
    reason_code: PolicyReason
    reason: str


@dataclass(frozen=True, slots=True)
class PortfolioPolicyReport:
    account_id: str
    evaluated_at: datetime
    policy_version: str
    evaluations: tuple[PolicyEvaluation, ...]
    not_applicable: tuple[PolicyKind, ...]
    allocation_evaluations: tuple[AllocationEvaluation, ...]
