"""Pure current-state policy evaluation over a completed PortfolioAnalysis."""

from collections.abc import Sequence
from decimal import Decimal

from asset_copilot.application.us_portfolio_analytics import (
    DirectSectorExposure, PortfolioAnalysis, PositionAnalysis,
)
from asset_copilot.domain.models import AssetType, Currency
from asset_copilot.domain.policy import (
    ALLOCATION_BUCKETS, AllocationBucket, AllocationEvaluation, CashRangeThresholds,
    ConcentrationThresholds, ETFClassification, ETFGroup, PolicyEvaluation,
    PolicyKind, PolicyReason, PolicyStatus, PolicyTarget, PolicyTargetKind,
    PortfolioPolicyConfig, PortfolioPolicyReport,
)
from asset_copilot.portfolio.calculator import _add, _div, _mul, _sub


ZERO = Decimal("0")
ONE = Decimal("1")


def _valid_ratio(value: Decimal | None) -> bool:
    return isinstance(value, Decimal) and value.is_finite() and ZERO <= value <= ONE


def _valid_value(value: Decimal | None, total: Decimal) -> bool:
    return isinstance(value, Decimal) and value.is_finite() and ZERO <= value <= total


def _unknown(policy: PolicyKind, target: PolicyTarget, actual: Decimal | None,
             thresholds: ConcentrationThresholds | CashRangeThresholds,
             reason_code: PolicyReason, reason: str) -> PolicyEvaluation:
    return PolicyEvaluation(policy, target, PolicyStatus.UNKNOWN, actual, thresholds,
                            reason_code, reason)


def _concentration(policy: PolicyKind, target: PolicyTarget, value: Decimal | None,
                   actual: Decimal | None, total: Decimal,
                   thresholds: ConcentrationThresholds, reliable: bool) -> PolicyEvaluation:
    if not reliable:
        return _unknown(policy, target, None, thresholds, PolicyReason.UNRELIABLE_ANALYSIS,
                        "Analysis evidence is unsuitable for policy evaluation")
    if total == ZERO:
        return _unknown(policy, target, None, thresholds, PolicyReason.ZERO_TOTAL_VALUE,
                        "Portfolio exposure is undefined at zero total value")
    if value is None or not _valid_value(value, total) or not _valid_ratio(actual):
        return _unknown(policy, target, None, thresholds, PolicyReason.INVALID_EXPOSURE,
                        "Required exposure is missing or invalid")
    # Compare exact Decimal values before division or display rounding. This also
    # keeps a repeating ratio at its mathematically correct threshold boundary.
    if value >= _mul(thresholds.breach_ratio, total):
        status, code, reason = PolicyStatus.BREACH, PolicyReason.BREACH_LIMIT, "At or above breach limit"
    elif thresholds.warn_ratio is not None and value >= _mul(thresholds.warn_ratio, total):
        status, code, reason = PolicyStatus.WARN, PolicyReason.WARNING_LIMIT, "At or above warning limit"
    else:
        code = PolicyReason.BELOW_WARNING if thresholds.warn_ratio is not None else PolicyReason.BELOW_LIMIT
        status, reason = PolicyStatus.PASS, "Below concentration limits"
    return PolicyEvaluation(policy, target, status, _div(value, total), thresholds, code, reason)


def _classified_etfs(positions: tuple[PositionAnalysis, ...],
                     classifications: Sequence[ETFClassification]) -> dict[str, ETFGroup]:
    if not isinstance(classifications, Sequence) or isinstance(classifications, (str, bytes)):
        raise TypeError("etf_classifications must be a sequence of ETFClassification")
    assets = {item.asset_id: item for item in positions
              if isinstance(item, PositionAnalysis) and isinstance(item.asset_id, str)}
    groups: dict[str, ETFGroup] = {}
    for item in classifications:
        if not isinstance(item, ETFClassification):
            raise TypeError("etf_classifications must contain ETFClassification values")
        if item.asset_id in groups:
            raise ValueError(f"duplicate or conflicting ETF classification: {item.asset_id}")
        asset = assets.get(item.asset_id)
        if asset is None:
            raise ValueError(f"classification asset_id is absent from analysis: {item.asset_id}")
        if asset.asset_type is not AssetType.ETF:
            raise ValueError(f"classification asset_id is not an ETF: {item.asset_id}")
        groups[item.asset_id] = item.group
    return groups


