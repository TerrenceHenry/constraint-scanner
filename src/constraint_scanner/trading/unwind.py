from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import structlog

from constraint_scanner.core.clock import ensure_utc, utc_now
from constraint_scanner.core.enums import TradingMode
from constraint_scanner.core.exceptions import TradingModeNotSupportedError
from constraint_scanner.db.models import Opportunity


@dataclass(frozen=True, slots=True)
class UnwindIntent:
    """Future-facing unwind intent scaffold."""

    opportunity_id: int
    trading_mode: TradingMode
    generated_at: datetime
    reason: str
    legs: tuple[dict[str, object], ...]


class UnwindPlanner:
    """Safe unwind scaffold for future live execution support."""

    def __init__(self, *, logger: Any | None = None) -> None:
        self._logger = logger or structlog.get_logger(__name__)

    def build_intent(
        self,
        *,
        opportunity: Opportunity,
        trading_mode: TradingMode,
        reason: str = "future_unwind_placeholder",
        generated_at: datetime | None = None,
    ) -> UnwindIntent:
        """Build an auditable unwind scaffold without executing anything."""

        active_generated_at = ensure_utc(generated_at or utc_now())
        pricing = (opportunity.details or {}).get("pricing")
        raw_legs = pricing.get("legs") if isinstance(pricing, dict) else []
        legs = tuple(leg for leg in raw_legs if isinstance(leg, dict))
        intent = UnwindIntent(
            opportunity_id=opportunity.id,
            trading_mode=trading_mode,
            generated_at=active_generated_at,
            reason=reason,
            legs=legs,
        )

        if trading_mode is TradingMode.PAPER:
            self._logger.info(
                "paper_unwind_intent_logged",
                opportunity_id=opportunity.id,
                trading_mode=trading_mode.value,
                generated_at=active_generated_at.isoformat(),
                reason=reason,
                leg_count=len(legs),
            )
            return intent

        raise TradingModeNotSupportedError(f"{trading_mode.value} unwind is intentionally not implemented in v1")
