from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from constraint_scanner.config.models import SimulationSettings
from constraint_scanner.core.constants import DECIMAL_ZERO
from constraint_scanner.core.types import OrderSide
from constraint_scanner.simulation.executable_pricing import FillComputation


@dataclass(frozen=True, slots=True)
class SlippageAssumptions:
    """Explicit slippage assumptions applied on top of executable book depth."""

    base_bps: Decimal = Decimal("5")
    per_extra_level_bps: Decimal = Decimal("2")

    @classmethod
    def from_settings(cls, settings: SimulationSettings) -> "SlippageAssumptions":
        """Convert runtime settings into Decimal-safe slippage assumptions."""

        return cls(
            base_bps=Decimal(str(settings.slippage_bps)),
            per_extra_level_bps=Decimal(str(settings.per_extra_level_slippage_bps)),
        )

    def as_detail_json(self) -> dict[str, str]:
        """Return a stable JSON representation for audit payloads."""

        return {
            "base_bps": str(self.base_bps),
            "per_extra_level_bps": str(self.per_extra_level_bps),
        }


@dataclass(frozen=True, slots=True)
class SlippageResult:
    """Adjusted leg pricing after deterministic slippage assumptions."""

    applied_bps: Decimal
    adjusted_price: Decimal | None
    adjusted_notional: Decimal


def apply_slippage(
    *,
    fill: FillComputation,
    side: OrderSide,
    assumptions: SlippageAssumptions,
) -> SlippageResult:
    """Apply simple explicit slippage to an executable fill result."""

    if fill.weighted_average_price is None or fill.filled_quantity <= DECIMAL_ZERO:
        return SlippageResult(
            applied_bps=DECIMAL_ZERO,
            adjusted_price=None,
            adjusted_notional=DECIMAL_ZERO,
        )

    extra_levels = max(len(fill.consumed_depth) - 1, 0)
    applied_bps = assumptions.base_bps + (assumptions.per_extra_level_bps * Decimal(extra_levels))
    adjustment = Decimal("1") + (applied_bps / Decimal("10000"))
    if side == "sell":
        adjustment = Decimal("1") - (applied_bps / Decimal("10000"))

    adjusted_price = fill.weighted_average_price * adjustment
    return SlippageResult(
        applied_bps=applied_bps,
        adjusted_price=adjusted_price,
        adjusted_notional=adjusted_price * fill.filled_quantity,
    )
