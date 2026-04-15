from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from constraint_scanner.config.models import SimulationSettings
from constraint_scanner.core.constants import DECIMAL_ZERO


@dataclass(frozen=True, slots=True)
class FillModelAssumptions:
    """Explicit deterministic heuristics for basket completion risk."""

    stale_quote_seconds: int = 15
    stale_quote_probability_factor: Decimal = Decimal("0.60")
    leg_asymmetry_ratio_threshold: Decimal = Decimal("0.20")
    leg_asymmetry_level_gap_threshold: int = 2
    leg_asymmetry_probability_factor: Decimal = Decimal("0.85")

    @classmethod
    def from_settings(cls, settings: SimulationSettings) -> "FillModelAssumptions":
        """Convert runtime settings into Decimal-safe fill model assumptions."""

        return cls(
            stale_quote_seconds=settings.stale_quote_seconds,
            stale_quote_probability_factor=Decimal(str(settings.stale_quote_fill_probability_factor)),
            leg_asymmetry_ratio_threshold=Decimal(str(settings.leg_asymmetry_ratio_threshold)),
            leg_asymmetry_level_gap_threshold=settings.leg_asymmetry_level_gap_threshold,
            leg_asymmetry_probability_factor=Decimal(str(settings.leg_asymmetry_fill_probability_factor)),
        )

    def as_detail_json(self) -> dict[str, str | int]:
        """Return a stable JSON representation for audit payloads."""

        return {
            "stale_quote_seconds": self.stale_quote_seconds,
            "stale_quote_probability_factor": str(self.stale_quote_probability_factor),
            "leg_asymmetry_ratio_threshold": str(self.leg_asymmetry_ratio_threshold),
            "leg_asymmetry_level_gap_threshold": self.leg_asymmetry_level_gap_threshold,
            "leg_asymmetry_probability_factor": str(self.leg_asymmetry_probability_factor),
            "basket_completion_basis": "minimum_supported_basket_units_across_legs",
        }


@dataclass(frozen=True, slots=True)
class FillModelLeg:
    """Per-leg simulation input for basket completion analysis."""

    token_id: int
    requested_quantity: Decimal
    filled_quantity: Decimal
    units_per_basket: Decimal
    quote_age_seconds: int | None
    stale_quote: bool
    timing_mismatch: bool
    consumed_levels: int
    role: str | None = None

    @property
    def completion_ratio(self) -> Decimal:
        """Return the realized fill ratio for this leg."""

        if self.requested_quantity <= DECIMAL_ZERO:
            return DECIMAL_ZERO
        return self.filled_quantity / self.requested_quantity

    @property
    def basket_capacity(self) -> Decimal:
        """Return how many full basket units this leg can support."""

        if self.units_per_basket <= DECIMAL_ZERO:
            return DECIMAL_ZERO
        return self.filled_quantity / self.units_per_basket


@dataclass(frozen=True, slots=True)
class BasketFillAssessment:
    """Deterministic completion assessment for a basket simulation."""

    requested_basket_quantity: Decimal
    completed_basket_quantity: Decimal
    basket_completion_ratio: Decimal
    fill_probability: Decimal
    incident_flags: tuple[str, ...]
    leg_asymmetry_ratio_gap: Decimal
    leg_asymmetry_level_gap: int
    legs: tuple[FillModelLeg, ...] = field(default_factory=tuple)


def assess_basket_fill(
    *,
    requested_basket_quantity: Decimal,
    legs: tuple[FillModelLeg, ...] | list[FillModelLeg],
    assumptions: FillModelAssumptions,
) -> BasketFillAssessment:
    """Assess basket completion risk from per-leg simulated fills."""

    normalized_legs = tuple(legs)
    if requested_basket_quantity <= DECIMAL_ZERO or not normalized_legs:
        return BasketFillAssessment(
            requested_basket_quantity=requested_basket_quantity,
            completed_basket_quantity=DECIMAL_ZERO,
            basket_completion_ratio=DECIMAL_ZERO,
            fill_probability=DECIMAL_ZERO,
            incident_flags=("invalid_requested_quantity",),
            leg_asymmetry_ratio_gap=DECIMAL_ZERO,
            leg_asymmetry_level_gap=0,
            legs=normalized_legs,
        )

    completed_basket_quantity = min((leg.basket_capacity for leg in normalized_legs), default=DECIMAL_ZERO)
    basket_completion_ratio = completed_basket_quantity / requested_basket_quantity
    completion_ratios = tuple(leg.completion_ratio for leg in normalized_legs)
    leg_asymmetry_ratio_gap = max(completion_ratios, default=DECIMAL_ZERO) - min(
        completion_ratios,
        default=DECIMAL_ZERO,
    )
    consumed_levels = tuple(leg.consumed_levels for leg in normalized_legs)
    leg_asymmetry_level_gap = max(consumed_levels, default=0) - min(consumed_levels, default=0)

    fill_probability = basket_completion_ratio
    flags: list[str] = []

    if any(leg.stale_quote for leg in normalized_legs):
        fill_probability *= assumptions.stale_quote_probability_factor
        flags.append("stale_quote")
    if any(leg.timing_mismatch for leg in normalized_legs):
        fill_probability = DECIMAL_ZERO
        flags.append("timing_mismatch")
    if any(leg.filled_quantity < leg.requested_quantity for leg in normalized_legs):
        flags.append("shallow_miss")
    if DECIMAL_ZERO < completed_basket_quantity < requested_basket_quantity:
        flags.append("partial_fill")
    if completed_basket_quantity <= DECIMAL_ZERO:
        flags.append("non_executable_depth")
    if (
        leg_asymmetry_ratio_gap > assumptions.leg_asymmetry_ratio_threshold
        or leg_asymmetry_level_gap >= assumptions.leg_asymmetry_level_gap_threshold
    ):
        fill_probability *= assumptions.leg_asymmetry_probability_factor
        flags.append("leg_asymmetry")
    if any(leg.quote_age_seconds is None for leg in normalized_legs):
        flags.append("missing_book")

    fill_probability = max(DECIMAL_ZERO, min(fill_probability, Decimal("1")))
    return BasketFillAssessment(
        requested_basket_quantity=requested_basket_quantity,
        completed_basket_quantity=completed_basket_quantity,
        basket_completion_ratio=basket_completion_ratio,
        fill_probability=fill_probability,
        incident_flags=tuple(_ordered_flags(flags)),
        leg_asymmetry_ratio_gap=leg_asymmetry_ratio_gap,
        leg_asymmetry_level_gap=leg_asymmetry_level_gap,
        legs=normalized_legs,
    )


def _ordered_flags(flags: list[str]) -> list[str]:
    order = (
        "missing_book",
        "timing_mismatch",
        "stale_quote",
        "shallow_miss",
        "partial_fill",
        "leg_asymmetry",
        "non_executable_depth",
    )
    seen = set(flags)
    return [flag for flag in order if flag in seen]
