from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_DOWN
from typing import Any

from constraint_scanner.core.clock import ensure_utc
from constraint_scanner.core.constants import DECIMAL_ZERO
from constraint_scanner.core.enums import TradingMode
from constraint_scanner.core.exceptions import RiskRejectedError, TradingValidationError
from constraint_scanner.core.ids import make_prefixed_id
from constraint_scanner.core.types import OrderRequest, RiskDecision
from constraint_scanner.db.models import Opportunity

PRICE_QUANTUM = Decimal("0.00000001")
SIZE_QUANTUM = Decimal("0.00000001")
MIN_MEANINGFUL_LEG_NOTIONAL_USD = Decimal("0.01")
MIN_MEANINGFUL_BASKET_NOTIONAL_USD = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class OrderBuildResult:
    """Deterministic per-leg order intents built from one approved opportunity."""

    requests: tuple[OrderRequest, ...]
    simulation_run_id: str
    gross_buy_cost: Decimal
    approved_notional_usd: Decimal
    scale_factor: Decimal
    rounded_total_notional_usd: Decimal


def build_order_requests(
    *,
    opportunity: Opportunity,
    risk_decision: RiskDecision,
    trading_mode: TradingMode,
    tif: str,
    submitted_at: datetime,
) -> OrderBuildResult:
    """Build auditable per-leg order intents from approved opportunity pricing data."""

    if not risk_decision.approved or risk_decision.reason_code != "approved":
        raise RiskRejectedError("trader requires an approved risk decision")

    details = opportunity.details or {}
    pricing = details.get("pricing")
    if not isinstance(pricing, dict):
        raise TradingValidationError("opportunity details.pricing is required to build order requests")

    raw_legs = pricing.get("legs")
    if not isinstance(raw_legs, list) or not raw_legs:
        raise TradingValidationError("opportunity details.pricing.legs must contain at least one executable leg")

    simulation_run_id = risk_decision.metadata.get("simulation_run_id")
    if not isinstance(simulation_run_id, str) or not simulation_run_id:
        raise TradingValidationError("approved risk decision must include simulation_run_id metadata")

    active_submitted_at = ensure_utc(submitted_at)
    gross_buy_cost = _decimal_value(pricing.get("gross_buy_cost"), field_name="gross_buy_cost")
    if gross_buy_cost <= DECIMAL_ZERO:
        gross_buy_cost = sum(
            (_decimal_value(leg.get("total_notional"), field_name="legs.total_notional") for leg in raw_legs if isinstance(leg, dict)),
            start=DECIMAL_ZERO,
        )
    if gross_buy_cost <= DECIMAL_ZERO:
        raise TradingValidationError("opportunity gross buy cost must be positive")

    approved_notional = risk_decision.max_size_usd
    if approved_notional is None:
        raise TradingValidationError("approved risk decision must include a positive max_size_usd")
    approved_notional = min(approved_notional, gross_buy_cost)
    if approved_notional <= DECIMAL_ZERO:
        raise TradingValidationError("approved notional must be positive")

    scale_factor = min(Decimal("1"), approved_notional / gross_buy_cost)
    requests: list[OrderRequest] = []
    rounded_total_notional_usd = DECIMAL_ZERO

    for index, raw_leg in enumerate(raw_legs, start=1):
        if not isinstance(raw_leg, dict):
            raise TradingValidationError("opportunity pricing legs must be dictionaries")

        market_id = _int_value(raw_leg.get("market_id"), field_name="legs.market_id")
        token_id = _int_value(raw_leg.get("token_id"), field_name="legs.token_id")
        side = _str_value(raw_leg.get("side"), field_name="legs.side")
        price = _optional_decimal(raw_leg.get("weighted_average_price"))
        if price is None:
            raise TradingValidationError("opportunity legs require weighted_average_price for limit-order intent")

        requested_quantity = _optional_decimal(raw_leg.get("requested_quantity"))
        if requested_quantity is None:
            requested_quantity = _optional_decimal(raw_leg.get("filled_quantity"))
        if requested_quantity is None or requested_quantity <= DECIMAL_ZERO:
            raise TradingValidationError("opportunity legs require a positive requested or filled quantity")

        scaled_quantity = (requested_quantity * scale_factor).quantize(SIZE_QUANTUM, rounding=ROUND_DOWN)
        if scaled_quantity <= DECIMAL_ZERO:
            raise TradingValidationError("approved notional scales order quantities below executable precision")

        normalized_price = price.quantize(PRICE_QUANTUM, rounding=ROUND_DOWN)
        rounded_leg_notional = normalized_price * scaled_quantity
        if rounded_leg_notional < MIN_MEANINGFUL_LEG_NOTIONAL_USD:
            raise TradingValidationError("approved notional scales an order leg below the minimum meaningful notional")
        rounded_total_notional_usd += rounded_leg_notional
        client_order_id = make_prefixed_id(
            "order",
            trading_mode.value,
            opportunity.id,
            simulation_run_id,
            token_id,
            index,
            active_submitted_at.isoformat(),
        )
        requests.append(
            OrderRequest(
                client_order_id=client_order_id,
                market_id=market_id,
                token_id=token_id,
                side=side,
                price=normalized_price,
                quantity=scaled_quantity,
                trading_mode=trading_mode,
                time_in_force=tif,
                metadata={
                    "opportunity_id": opportunity.id,
                    "simulation_run_id": simulation_run_id,
                    "risk_reason_code": risk_decision.reason_code,
                    "pricing_source": "opportunity.details.pricing.legs",
                    "role": raw_leg.get("role"),
                    "requested_quantity": str(requested_quantity),
                    "scaled_quantity": str(scaled_quantity),
                    "detector_filled_quantity": (
                        str(_optional_decimal(raw_leg.get("filled_quantity")))
                        if _optional_decimal(raw_leg.get("filled_quantity")) is not None
                        else None
                    ),
                    "source_weighted_average_price": str(price),
                    "source_total_notional": raw_leg.get("total_notional"),
                    "rounded_leg_notional_usd": str(rounded_leg_notional),
                    "original_basket_gross_buy_cost_usd": str(gross_buy_cost),
                    "consumed_depth": list(raw_leg.get("consumed_depth", []))
                    if isinstance(raw_leg.get("consumed_depth"), list)
                    else [],
                    "approved_notional_usd": str(approved_notional),
                    "scale_factor": str(scale_factor),
                },
            )
        )

    if rounded_total_notional_usd < MIN_MEANINGFUL_BASKET_NOTIONAL_USD:
        raise TradingValidationError("approved notional scales the basket below the minimum meaningful total notional")

    return OrderBuildResult(
        requests=tuple(requests),
        simulation_run_id=simulation_run_id,
        gross_buy_cost=gross_buy_cost,
        approved_notional_usd=approved_notional,
        scale_factor=scale_factor,
        rounded_total_notional_usd=rounded_total_notional_usd,
    )


def _decimal_value(value: object, *, field_name: str) -> Decimal:
    try:
        decimal_value = Decimal(str(value))
    except Exception as exc:  # pragma: no cover - defensive type normalization
        raise TradingValidationError(f"{field_name} must be Decimal-compatible") from exc
    return decimal_value


def _optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _int_value(value: object, *, field_name: str) -> int:
    if not isinstance(value, int):
        raise TradingValidationError(f"{field_name} must be an integer")
    return value


def _str_value(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise TradingValidationError(f"{field_name} must be a non-empty string")
    return value