def _allocation_evaluations(analysis: PortfolioAnalysis, config: PortfolioPolicyConfig,
                            positions: tuple[PositionAnalysis, ...],
                            groups: dict[str, ETFGroup]) -> tuple[AllocationEvaluation, ...]:
    bands = {band.bucket: band for band in config.allocation_bands}

    def unknown(code: PolicyReason, reason: str) -> tuple[AllocationEvaluation, ...]:
        return tuple(AllocationEvaluation(bucket, None, None, bands[bucket].target_ratio,
                     bands[bucket].min_ratio, bands[bucket].max_ratio, None,
                     PolicyStatus.UNKNOWN, code, reason) for bucket in ALLOCATION_BUCKETS)

    if analysis.all_quotes_fresh is not True or analysis.fx_fresh is not True \
            or analysis.currency is not Currency.USD:
        return unknown(PolicyReason.UNRELIABLE_ANALYSIS,
                       "Analysis evidence is unsuitable for allocation evaluation")
    if not isinstance(analysis.positions, tuple) or not all(
            isinstance(item, PositionAnalysis) and isinstance(item.asset_type, AssetType)
               and isinstance(item.asset_id, str) and item.asset_id.strip()
               for item in analysis.positions):
        return unknown(PolicyReason.INVALID_ANALYSIS, "Position identity or type is invalid")
    asset_ids = [item.asset_id for item in positions]
    if len(set(asset_ids)) != len(asset_ids):
        return unknown(PolicyReason.DUPLICATE_POSITION, "Duplicate asset_id in analysis positions")
    total = analysis.total_value_usd
    if not isinstance(total, Decimal) or not total.is_finite() or total < ZERO:
        return unknown(PolicyReason.INVALID_ANALYSIS, "Total USD value is invalid")
    if total == ZERO:
        return unknown(PolicyReason.ZERO_TOTAL_VALUE, "Allocation ratios are undefined at zero total value")

    cash, invested = analysis.cash_balance, analysis.invested_market_value
    if not _valid_value(cash, total) or not _valid_value(invested, total) \
            or _add(cash, invested) != total:
        return unknown(PolicyReason.INVALID_EXPOSURE, "Cash and invested value do not reconcile to total")
    values = {bucket: ZERO for bucket in ALLOCATION_BUCKETS}
    values[AllocationBucket.CASH] = cash
    stock_value = etf_value = position_total = ZERO
    sector_values: dict[str, Decimal] = {}
    unclassified_stock_value = ZERO
    unclassified_etfs: list[str] = []
    for item in positions:
        amount = item.market_value
        if not _valid_value(amount, total) or not _valid_ratio(item.weight) \
                or item.weight != _div(amount, total):
            return unknown(PolicyReason.INVALID_EXPOSURE,
                           "Position amount or weight is missing or inconsistent")
        position_total = _add(position_total, amount)
        if item.asset_type is AssetType.STOCK:
            stock_value = _add(stock_value, amount)
            values[AllocationBucket.INDIVIDUAL_STOCKS] = _add(
                values[AllocationBucket.INDIVIDUAL_STOCKS], amount)
            if item.sector is None:
                unclassified_stock_value = _add(unclassified_stock_value, amount)
            elif isinstance(item.sector, str) and item.sector.strip():
                sector_values[item.sector] = _add(sector_values.get(item.sector, ZERO), amount)
            else:
                return unknown(PolicyReason.INVALID_ANALYSIS, "Stock sector type is invalid")
        else:
            etf_value = _add(etf_value, amount)
            group = groups.get(item.asset_id)
            if group is None:
                unclassified_etfs.append(item.asset_id)
            else:
                bucket = AllocationBucket.CORE_ETF if group is ETFGroup.CORE else AllocationBucket.GROWTH_ETF
                values[bucket] = _add(values[bucket], amount)
    if position_total != invested or not _valid_value(analysis.etf_market_value, total) \
            or analysis.etf_market_value != etf_value:
        return unknown(PolicyReason.INVALID_EXPOSURE, "Position and ETF amounts do not reconcile")
    if not all(_valid_ratio(ratio) for ratio in (
            analysis.cash_ratio, analysis.stock_exposure, analysis.etf_exposure)) \
            or analysis.cash_ratio != _div(cash, total) \
            or analysis.stock_exposure != _div(stock_value, total) \
            or analysis.etf_exposure != _div(etf_value, total):
        return unknown(PolicyReason.INVALID_EXPOSURE, "Analysis exposure ratios do not reconcile")
    if not _valid_value(analysis.sector_classified_market_value, total) \
            or not _valid_value(analysis.unclassified_stock_market_value, total) \
            or _add(analysis.sector_classified_market_value,
                    analysis.unclassified_stock_market_value) != stock_value \
            or analysis.unclassified_stock_market_value != unclassified_stock_value \
            or not isinstance(analysis.direct_sector_exposure, tuple):
        return unknown(PolicyReason.INVALID_EXPOSURE, "Direct stock sector amounts do not reconcile")
    sector_total = ZERO
    seen_sectors: set[str] = set()
    for sector in analysis.direct_sector_exposure:
        if not isinstance(sector, DirectSectorExposure) or not isinstance(sector.sector, str) \
                or not sector.sector.strip() or sector.sector in seen_sectors \
                or not _valid_value(sector.market_value, total) \
                or not _valid_ratio(sector.account_weight) \
                or sector.account_weight != _div(sector.market_value, total):
            return unknown(PolicyReason.INVALID_EXPOSURE, "Direct sector evidence is invalid")
        seen_sectors.add(sector.sector)
        sector_total = _add(sector_total, sector.market_value)
    if sector_total != analysis.sector_classified_market_value:
        return unknown(PolicyReason.INVALID_EXPOSURE, "Direct sector values do not reconcile")
    if {item.sector: item.market_value for item in analysis.direct_sector_exposure} != sector_values:
        return unknown(PolicyReason.INVALID_EXPOSURE, "Direct sector classifications do not reconcile")
    if not unclassified_etfs and _add(_add(values[AllocationBucket.CORE_ETF],
            values[AllocationBucket.GROWTH_ETF]), _add(stock_value, cash)) != total:
        return unknown(PolicyReason.INVALID_EXPOSURE, "Allocation bucket amounts do not reconcile")

    results: list[AllocationEvaluation] = []
    for bucket in ALLOCATION_BUCKETS:
        band = bands[bucket]
        if unclassified_etfs and bucket in (AllocationBucket.CORE_ETF, AllocationBucket.GROWTH_ETF):
            results.append(AllocationEvaluation(
                bucket, None, None, band.target_ratio, band.min_ratio, band.max_ratio, None,
                PolicyStatus.UNKNOWN, PolicyReason.UNCLASSIFIED_ETF,
                "ETF asset_id lacks Core/Growth classification: " + ", ".join(sorted(unclassified_etfs))))
            continue
        value = values[bucket]
        if value < _mul(band.min_ratio, total):
            status, code, reason = PolicyStatus.BREACH, PolicyReason.BELOW_MINIMUM, "Below inclusive allocation minimum"
        elif value > _mul(band.max_ratio, total):
            status, code, reason = PolicyStatus.BREACH, PolicyReason.ABOVE_MAXIMUM, "Above inclusive allocation maximum"
        else:
            status, code, reason = PolicyStatus.PASS, PolicyReason.WITHIN_RANGE, "Within inclusive allocation range"
        results.append(AllocationEvaluation(
            bucket, value, _div(value, total), band.target_ratio, band.min_ratio,
            band.max_ratio, _div(_sub(value, _mul(band.target_ratio, total)), total),
            status, code, reason))
    return tuple(results)


