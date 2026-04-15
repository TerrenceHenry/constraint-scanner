from __future__ import annotations

from decimal import Decimal
from typing import Any

from constraint_scanner.core.types import RiskDecision


def approve(
    *,
    reason: str = "risk policy approved",
    max_size_usd: Decimal | None = None,
    metadata: dict[str, Any] | None = None,
) -> RiskDecision:
    """Build a stable approval decision."""

    return RiskDecision(
        approved=True,
        reason_code="approved",
        reason=reason,
        max_size_usd=max_size_usd,
        metadata=dict(metadata or {}),
    )


def reject(
    *,
    reason_code: str,
    reason: str,
    metadata: dict[str, Any] | None = None,
) -> RiskDecision:
    """Build a stable rejection decision."""

    return RiskDecision(
        approved=False,
        reason_code=reason_code,
        reason=reason,
        max_size_usd=None,
        metadata=dict(metadata or {}),
    )
