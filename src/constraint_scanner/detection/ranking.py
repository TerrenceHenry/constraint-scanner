from __future__ import annotations

from decimal import Decimal

from constraint_scanner.core.constants import DECIMAL_ZERO


def compute_ranking_score(
    *,
    max_executable_notional: Decimal,
    net_edge_pct: Decimal,
    confidence_score: Decimal,
) -> Decimal:
    """Compute the transparent pre-simulation ranking score for an opportunity."""

    if max_executable_notional <= DECIMAL_ZERO:
        return DECIMAL_ZERO
    if net_edge_pct <= DECIMAL_ZERO:
        return DECIMAL_ZERO
    if confidence_score <= DECIMAL_ZERO:
        return DECIMAL_ZERO
    return max_executable_notional * net_edge_pct * confidence_score
