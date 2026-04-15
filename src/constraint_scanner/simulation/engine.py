from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from constraint_scanner.config.loader import get_settings
from constraint_scanner.config.models import SimulationSettings
from constraint_scanner.core.clock import ensure_utc
from constraint_scanner.core.constants import DECIMAL_ZERO
from constraint_scanner.core.enums import SimulationClassification
from constraint_scanner.core.ids import make_prefixed_id
from constraint_scanner.core.types import BookSnapshot, SimulationResult
from constraint_scanner.db.models import Opportunity
from constraint_scanner.simulation.executable_pricing import FillComputation, FillSlice, compute_weighted_fill_price
from constraint_scanner.simulation.fill_model import (
    BasketFillAssessment,
    FillModelAssumptions,
    FillModelLeg,
    assess_basket_fill,
)
from constraint_scanner.simulation.fragility import (
    FragilityAssumptions,
    classify_simulation_fragility,
)
from constraint_scanner.simulation.slippage import SlippageAssumptions, SlippageResult, apply_slippage


@dataclass(frozen=True, slots=True)
class ResidualValuation:
    """Residual value assumption for unmatched or excess fills."""

    expected_value: Decimal
    downside_value: Decimal


@dataclass(frozen=True, slots=True)
class SimulatedLeg:
    """Single leg re-simulated against the current live book."""

    market_id: int | None
    token_id: int
    role: str | None
    side: str
    requested_quantity: Decimal
    units_per_basket: Decimal
    detector_weighted_average_price: Decimal | None
    detector_reference_at: datetime
    live_book_observed_at: datetime | None
    fill: FillComputation
    slippage: SlippageResult
    quote_age_seconds: int | None
    stale_quote: bool
    timing_mismatch: bool

    @property
    def consumed_levels(self) -> int:
        """Return the number of executable levels consumed by this leg."""

        return len(self.fill.consumed_depth)


