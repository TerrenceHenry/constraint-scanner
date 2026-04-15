from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from constraint_scanner.config.models import DetectionSettings
from constraint_scanner.constraints.template_registry import TemplateRegistry, get_template_registry
from constraint_scanner.constraints.types import TemplateContext
from constraint_scanner.core.constants import DECIMAL_ZERO
from constraint_scanner.core.enums import OpportunityState, StrategyType
from constraint_scanner.core.types import BookSnapshot, OpportunityCandidate, OpportunityLeg
from constraint_scanner.detection.detector_base import DetectionOutcome, DetectionRejection, DetectorBase, RankedFinding
from constraint_scanner.detection.persistence import build_persistence_key
from constraint_scanner.detection.ranking import compute_ranking_score
from constraint_scanner.simulation.executable_pricing import (
    BasketCostResult,
    BasketExecutableSize,
    compute_basket_cost,
    compute_max_executable_size_for_basket,
)


@dataclass(frozen=True, slots=True)
class CombinatorialDetectorSettings:
    """Typed runtime settings for combinatorial detection bounds."""

    confidence_threshold: Decimal = Decimal("0.80")
    min_edge_bps: Decimal = DECIMAL_ZERO
    max_legs: int = 8

    @classmethod
    def from_detection_settings(cls, settings: DetectionSettings) -> "CombinatorialDetectorSettings":
        """Convert app detection settings into Decimal-safe detector settings."""

        return cls(
            confidence_threshold=Decimal(str(settings.confidence_threshold)),
            min_edge_bps=Decimal(str(settings.min_edge_bps)),
            max_legs=settings.max_legs,
        )

    def thresholds_for_log(self) -> dict[str, str | int]:
        """Return stable structured threshold values for audit logging."""

        return {
            "confidence_threshold": str(self.confidence_threshold),
            "min_edge_bps": str(self.min_edge_bps),
            "max_legs": self.max_legs,
        }


