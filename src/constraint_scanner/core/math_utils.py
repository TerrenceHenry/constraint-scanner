from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from constraint_scanner.core.constants import DECIMAL_ZERO


def clamp_decimal(value: Decimal, minimum: Decimal, maximum: Decimal) -> Decimal:
    """Clamp a decimal between inclusive bounds."""

    return max(minimum, min(value, maximum))


def quantize_decimal(value: Decimal, places: str = "0.0001") -> Decimal:
    """Quantize a decimal deterministically using half-up rounding."""

    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def midpoint_diagnostic(best_bid: Decimal | None, best_ask: Decimal | None) -> Decimal | None:
    """Return a diagnostic midpoint. This value is never executable."""

    if best_bid is None or best_ask is None:
        return None
    return (best_bid + best_ask) / Decimal("2")


def safe_decimal_ratio(numerator: Decimal, denominator: Decimal) -> Decimal:
    """Return a ratio or zero when the denominator is zero."""

    if denominator == DECIMAL_ZERO:
        return DECIMAL_ZERO
    return numerator / denominator