class SimulationEngine:
    """Run deterministic paper simulation against canonical detector outputs."""

    def __init__(self, settings: SimulationSettings | None = None) -> None:
        self._settings = settings or get_settings().simulation
        self._slippage_assumptions = SlippageAssumptions.from_settings(self._settings)
        self._fill_assumptions = FillModelAssumptions.from_settings(self._settings)
        self._fragility_assumptions = FragilityAssumptions.from_settings(self._settings)

    def simulate(
        self,
        *,
        opportunity: Opportunity,
        books: dict[int, BookSnapshot],
        simulated_at: datetime,
    ) -> SimulationResult:
        """Stress-test a detected opportunity against the latest live books."""

        active_simulated_at = ensure_utc(simulated_at)
        simulation_run_id = make_prefixed_id("simrun", opportunity.id, active_simulated_at.isoformat())
        details = dict(opportunity.details or {})
        pricing = details.get("pricing")
        if not isinstance(pricing, dict):
            return self._invalid_result(
                opportunity=opportunity,
                simulated_at=active_simulated_at,
                simulation_run_id=simulation_run_id,
                reason="missing_pricing_payload",
            )

        raw_pricing_legs = pricing.get("legs")
        raw_state_payoffs = details.get("state_payoff_summary")
        if not isinstance(raw_pricing_legs, list) or not isinstance(raw_state_payoffs, list):
            return self._invalid_result(
                opportunity=opportunity,
                simulated_at=active_simulated_at,
                simulation_run_id=simulation_run_id,
                reason="missing_leg_or_state_payload",
            )

        requested_basket_quantity = self._decimal_or_zero(pricing.get("basket_quantity"))
        payout_floor_per_basket = min(
            (
                self._decimal_or_zero(state.get("gross_payoff_per_basket"))
                for state in raw_state_payoffs
                if isinstance(state, dict)
            ),
            default=DECIMAL_ZERO,
        )
        if requested_basket_quantity <= DECIMAL_ZERO or payout_floor_per_basket <= DECIMAL_ZERO:
            return self._invalid_result(
                opportunity=opportunity,
                simulated_at=active_simulated_at,
                simulation_run_id=simulation_run_id,
                reason="invalid_basket_quantity_or_payoff_floor",
            )

        detector_reference_at = ensure_utc(opportunity.detected_at)
        simulated_legs: list[SimulatedLeg] = []
        fill_model_legs: list[FillModelLeg] = []

        for raw_leg in raw_pricing_legs:
            if not isinstance(raw_leg, dict):
                continue

            token_id = int(raw_leg["token_id"])
            requested_quantity = self._decimal_or_zero(raw_leg.get("requested_quantity"))
            if requested_quantity <= DECIMAL_ZERO:
                continue

            side = str(raw_leg.get("side", "buy"))
            book = books.get(token_id)
            live_book_observed_at = ensure_utc(book.observed_at) if book is not None else None
            fill = self._compute_fill(book=book, side=side, requested_quantity=requested_quantity)
            slippage = apply_slippage(fill=fill, side=side, assumptions=self._slippage_assumptions)
            quote_age_seconds = self._quote_age_seconds(book=book, simulated_at=active_simulated_at)
            timing_mismatch = quote_age_seconds is not None and quote_age_seconds < 0
            stale_quote = (
                quote_age_seconds is None
                or timing_mismatch
                or quote_age_seconds > self._fill_assumptions.stale_quote_seconds
            )
            units_per_basket = requested_quantity / requested_basket_quantity

            simulated_leg = SimulatedLeg(
                market_id=int(raw_leg["market_id"]) if raw_leg.get("market_id") is not None else None,
                token_id=token_id,
                role=str(raw_leg.get("role")) if raw_leg.get("role") is not None else None,
                side=side,
                requested_quantity=requested_quantity,
                units_per_basket=units_per_basket,
                detector_weighted_average_price=self._decimal_or_none(raw_leg.get("weighted_average_price")),
                detector_reference_at=detector_reference_at,
                live_book_observed_at=live_book_observed_at,
                fill=fill,
                slippage=slippage,
                quote_age_seconds=quote_age_seconds,
                stale_quote=stale_quote,
                timing_mismatch=timing_mismatch,
            )
            simulated_legs.append(simulated_leg)
            fill_model_legs.append(
                FillModelLeg(
                    token_id=token_id,
                    requested_quantity=requested_quantity,
                    filled_quantity=fill.filled_quantity,
                    units_per_basket=units_per_basket,
                    quote_age_seconds=quote_age_seconds,
                    stale_quote=stale_quote,
                    timing_mismatch=timing_mismatch,
                    consumed_levels=simulated_leg.consumed_levels,
                    role=simulated_leg.role,
                )
            )

        if not simulated_legs:
            return self._invalid_result(
                opportunity=opportunity,
                simulated_at=active_simulated_at,
                simulation_run_id=simulation_run_id,
                reason="no_pricing_legs",
            )

        fill_assessment = assess_basket_fill(
            requested_basket_quantity=requested_basket_quantity,
            legs=fill_model_legs,
            assumptions=self._fill_assumptions,
        )
        gross_buy_cost = sum(
            (leg.slippage.adjusted_notional for leg in simulated_legs if leg.side == "buy"),
            start=DECIMAL_ZERO,
        )
        gross_sell_proceeds = sum(
            (leg.slippage.adjusted_notional for leg in simulated_legs if leg.side == "sell"),
            start=DECIMAL_ZERO,
        )
        net_cost = gross_buy_cost - gross_sell_proceeds
        completed_basket_quantity = fill_assessment.completed_basket_quantity
        guaranteed_gross_payoff_total = payout_floor_per_basket * completed_basket_quantity

        residual_valuations = [
            self._residual_valuation(leg=leg, book=books.get(leg.token_id), completed_basket_quantity=completed_basket_quantity)
            for leg in simulated_legs
        ]
        base_case_residual_value = sum((value.expected_value for value in residual_valuations), start=DECIMAL_ZERO)
        downside_residual_value = sum((value.downside_value for value in residual_valuations), start=DECIMAL_ZERO)

        base_case_pnl_usd = guaranteed_gross_payoff_total + base_case_residual_value - net_cost
        downside_bound_usd = guaranteed_gross_payoff_total + downside_residual_value - net_cost
        fill_probability = fill_assessment.fill_probability
        expected_pnl_usd = downside_bound_usd + ((base_case_pnl_usd - downside_bound_usd) * fill_probability)

        incident_flags = list(fill_assessment.incident_flags)
        if expected_pnl_usd <= DECIMAL_ZERO:
            incident_flags.append("negative_expected_pnl")

        estimated_slippage_bps = self._weighted_slippage_bps(simulated_legs)
        classification = classify_simulation_fragility(
            expected_pnl_usd=expected_pnl_usd,
            downside_bound_usd=downside_bound_usd,
            fill_probability=fill_probability,
            incident_flags=incident_flags,
            assumptions=self._fragility_assumptions,
        )

        ordered_flags = tuple(self._ordered_flags(incident_flags))
        detail_json = self._build_detail_json(
            opportunity=opportunity,
            simulation_run_id=simulation_run_id,
            simulated_at=active_simulated_at,
            payout_floor_per_basket=payout_floor_per_basket,
            requested_basket_quantity=requested_basket_quantity,
            fill_assessment=fill_assessment,
            simulated_legs=tuple(simulated_legs),
            residual_valuations=tuple(residual_valuations),
            gross_buy_cost=gross_buy_cost,
            gross_sell_proceeds=gross_sell_proceeds,
            net_cost=net_cost,
            guaranteed_gross_payoff_total=guaranteed_gross_payoff_total,
            base_case_pnl_usd=base_case_pnl_usd,
            expected_pnl_usd=expected_pnl_usd,
            downside_bound_usd=downside_bound_usd,
            base_case_residual_value=base_case_residual_value,
            downside_residual_value=downside_residual_value,
            fill_probability=fill_probability,
            estimated_slippage_bps=estimated_slippage_bps,
            classification=classification,
            incident_flags=ordered_flags,
        )

        return SimulationResult(
            candidate_id=opportunity.persistence_key,
            simulation_run_id=simulation_run_id,
            classification=classification,
            simulated_at=active_simulated_at,
            fill_probability=fill_probability,
            expected_pnl_usd=expected_pnl_usd,
            downside_bound_usd=downside_bound_usd,
            estimated_slippage_bps=estimated_slippage_bps,
            incident_flags=ordered_flags,
            notes=self._build_notes(classification=classification, incident_flags=ordered_flags),
            details=detail_json,
        )

    def _invalid_result(
        self,
        *,
        opportunity: Opportunity,
        simulated_at: datetime,
        simulation_run_id: str,
        reason: str,
    ) -> SimulationResult:
        classification = SimulationClassification.NON_EXECUTABLE
        return SimulationResult(
            candidate_id=opportunity.persistence_key,
            simulation_run_id=simulation_run_id,
            classification=classification,
            simulated_at=simulated_at,
            fill_probability=DECIMAL_ZERO,
            expected_pnl_usd=DECIMAL_ZERO,
            downside_bound_usd=DECIMAL_ZERO,
            estimated_slippage_bps=DECIMAL_ZERO,
            incident_flags=("invalid_opportunity_payload",),
            notes=(reason,),
            details={
                "simulation_run_id": simulation_run_id,
                "classification": {"value": classification.value, "reason": reason},
                "incident_flags": ["invalid_opportunity_payload"],
                "assumptions": self._assumptions_json(),
            },
        )

    def _build_detail_json(
        self,
        *,
        opportunity: Opportunity,
        simulation_run_id: str,
        simulated_at: datetime,
        payout_floor_per_basket: Decimal,
        requested_basket_quantity: Decimal,
        fill_assessment: BasketFillAssessment,
        simulated_legs: tuple[SimulatedLeg, ...],
        residual_valuations: tuple[ResidualValuation, ...],
        gross_buy_cost: Decimal,
        gross_sell_proceeds: Decimal,
        net_cost: Decimal,
        guaranteed_gross_payoff_total: Decimal,
        base_case_pnl_usd: Decimal,
        expected_pnl_usd: Decimal,
        downside_bound_usd: Decimal,
        base_case_residual_value: Decimal,
        downside_residual_value: Decimal,
        fill_probability: Decimal,
        estimated_slippage_bps: Decimal,
        classification: SimulationClassification,
        incident_flags: tuple[str, ...],
    ) -> dict[str, Any]:
        return {
            "simulation_run_id": simulation_run_id,
            "template_type": (opportunity.details or {}).get("template_type"),
            "simulated_at": simulated_at.isoformat(),
            "assumptions": self._assumptions_json(),
            "baseline": {
                "detected_at": ensure_utc(opportunity.detected_at).isoformat(),
                "pricing_source": "canonical_opportunity_pricing_legs",
                "requested_basket_quantity": str(requested_basket_quantity),
                "gross_payoff_floor_per_basket": str(payout_floor_per_basket),
            },
            "timing": {
                "simulation_timestamp": simulated_at.isoformat(),
                "detector_reference_timestamp": ensure_utc(opportunity.detected_at).isoformat(),
                "stale_quote_threshold_seconds": self._fill_assumptions.stale_quote_seconds,
                "timing_mismatch_tokens": [
                    leg.token_id for leg in simulated_legs if leg.timing_mismatch
                ],
            },
            "pricing": {
                "requested_basket_quantity": str(requested_basket_quantity),
                "completed_basket_quantity": str(fill_assessment.completed_basket_quantity),
                "basket_completion_ratio": str(fill_assessment.basket_completion_ratio),
                "gross_buy_cost": str(gross_buy_cost),
                "gross_sell_proceeds": str(gross_sell_proceeds),
                "net_cost": str(net_cost),
                "guaranteed_gross_payoff_total": str(guaranteed_gross_payoff_total),
                "legs": [
                    self._leg_detail_json(
                        leg=leg,
                        residual=residual,
                        simulated_at=simulated_at,
                        completed_basket_quantity=fill_assessment.completed_basket_quantity,
                    )
                    for leg, residual in zip(simulated_legs, residual_valuations, strict=True)
                ],
            },
            "fill_model": {
                "fill_probability": str(fill_probability),
                "incident_flags": list(incident_flags),
                "leg_asymmetry_ratio_gap": str(fill_assessment.leg_asymmetry_ratio_gap),
                "leg_asymmetry_level_gap": fill_assessment.leg_asymmetry_level_gap,
            },
            "pnl": {
                "base_case_pnl_usd": str(base_case_pnl_usd),
                "expected_pnl_usd": str(expected_pnl_usd),
                "downside_bound_usd": str(downside_bound_usd),
                "base_case_residual_value_usd": str(base_case_residual_value),
                "downside_residual_value_usd": str(downside_residual_value),
                "estimated_slippage_bps": str(estimated_slippage_bps),
                "expected_formula": "downside_bound + ((base_case - downside_bound) * fill_probability)",
                "downside_basis": "guaranteed_completed_basket_payoff_plus_adverse_residual_value_minus_net_cost",
            },
            "classification": {
                "value": classification.value,
                "reason": self._classification_reason(classification, incident_flags),
            },
        }

    def _leg_detail_json(
        self,
        *,
        leg: SimulatedLeg,
        residual: ResidualValuation,
        simulated_at: datetime,
        completed_basket_quantity: Decimal,
    ) -> dict[str, Any]:
        excess_quantity = max(leg.fill.filled_quantity - (leg.units_per_basket * completed_basket_quantity), DECIMAL_ZERO)
        return {
            "market_id": leg.market_id,
            "token_id": leg.token_id,
            "role": leg.role,
            "side": leg.side,
            "requested_quantity": str(leg.requested_quantity),
            "filled_quantity": str(leg.fill.filled_quantity),
            "requested_basket_units": str(leg.units_per_basket),
            "completion_ratio": str(self._ratio(leg.fill.filled_quantity, leg.requested_quantity)),
            "matched_quantity": str(leg.fill.filled_quantity - excess_quantity),
            "excess_quantity": str(excess_quantity),
            "detector_weighted_average_price": (
                str(leg.detector_weighted_average_price) if leg.detector_weighted_average_price is not None else None
            ),
            "simulated_weighted_average_price": (
                str(leg.fill.weighted_average_price) if leg.fill.weighted_average_price is not None else None
            ),
            "simulated_adjusted_price": (
                str(leg.slippage.adjusted_price) if leg.slippage.adjusted_price is not None else None
            ),
            "simulated_notional": str(leg.slippage.adjusted_notional),
            "slippage_bps": str(leg.slippage.applied_bps),
            "timing": {
                "simulation_timestamp": simulated_at.isoformat(),
                "detector_reference_timestamp": leg.detector_reference_at.isoformat(),
                "live_book_observed_at": leg.live_book_observed_at.isoformat() if leg.live_book_observed_at is not None else None,
                "quote_age_seconds": leg.quote_age_seconds,
                "stale_threshold_seconds": self._fill_assumptions.stale_quote_seconds,
                "stale_quote": leg.stale_quote,
                "timing_mismatch": leg.timing_mismatch,
            },
            "residual_value": {
                "expected_value_usd": str(residual.expected_value),
                "downside_value_usd": str(residual.downside_value),
            },
            "consumed_depth": [self._slice_detail_json(slice_) for slice_ in leg.fill.consumed_depth],
        }

    def _slice_detail_json(self, slice_: FillSlice) -> dict[str, str]:
        return {
            "price": str(slice_.price),
            "available_quantity": str(slice_.available_quantity),
            "filled_quantity": str(slice_.filled_quantity),
        }

    def _weighted_slippage_bps(self, simulated_legs: tuple[SimulatedLeg, ...] | list[SimulatedLeg]) -> Decimal:
        total_notional = sum((leg.fill.total_notional for leg in simulated_legs), start=DECIMAL_ZERO)
        if total_notional <= DECIMAL_ZERO:
            return DECIMAL_ZERO
        weighted_bps = sum(
            (leg.slippage.applied_bps * leg.fill.total_notional for leg in simulated_legs),
            start=DECIMAL_ZERO,
        )
        return weighted_bps / total_notional

    def _assumptions_json(self) -> dict[str, Any]:
        return {
            "slippage": self._slippage_assumptions.as_detail_json(),
            "fill_model": self._fill_assumptions.as_detail_json(),
            "fragility": self._fragility_assumptions.as_detail_json(),
            "economic_model": {
                "base_case_basis": "completed_basket_payoff_plus_expected_residual_value_minus_net_cost",
                "downside_basis": "completed_basket_payoff_plus_adverse_residual_value_minus_net_cost",
                "unmatched_buy_residual_downside_value": "zero",
            },
        }

    def _compute_fill(
        self,
        *,
        book: BookSnapshot | None,
        side: str,
        requested_quantity: Decimal,
    ) -> FillComputation:
        if book is None:
            return FillComputation(
                side=side,
                desired_quantity=requested_quantity,
                filled_quantity=DECIMAL_ZERO,
                weighted_average_price=None,
                total_notional=DECIMAL_ZERO,
                consumed_depth=(),
            )
        levels = book.asks if side == "buy" else book.bids
        return compute_weighted_fill_price(levels, requested_quantity, side)

    def _residual_valuation(
        self,
        *,
        leg: SimulatedLeg,
        book: BookSnapshot | None,
        completed_basket_quantity: Decimal,
    ) -> ResidualValuation:
        matched_quantity = min(leg.fill.filled_quantity, leg.units_per_basket * completed_basket_quantity)
        excess_quantity = max(leg.fill.filled_quantity - matched_quantity, DECIMAL_ZERO)
        if excess_quantity <= DECIMAL_ZERO:
            return ResidualValuation(expected_value=DECIMAL_ZERO, downside_value=DECIMAL_ZERO)

        if leg.side == "buy":
            recovery_fill = self._compute_fill(book=book, side="sell", requested_quantity=excess_quantity)
            recovery_slippage = apply_slippage(fill=recovery_fill, side="sell", assumptions=self._slippage_assumptions)
            return ResidualValuation(
                expected_value=recovery_slippage.adjusted_notional,
                downside_value=DECIMAL_ZERO,
            )

        cover_fill = self._compute_fill(book=book, side="buy", requested_quantity=excess_quantity)
        cover_slippage = apply_slippage(fill=cover_fill, side="buy", assumptions=self._slippage_assumptions)
        conservative_cover = cover_slippage.adjusted_notional + (cover_fill.unfilled_quantity * Decimal("1"))
        return ResidualValuation(
            expected_value=-conservative_cover,
            downside_value=-conservative_cover,
        )

    def _quote_age_seconds(self, *, book: BookSnapshot | None, simulated_at: datetime) -> int | None:
        if book is None:
            return None
        delta = ensure_utc(simulated_at) - ensure_utc(book.observed_at)
        return int(delta.total_seconds())

    def _build_notes(
        self,
        *,
        classification: SimulationClassification,
        incident_flags: tuple[str, ...],
    ) -> tuple[str, ...]:
        if incident_flags:
            return (
                f"classification={classification.value}",
                f"incident_flags={','.join(incident_flags)}",
            )
        return (f"classification={classification.value}",)

    def _classification_reason(
        self,
        classification: SimulationClassification,
        incident_flags: tuple[str, ...],
    ) -> str:
        if incident_flags:
            return ",".join(incident_flags)
        return classification.value

    def _ordered_flags(self, flags: list[str]) -> list[str]:
        order = (
            "invalid_opportunity_payload",
            "missing_book",
            "timing_mismatch",
            "stale_quote",
            "shallow_miss",
            "partial_fill",
            "leg_asymmetry",
            "non_executable_depth",
            "negative_expected_pnl",
        )
        seen = set(flags)
        return [flag for flag in order if flag in seen]

    def _decimal_or_zero(self, value: object) -> Decimal:
        if value is None:
            return DECIMAL_ZERO
        return Decimal(str(value))

    def _decimal_or_none(self, value: object) -> Decimal | None:
        if value is None:
            return None
        return Decimal(str(value))

    def _ratio(self, numerator: Decimal, denominator: Decimal) -> Decimal:
        if denominator <= DECIMAL_ZERO:
            return DECIMAL_ZERO
        return numerator / denominator
