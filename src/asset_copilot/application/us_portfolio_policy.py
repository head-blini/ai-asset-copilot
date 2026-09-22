"""Pure current-state policy evaluation over a completed PortfolioAnalysis."""

from decimal import Decimal

from asset_copilot.application.us_portfolio_analytics import PortfolioAnalysis
from asset_copilot.domain.models import Currency
from asset_copilot.domain.policy import (
    CashRangeThresholds, ConcentrationThresholds, PolicyEvaluation, PolicyKind,
    PolicyReason, PolicyStatus, PolicyTarget, PolicyTargetKind, PortfolioPolicyConfig,
    PortfolioPolicyReport,
)
from asset_copilot.portfolio.calculator import _div, _mul


ZERO = Decimal("0")
ONE = Decimal("1")


def _valid_ratio(value: Decimal | None) -> bool:
    return isinstance(value, Decimal) and value.is_finite() and ZERO <= value <= ONE


def _valid_value(value: Decimal, total: Decimal) -> bool:
    return isinstance(value, Decimal) and value.is_finite() and ZERO <= value <= total


def _unknown(policy: PolicyKind, target: PolicyTarget, actual: Decimal | None,
             thresholds: ConcentrationThresholds | CashRangeThresholds,
             reason_code: PolicyReason, reason: str) -> PolicyEvaluation:
    return PolicyEvaluation(policy, target, PolicyStatus.UNKNOWN, actual, thresholds,
                            reason_code, reason)


def _concentration(policy: PolicyKind, target: PolicyTarget, value: Decimal,
                   actual: Decimal | None, total: Decimal,
                   thresholds: ConcentrationThresholds, reliable: bool) -> PolicyEvaluation:
    if not reliable:
        return _unknown(policy, target, None, thresholds, PolicyReason.UNRELIABLE_ANALYSIS,
                        "Quote or FX evidence is unsuitable for policy evaluation")
    if total == ZERO:
        return _unknown(policy, target, None, thresholds, PolicyReason.ZERO_TOTAL_VALUE,
                        "Portfolio exposure is undefined at zero total value")
    if not _valid_value(value, total) or not _valid_ratio(actual):
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


class PortfolioPolicyEngine:
    """Evaluate supplied facts only; no repository, provider, or clock dependency."""

    def __init__(self, config: PortfolioPolicyConfig) -> None:
        if not isinstance(config, PortfolioPolicyConfig):
            raise TypeError("config must be PortfolioPolicyConfig")
        self._config = config

    def evaluate(self, analysis: PortfolioAnalysis) -> PortfolioPolicyReport:
        if not isinstance(analysis, PortfolioAnalysis):
            raise TypeError("analysis must be PortfolioAnalysis")
        config = self._config
        total = analysis.total_value_usd
        reliable = (analysis.all_quotes_fresh is True and analysis.fx_fresh is True
                    and analysis.currency is Currency.USD
                    and isinstance(total, Decimal) and total.is_finite() and total >= ZERO)
        total = total if isinstance(total, Decimal) and total.is_finite() and total >= ZERO else ZERO
        asset_limits = ConcentrationThresholds(config.single_asset_warn_ratio,
                                               config.single_asset_breach_ratio)
        sector_limits = ConcentrationThresholds(config.direct_sector_warn_ratio,
                                                config.direct_sector_breach_ratio)
        cash_limits = CashRangeThresholds(config.min_cash_ratio, config.max_cash_ratio)
        evaluations: list[PolicyEvaluation] = []
        not_applicable: list[PolicyKind] = []

        if analysis.positions:
            for position in sorted(analysis.positions, key=lambda item: item.asset_id):
                evaluations.append(_concentration(
                    PolicyKind.SINGLE_ASSET, PolicyTarget(PolicyTargetKind.ASSET, position.asset_id),
                    position.market_value, position.weight, total, asset_limits, reliable,
                ))
        else:
            not_applicable.append(PolicyKind.SINGLE_ASSET)

        if analysis.direct_sector_exposure:
            for sector in sorted(analysis.direct_sector_exposure, key=lambda item: item.sector):
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
                                "Quote or FX evidence is unsuitable for policy evaluation")
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
        elif not analysis.direct_sector_exposure:
            not_applicable.append(PolicyKind.DIRECT_SECTOR)

        cash_actual = analysis.cash_ratio if _valid_ratio(analysis.cash_ratio) else None
        cash_target = PolicyTarget(PolicyTargetKind.PORTFOLIO, analysis.account_id)
        if not reliable:
            evaluations.append(_unknown(PolicyKind.CASH_RATIO, cash_target, None, cash_limits,
                                        PolicyReason.UNRELIABLE_ANALYSIS,
                                        "Quote or FX evidence is unsuitable for policy evaluation"))
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
                                     tuple(not_applicable))
