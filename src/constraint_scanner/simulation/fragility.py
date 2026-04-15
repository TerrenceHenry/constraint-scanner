from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from constraint_scanner.config.models import SimulationSettings
from constraint_scanner.core.enums import SimulationClassification


@dataclass(frozen=True, slots=True)
class FragilityAssumptions:
    """Deterministic fragility thresholds for simulation results."""

    robust_fill_probability_threshold: Decimal = Decimal("0.95")

    @classmethod
    def from_settings(cls, settings: SimulationSettings) -> "FragilityAssumptions":
        """Convert runtime settings into Decimal-safe fragility thresholds."""

        return cls(
            robust_fill_probability_threshold=Decimal(str(settings.robust_fill_probability_threshold)),
        )

    def as_detail_json(self) -> dict[str, str]:
        """Return a stable JSON representation for audit payloads."""

        return {
            "robust_fill_probability_threshold": str(self.robust_fill_probability_threshold),
        }


def classify_simulation_fragility(
    *,
    expected_pnl_usd: Decimal,
    downside_bound_usd: Decimal,
    fill_probability: Decimal,
    incident_flags: tuple[str, ...] | list[str],
    assumptions: FragilityAssumptions,
) -> SimulationClassification:
    """Classify a simulation result for later risk gating."""

    flags = set(incident_flags)
    if (
        expected_pnl_usd <= Decimal("0")
        or downside_bound_usd <= Decimal("0")
        or fill_probability <= Decimal("0")
        or "missing_book" in flags
        or "timing_mismatch" in flags
        or "non_executable_depth" in flags
        or "negative_expected_pnl" in flags
    ):
        return SimulationClassification.NON_EXECUTABLE

    if (
        fill_probability < assumptions.robust_fill_probability_threshold
        or any(flag in flags for flag in ("stale_quote", "shallow_miss", "partial_fill", "leg_asymmetry"))
    ):
        return SimulationClassification.FRAGILE

    return SimulationClassification.ROBUST
