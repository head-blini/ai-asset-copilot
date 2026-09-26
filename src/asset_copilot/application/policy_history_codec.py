"""Closed, lossless JSON codec for policy evidence. Never imports types from stored data."""

from dataclasses import fields, is_dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
import json

from asset_copilot.application.us_portfolio_analytics import (
    DirectSectorExposure, PortfolioAnalysis, PositionAnalysis,
)
from asset_copilot.domain.models import AssetType, Currency
from asset_copilot.domain.policy import (
    AllocationBand, AllocationBucket, AllocationEvaluation, CashRangeThresholds,
    ConcentrationThresholds, ETFClassification, ETFGroup, PolicyEvaluation,
    PolicyKind, PolicyReason, PolicyStatus, PolicyTarget, PolicyTargetKind,
    PortfolioPolicyConfig, PortfolioPolicyReport,
)

_CLASSES = {cls.__name__: cls for cls in (
    DirectSectorExposure, PortfolioAnalysis, PositionAnalysis, AllocationBand,
    AllocationEvaluation, CashRangeThresholds, ConcentrationThresholds,
    ETFClassification, PolicyEvaluation, PolicyTarget, PortfolioPolicyConfig,
    PortfolioPolicyReport,
)}
_ENUMS = {cls.__name__: cls for cls in (
    AssetType, Currency, AllocationBucket, ETFGroup, PolicyKind, PolicyReason,
    PolicyStatus, PolicyTargetKind,
)}


def _encode(value):
    if value is None or type(value) in (str, int, bool):
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("non-finite Decimal in policy evidence")
        return {"@": "decimal", "value": str(value)}
    if isinstance(value, datetime):
        if value.utcoffset() is None:
            raise ValueError("naive datetime in policy evidence")
        return {"@": "datetime", "value": value.isoformat()}
    if isinstance(value, timedelta):
        return {"@": "timedelta", "days": value.days, "seconds": value.seconds,
                "microseconds": value.microseconds}
    if isinstance(value, Enum) and type(value).__name__ in _ENUMS:
        return {"@": "enum", "class": type(value).__name__, "value": value.value}
    if isinstance(value, tuple):
        return {"@": "tuple", "items": [_encode(item) for item in value]}
    if isinstance(value, list):
        return {"@": "list", "items": [_encode(item) for item in value]}
    if is_dataclass(value) and type(value).__name__ in _CLASSES:
        return {"@": "model", "class": type(value).__name__,
                "fields": {field.name: _encode(getattr(value, field.name)) for field in fields(value)}}
    raise TypeError(f"unsupported policy evidence type: {type(value).__name__}")


def _decode(value):
    if value is None or type(value) in (str, int, bool):
        return value
    if not isinstance(value, dict):
        raise ValueError("invalid policy evidence JSON")
    tag = value.get("@")
    if tag == "decimal" and set(value) == {"@", "value"}:
        result = Decimal(value["value"])
        if not result.is_finite():
            raise ValueError("non-finite Decimal in policy evidence")
        return result
    if tag == "datetime" and set(value) == {"@", "value"}:
        result = datetime.fromisoformat(value["value"])
        if result.utcoffset() is None:
            raise ValueError("naive datetime in policy evidence")
        return result
    if tag == "timedelta" and set(value) == {"@", "days", "seconds", "microseconds"}:
        return timedelta(days=value["days"], seconds=value["seconds"],
                         microseconds=value["microseconds"])
    if tag == "enum" and set(value) == {"@", "class", "value"}:
        return _ENUMS[value["class"]](value["value"])
    if tag in ("tuple", "list") and set(value) == {"@", "items"}:
        items = [_decode(item) for item in value["items"]]
        return tuple(items) if tag == "tuple" else items
    if tag == "model" and set(value) == {"@", "class", "fields"}:
        cls = _CLASSES[value["class"]]
        expected = {field.name for field in fields(cls)}
        if set(value["fields"]) != expected:
            raise ValueError("policy evidence model fields differ")
        return cls(**{key: _decode(item) for key, item in value["fields"].items()})
    raise ValueError("invalid policy evidence tag")


def dumps(value) -> str:
    return json.dumps(_encode(value), sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def loads(raw: str):
    return _decode(json.loads(raw))
