from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from constraint_scanner.core.constants import DECIMAL_ZERO
from constraint_scanner.core.types import ExposureState
from constraint_scanner.db.models import Opportunity

REPORTING_BASIS = {
    "unresolved_notional_usd": "sum(open opportunity pricing.gross_buy_cost)",
    "gross_exposure_usd": "sum(open opportunity pricing.gross_buy_cost)",
    "net_exposure_usd": "sum(open opportunity pricing.net_cost)",
    "group_exposure_usd": "sum(open opportunity pricing.gross_buy_cost) grouped by group_id",
    "market_exposure_usd": (
        "sum(open opportunity pricing.legs[*].total_notional) grouped by market_id "
        "when leg details exist; otherwise fallback to pricing.gross_buy_cost on opportunity.market_id"
    ),
    "token_exposure_usd": (
        "sum(open opportunity pricing.legs[*].total_notional) grouped by token_id "
        "when leg details exist; otherwise fallback to pricing.gross_buy_cost on opportunity.token_id"
    ),
}


def build_exposure_state(
    opportunities: Iterable[Opportunity],
    *,
    open_order_count: int = 0,
) -> ExposureState:
    """Build a deterministic exposure snapshot from open opportunities."""

    unresolved_notional_usd = DECIMAL_ZERO
    gross_exposure_usd = DECIMAL_ZERO
    net_exposure_usd = DECIMAL_ZERO
    open_basket_count = 0
    market_exposure_usd: dict[int, Decimal] = {}
    group_exposure_usd: dict[int, Decimal] = {}
    token_exposure_usd: dict[int, Decimal] = {}

    for opportunity in opportunities:
        if opportunity.status != "open":
            continue

        open_basket_count += 1
        unresolved_notional = _pricing_decimal(opportunity, "gross_buy_cost")
        net_cost = _pricing_decimal(opportunity, "net_cost")
        unresolved_notional_usd += unresolved_notional
        gross_exposure_usd += unresolved_notional
        net_exposure_usd += net_cost

        if opportunity.group_id is not None:
            group_exposure_usd[opportunity.group_id] = (
                group_exposure_usd.get(opportunity.group_id, DECIMAL_ZERO) + unresolved_notional
            )

        pricing_legs = _pricing_legs(opportunity)
        if pricing_legs:
            for leg in pricing_legs:
                leg_notional = _leg_decimal(leg, "total_notional")
                market_id = leg.get("market_id")
                token_id = leg.get("token_id")
                if isinstance(market_id, int):
                    market_exposure_usd[market_id] = market_exposure_usd.get(market_id, DECIMAL_ZERO) + leg_notional
                if isinstance(token_id, int):
                    token_exposure_usd[token_id] = token_exposure_usd.get(token_id, DECIMAL_ZERO) + leg_notional
            continue

        if opportunity.market_id is not None:
            market_exposure_usd[opportunity.market_id] = (
                market_exposure_usd.get(opportunity.market_id, DECIMAL_ZERO) + unresolved_notional
            )
        if opportunity.token_id is not None:
            token_exposure_usd[opportunity.token_id] = (
                token_exposure_usd.get(opportunity.token_id, DECIMAL_ZERO) + unresolved_notional
            )

    return ExposureState(
        unresolved_notional_usd=unresolved_notional_usd,
        open_basket_count=open_basket_count,
        gross_exposure_usd=gross_exposure_usd,
        net_exposure_usd=net_exposure_usd,
        open_order_count=open_order_count,
        market_exposure_usd=market_exposure_usd,
        group_exposure_usd=group_exposure_usd,
        token_exposure_usd=token_exposure_usd,
        reporting_basis=dict(REPORTING_BASIS),
    )


def opportunity_unresolved_notional_usd(opportunity: Opportunity) -> Decimal:
    """Return the conservative unresolved notional for one opportunity."""

    return _pricing_decimal(opportunity, "gross_buy_cost")


def _pricing_decimal(opportunity: Opportunity, field_name: str) -> Decimal:
    details = opportunity.details or {}
    pricing = details.get("pricing")
    if not isinstance(pricing, dict):
        return DECIMAL_ZERO
    value = pricing.get(field_name)
    if value is None:
        return DECIMAL_ZERO
    return Decimal(str(value))


def _pricing_legs(opportunity: Opportunity) -> list[dict[str, object]]:
    details = opportunity.details or {}
    pricing = details.get("pricing")
    if not isinstance(pricing, dict):
        return []
    raw_legs = pricing.get("legs")
    if not isinstance(raw_legs, list):
        return []
    return [leg for leg in raw_legs if isinstance(leg, dict)]


def _leg_decimal(leg: dict[str, object], field_name: str) -> Decimal:
    value = leg.get(field_name)
    if value is None:
        return DECIMAL_ZERO
    return Decimal(str(value))
