from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from constraint_scanner.constraints.template_registry import get_template_registry
from constraint_scanner.constraints.types import TemplateContext
from constraint_scanner.core.constants import DECIMAL_ZERO
from constraint_scanner.core.enums import OpportunityState, StrategyType, TemplateType
from constraint_scanner.core.types import BookSnapshot, OpportunityCandidate, OpportunityLeg
from constraint_scanner.detection.detector_base import DetectionOutcome, DetectorBase, RankedFinding
from constraint_scanner.detection.persistence import build_persistence_key
from constraint_scanner.detection.ranking import compute_ranking_score
from constraint_scanner.simulation.executable_pricing import (
    compute_basket_cost,
    compute_max_executable_size_for_basket,
    compute_net_edge,
)


class IntraMarketDetector(DetectorBase):
    """Detect conservative buy-basket arbitrage for exhaustive templates."""

    def __init__(self, *, enable_sell_side: bool = False) -> None:
        self._enable_sell_side = enable_sell_side
        self._registry = get_template_registry()

    def detect(
        self,
        *,
        context: TemplateContext,
        books: dict[int, BookSnapshot],
        confidence_score: Decimal,
        detected_at: datetime,
    ) -> DetectionOutcome:
        if context.template_type not in {
            TemplateType.BINARY_COMPLEMENT,
            TemplateType.EXACT_ONE_OF_N,
            TemplateType.ONE_VS_FIELD,
        }:
            return DetectionOutcome(finding=None, rejection_reason="template not supported for intra-market detection")

        template = self._registry.get(context.template_type)
        validation = template.validate(context)
        if not validation.valid:
            return DetectionOutcome(finding=None, rejection_reason="; ".join(validation.issues))

        if self._enable_sell_side:
            sell_side_scaffold = {"enabled": True}
        else:
            sell_side_scaffold = {"enabled": False, "reason": "sell-side arbitrage disabled by config in v1"}

        legs = tuple(
            OpportunityLeg(
                market_id=member.market_id,
                token_id=member.token_id,
                side="buy",
                price=DECIMAL_ZERO,
                quantity=Decimal("1"),
                note=member.role,
            )
            for member in context.members
        )
        requested_quantities = {
            leg.token_id: leg.quantity
            for leg in legs
        }
        executable_size = compute_max_executable_size_for_basket(books, legs)
        if executable_size.max_basket_quantity <= DECIMAL_ZERO:
            return DetectionOutcome(finding=None, rejection_reason="no executable buy-side depth")

        basket_cost = compute_basket_cost(books, legs, executable_size.max_basket_quantity)
        if any(not fill.fully_filled for fill in basket_cost.fills_by_token.values()):
            return DetectionOutcome(finding=None, rejection_reason="insufficient depth for full basket fill")

        payout_per_basket = Decimal("1")
        net_edge_usd = compute_net_edge(
            payout_per_basket=payout_per_basket,
            basket_cost=basket_cost,
        )
        if net_edge_usd <= DECIMAL_ZERO:
            return DetectionOutcome(finding=None, rejection_reason="basket cost is not below guaranteed payout")

        gross_notional = basket_cost.gross_buy_cost
        if gross_notional <= DECIMAL_ZERO:
            return DetectionOutcome(finding=None, rejection_reason="basket notional is zero")

        net_edge_pct = net_edge_usd / gross_notional
        ranking_score = compute_ranking_score(
            max_executable_notional=gross_notional,
            net_edge_pct=net_edge_pct,
            confidence_score=confidence_score,
        )

        priced_legs = tuple(
            OpportunityLeg(
                market_id=member.market_id,
                token_id=member.token_id,
                side="buy",
                price=basket_cost.fills_by_token[member.token_id].weighted_average_price or DECIMAL_ZERO,
                quantity=basket_cost.fills_by_token[member.token_id].filled_quantity,
                note=member.role,
            )
            for member in context.members
        )
        persistence_key = build_persistence_key(context.template_type, legs)
        candidate = OpportunityCandidate(
            candidate_id=persistence_key,
            strategy_type=StrategyType.ARBITRAGE,
            template_type=context.template_type,
            state=OpportunityState.DETECTED,
            detected_at=detected_at,
            legs=priced_legs,
            expected_edge_bps=net_edge_pct * Decimal("10000"),
            expected_value_usd=net_edge_usd,
            metadata={"payout_per_basket": str(payout_per_basket)},
        )

        detail_json = {
            "template_type": context.template_type.value,
            "group_key": context.group_key,
            "assumptions": context.assumptions,
            "states": [
                {
                    "state_id": state.state_id,
                    "label": state.label,
                    "payouts_by_token": {str(token_id): str(value) for token_id, value in state.payouts_by_token.items()},
                }
                for state in template.build_states(context)
            ],
            "pricing": {
                "basket_quantity": str(executable_size.max_basket_quantity),
                "limiting_token_id": executable_size.limiting_token_id,
                "per_leg_limits": {str(token_id): str(value) for token_id, value in executable_size.per_leg_limits.items()},
                "gross_buy_cost": str(basket_cost.gross_buy_cost),
                "gross_sell_proceeds": str(basket_cost.gross_sell_proceeds),
                "net_cost": str(basket_cost.net_cost),
                "net_edge_usd": str(net_edge_usd),
                "net_edge_pct": str(net_edge_pct),
                "legs": [
                    {
                        "market_id": member.market_id,
                        "token_id": member.token_id,
                        "role": member.role,
                        "side": "buy",
                        "requested_quantity": str(requested_quantities[member.token_id] * executable_size.max_basket_quantity),
                        "filled_quantity": str(basket_cost.fills_by_token[member.token_id].filled_quantity),
                        "weighted_average_price": (
                            str(basket_cost.fills_by_token[member.token_id].weighted_average_price)
                            if basket_cost.fills_by_token[member.token_id].weighted_average_price is not None
                            else None
                        ),
                        "total_notional": str(basket_cost.fills_by_token[member.token_id].total_notional),
                        "fully_filled": basket_cost.fills_by_token[member.token_id].fully_filled,
                        "consumed_depth": [
                            {
                                "price": str(slice_.price),
                                "available_quantity": str(slice_.available_quantity),
                                "filled_quantity": str(slice_.filled_quantity),
                            }
                            for slice_ in basket_cost.fills_by_token[member.token_id].consumed_depth
                        ],
                    }
                    for member in context.members
                ],
            },
            "ranking": {
                "formula": "max_executable_notional * net_edge_pct * confidence_score",
                "max_executable_notional": str(gross_notional),
                "net_edge_pct": str(net_edge_pct),
                "confidence_score": str(confidence_score),
                "ranking_score": str(ranking_score),
            },
            "rejections": {
                "sell_side": sell_side_scaffold,
            },
        }

        return DetectionOutcome(
            finding=RankedFinding(
                candidate=candidate,
                ranking_score=ranking_score,
                confidence_score=confidence_score,
                max_executable_notional=gross_notional,
                net_edge_pct=net_edge_pct,
                detail_json=detail_json,
                persistence_key=persistence_key,
            )
        )