class CombinatorialDetector(DetectorBase):
    """Detect template-based combinatorial arbitrage from explicit constraint states."""

    detector_name = "combinatorial"

    def __init__(
        self,
        *,
        registry: TemplateRegistry | None = None,
        settings: CombinatorialDetectorSettings | None = None,
        confidence_threshold: Decimal = Decimal("0.80"),
        min_edge_bps: Decimal = DECIMAL_ZERO,
        max_legs: int = 8,
    ) -> None:
        self._registry = registry or get_template_registry()
        self._settings = settings or CombinatorialDetectorSettings(
            confidence_threshold=confidence_threshold,
            min_edge_bps=min_edge_bps,
            max_legs=max_legs,
        )

    @property
    def settings(self) -> CombinatorialDetectorSettings:
        """Expose active runtime settings for service-level audit logging."""

        return self._settings

    def detect(
        self,
        *,
        context: TemplateContext,
        books: dict[int, BookSnapshot],
        confidence_score: Decimal,
        detected_at: datetime,
    ) -> DetectionOutcome:
        template = self._registry.get(context.template_type)
        validation = template.validate(context)
        if not validation.valid:
            return self._reject(
                "template_validation_failed",
                "; ".join(validation.issues),
                member_count=len(context.members),
                validation_issues=list(validation.issues),
            )

        if len(context.members) > self._settings.max_legs:
            return self._reject(
                "max_legs_exceeded",
                f"constraint has {len(context.members)} legs which exceeds max_legs={self._settings.max_legs}",
                member_count=len(context.members),
                max_legs=self._settings.max_legs,
            )
        if confidence_score < self._settings.confidence_threshold:
            return self._reject(
                "confidence_below_threshold",
                f"confidence {confidence_score} is below threshold {self._settings.confidence_threshold}",
                confidence_score=str(confidence_score),
                confidence_threshold=str(self._settings.confidence_threshold),
            )

        states = template.build_states(context)
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
        executable_size = compute_max_executable_size_for_basket(books, legs)
        if executable_size.max_basket_quantity <= DECIMAL_ZERO:
            return self._reject(
                "no_executable_depth",
                "no executable buy-side depth",
                member_count=len(context.members),
            )

        basket_cost = compute_basket_cost(books, legs, executable_size.max_basket_quantity)
        if any(not fill.fully_filled for fill in basket_cost.fills_by_token.values()):
            return self._reject(
                "insufficient_depth_for_full_fill",
                "insufficient depth for full basket fill",
                basket_quantity=str(executable_size.max_basket_quantity),
            )

        pricing = {
            token_id: fill.weighted_average_price or DECIMAL_ZERO
            for token_id, fill in basket_cost.fills_by_token.items()
        }
        evaluation = template.evaluate(context, pricing)
        if evaluation.min_net_payoff <= DECIMAL_ZERO:
            return self._reject(
                "non_positive_guaranteed_payoff",
                "guaranteed state payoff is not above executable basket cost",
                min_net_payoff=str(evaluation.min_net_payoff),
                basket_quantity=str(executable_size.max_basket_quantity),
            )

        gross_notional = basket_cost.gross_buy_cost
        if gross_notional <= DECIMAL_ZERO:
            return self._reject(
                "zero_notional",
                "basket notional is zero",
                gross_notional=str(gross_notional),
            )

        net_edge_usd = evaluation.min_net_payoff * executable_size.max_basket_quantity
        net_edge_pct = net_edge_usd / gross_notional
        edge_bps = net_edge_pct * Decimal("10000")
        if edge_bps <= self._settings.min_edge_bps:
            return self._reject(
                "edge_below_threshold",
                f"edge {edge_bps} bps is below threshold {self._settings.min_edge_bps}",
                edge_bps=str(edge_bps),
                min_edge_bps=str(self._settings.min_edge_bps),
                gross_notional=str(gross_notional),
            )

        ranking_score = compute_ranking_score(
            max_executable_notional=gross_notional,
            net_edge_pct=net_edge_pct,
            confidence_score=confidence_score,
        )
        persistence_key = build_persistence_key(context.template_type, legs)
        candidate = OpportunityCandidate(
            candidate_id=persistence_key,
            strategy_type=StrategyType.ARBITRAGE,
            template_type=context.template_type,
            state=OpportunityState.DETECTED,
            detected_at=detected_at,
            legs=tuple(
                OpportunityLeg(
                    market_id=member.market_id,
                    token_id=member.token_id,
                    side="buy",
                    price=basket_cost.fills_by_token[member.token_id].weighted_average_price or DECIMAL_ZERO,
                    quantity=basket_cost.fills_by_token[member.token_id].filled_quantity,
                    note=member.role,
                )
                for member in context.members
            ),
            expected_edge_bps=edge_bps,
            expected_value_usd=net_edge_usd,
            metadata={
                "min_net_payoff_per_basket": str(evaluation.min_net_payoff),
                "max_net_payoff_per_basket": str(evaluation.max_net_payoff),
            },
        )

        return DetectionOutcome(
            finding=RankedFinding(
                candidate=candidate,
                ranking_score=ranking_score,
                confidence_score=confidence_score,
                max_executable_notional=gross_notional,
                net_edge_pct=net_edge_pct,
                detail_json=self._build_detail_json(
                    context=context,
                    states=states,
                    basket_cost=basket_cost,
                    executable_size=executable_size,
                    confidence_score=confidence_score,
                    ranking_score=ranking_score,
                    evaluation=evaluation,
                    net_edge_usd=net_edge_usd,
                    net_edge_pct=net_edge_pct,
                ),
                persistence_key=persistence_key,
            )
        )

    def _build_detail_json(
        self,
        *,
        context: TemplateContext,
        states: tuple[object, ...],
        basket_cost: BasketCostResult,
        executable_size: BasketExecutableSize,
        confidence_score: Decimal,
        ranking_score: Decimal,
        evaluation,
        net_edge_usd: Decimal,
        net_edge_pct: Decimal,
    ) -> dict[str, object]:
        members = [
            {
                "market_id": member.market_id,
                "token_id": member.token_id,
                "question": member.question,
                "outcome_name": member.outcome_name,
                "role": member.role,
            }
            for member in context.members
        ]
        pricing_legs = [
            {
                "market_id": member.market_id,
                "token_id": member.token_id,
                "role": member.role,
                "side": "buy",
                "requested_quantity": str(executable_size.max_basket_quantity),
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
        ]

        return {
            "template_type": context.template_type.value,
            "group_key": context.group_key,
            "assumptions": context.assumptions,
            "members": members,
            "state_payoff_summary": [
                {
                    "state_id": payoff.state_id,
                    "label": payoff.label,
                    "gross_payoff_per_basket": str(payoff.gross_payoff),
                    "net_payoff_per_basket": str(payoff.net_payoff),
                    "net_payoff_total": str(payoff.net_payoff * executable_size.max_basket_quantity),
                }
                for payoff in evaluation.state_payoffs
            ],
            "pricing": {
                "basket_quantity": str(executable_size.max_basket_quantity),
                "gross_buy_cost": str(basket_cost.gross_buy_cost),
                "gross_sell_proceeds": str(basket_cost.gross_sell_proceeds),
                "net_cost": str(basket_cost.net_cost),
                "net_edge_usd": str(net_edge_usd),
                "net_edge_pct": str(net_edge_pct),
                "legs": pricing_legs,
            },
            "depth_assumptions": {
                "pricing_basis": "executable_orderbook_depth_only",
                "midpoint_used": False,
                "limiting_token_id": executable_size.limiting_token_id,
                "per_leg_limits": {
                    str(token_id): str(value)
                    for token_id, value in executable_size.per_leg_limits.items()
                },
            },
            "filters": {
                "confidence_threshold": str(self._settings.confidence_threshold),
                "min_edge_bps": str(self._settings.min_edge_bps),
                "max_legs": self._settings.max_legs,
                "rejection_reason": None,
            },
            "states": [
                {
                    "state_id": state.state_id,
                    "label": state.label,
                    "payouts_by_token": {
                        str(token_id): str(value)
                        for token_id, value in state.payouts_by_token.items()
                    },
                }
                for state in states
            ],
            "ranking": {
                "formula": "max_executable_notional * net_edge_pct * confidence_score",
                "max_executable_notional": str(basket_cost.gross_buy_cost),
                "net_edge_pct": str(net_edge_pct),
                "confidence_score": str(confidence_score),
                "ranking_score": str(ranking_score),
            },
        }

    def _reject(
        self,
        reason_code: str,
        reason: str,
        **summary_metrics: Any,
    ) -> DetectionOutcome:
        return DetectionOutcome(
            finding=None,
            rejection_reason=reason,
            rejection=DetectionRejection(
                reason_code=reason_code,
                reason=reason,
                summary_metrics=summary_metrics,
            ),
        )