class PortfolioPolicyEngine:
    """Evaluate supplied facts only; no repository, provider, or clock dependency."""

    def __init__(self, config: PortfolioPolicyConfig) -> None:
        if not isinstance(config, PortfolioPolicyConfig):
            raise TypeError("config must be PortfolioPolicyConfig")
        self._config = config

    def evaluate(self, analysis: PortfolioAnalysis, *,
                 etf_classifications: Sequence[ETFClassification] = ()) -> PortfolioPolicyReport:
        if not isinstance(analysis, PortfolioAnalysis):
            raise TypeError("analysis must be PortfolioAnalysis")
        config = self._config
        total = analysis.total_value_usd
        positions = analysis.positions if isinstance(analysis.positions, tuple) else ()
        valid_positions = tuple(item for item in positions if isinstance(item, PositionAnalysis))
        position_shape_ok = (isinstance(analysis.positions, tuple)
                             and len(valid_positions) == len(positions)
                             and all(isinstance(item.asset_type, AssetType)
                                     and isinstance(item.asset_id, str) and item.asset_id.strip()
                                     for item in valid_positions))
        duplicate_positions = (position_shape_ok and
                               len({item.asset_id for item in valid_positions}) != len(valid_positions))
        groups = _classified_etfs(valid_positions, etf_classifications)
        reliable = (analysis.all_quotes_fresh is True and analysis.fx_fresh is True
                    and analysis.currency is Currency.USD
                    and position_shape_ok and not duplicate_positions
                    and isinstance(total, Decimal) and total.is_finite() and total >= ZERO)
        total = total if isinstance(total, Decimal) and total.is_finite() and total >= ZERO else ZERO
        stock_limits = ConcentrationThresholds(config.individual_stock_warn_ratio,
                                              config.individual_stock_breach_ratio)
        total_stock_limits = ConcentrationThresholds(None, config.individual_stocks_total_max_ratio)
        sector_limits = ConcentrationThresholds(config.direct_sector_warn_ratio,
                                                config.direct_sector_breach_ratio)
        cash_limits = CashRangeThresholds(config.min_cash_ratio, config.max_cash_ratio)
        evaluations: list[PolicyEvaluation] = []
        not_applicable: list[PolicyKind] = []

        stocks = sorted((item for item in valid_positions if item.asset_type is AssetType.STOCK),
                        key=lambda item: item.asset_id)
        if stocks:
            for position in stocks:
                evaluations.append(_concentration(
                    PolicyKind.INDIVIDUAL_STOCK, PolicyTarget(PolicyTargetKind.ASSET, position.asset_id),
                    position.market_value, position.weight, total, stock_limits, reliable,
                ))
        else:
            not_applicable.append(PolicyKind.INDIVIDUAL_STOCK)

        # stock_exposure is the Phase 3 ratio/availability signal. Sum the exact
        # STOCK amounts (including unclassified stocks) instead of multiplying a
        # rounded ratio back into money or including ETF holdings.
        stock_value: Decimal | None = ZERO
        for position in stocks:
            if not _valid_value(position.market_value, total):
                stock_value = None
                break
            stock_value = _add(stock_value, position.market_value)
        evaluations.append(_concentration(
            PolicyKind.TOTAL_STOCK_EXPOSURE,
            PolicyTarget(PolicyTargetKind.PORTFOLIO, analysis.account_id),
            stock_value, analysis.stock_exposure, total, total_stock_limits, reliable,
        ))

        sectors = analysis.direct_sector_exposure
        sector_shape_ok = (isinstance(sectors, tuple)
                           and all(isinstance(item, DirectSectorExposure)
                                   and isinstance(item.sector, str) and item.sector.strip()
                                   for item in sectors))
        if sector_shape_ok:
            sector_shape_ok = len({item.sector for item in sectors}) == len(sectors)
        if not sector_shape_ok:
            evaluations.append(_unknown(
                PolicyKind.DIRECT_SECTOR, PolicyTarget(PolicyTargetKind.DIRECT_SECTOR),
                None, sector_limits, PolicyReason.INVALID_ANALYSIS,
                "Direct sector structure is invalid"))
        elif sectors:
            for sector in sorted(sectors, key=lambda item: item.sector):
                evaluations.append(_concentration(
                    PolicyKind.DIRECT_SECTOR,
                    PolicyTarget(PolicyTargetKind.DIRECT_SECTOR, sector.sector),
                    sector.market_value, sector.account_weight, total, sector_limits, reliable,
                ))
        unclassified = analysis.unclassified_stock_market_value
        if not isinstance(unclassified, Decimal) or not unclassified.is_finite() \
                or unclassified != ZERO:
            unknown_ratio = (_div(unclassified, total)
                             if reliable and total > ZERO and _valid_value(unclassified, total) else None)
            if not reliable:
                code, reason = (PolicyReason.UNRELIABLE_ANALYSIS,
                                "Analysis evidence is unsuitable for policy evaluation")
            elif not _valid_value(unclassified, total):
                code, reason = (PolicyReason.INVALID_EXPOSURE,
                                "Unclassified stock exposure is invalid")
            else:
                code, reason = (PolicyReason.UNCLASSIFIED_STOCK,
                                "Direct stock sector is unclassified; no sector limit can be applied")
            evaluations.append(_unknown(
                PolicyKind.DIRECT_SECTOR, PolicyTarget(PolicyTargetKind.UNCLASSIFIED_STOCK),
                unknown_ratio, sector_limits, code, reason,
            ))
        elif sector_shape_ok and not sectors:
            not_applicable.append(PolicyKind.DIRECT_SECTOR)

        cash_actual = analysis.cash_ratio if _valid_ratio(analysis.cash_ratio) else None
        cash_target = PolicyTarget(PolicyTargetKind.PORTFOLIO, analysis.account_id)
        if not reliable:
            evaluations.append(_unknown(PolicyKind.CASH_RATIO, cash_target, None, cash_limits,
                                        PolicyReason.UNRELIABLE_ANALYSIS,
                                        "Analysis evidence is unsuitable for policy evaluation"))
        elif total == ZERO:
            evaluations.append(_unknown(PolicyKind.CASH_RATIO, cash_target, None, cash_limits,
                                        PolicyReason.ZERO_TOTAL_VALUE,
                                        "Cash ratio is undefined at zero total value"))
        elif not _valid_value(analysis.cash_balance, total) or cash_actual is None:
            evaluations.append(_unknown(PolicyKind.CASH_RATIO, cash_target, None, cash_limits,
                                        PolicyReason.INVALID_EXPOSURE,
                                        "Required cash exposure is missing or invalid"))
        elif analysis.cash_balance < _mul(config.min_cash_ratio, total):
            evaluations.append(PolicyEvaluation(PolicyKind.CASH_RATIO, cash_target,
                PolicyStatus.BREACH, _div(analysis.cash_balance, total), cash_limits, PolicyReason.BELOW_MINIMUM,
                "Below minimum cash ratio"))
        elif analysis.cash_balance > _mul(config.max_cash_ratio, total):
            evaluations.append(PolicyEvaluation(PolicyKind.CASH_RATIO, cash_target,
                PolicyStatus.BREACH, _div(analysis.cash_balance, total), cash_limits, PolicyReason.ABOVE_MAXIMUM,
                "Above maximum cash ratio"))
        else:
            evaluations.append(PolicyEvaluation(PolicyKind.CASH_RATIO, cash_target,
                PolicyStatus.PASS, _div(analysis.cash_balance, total), cash_limits, PolicyReason.WITHIN_RANGE,
                "Within cash ratio range"))

        return PortfolioPolicyReport(analysis.account_id, analysis.evaluated_at,
                                     config.policy_version, tuple(evaluations),
                                     tuple(not_applicable),
                                     _allocation_evaluations(analysis, config, valid_positions, groups))
