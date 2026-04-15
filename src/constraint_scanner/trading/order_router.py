from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import structlog
from sqlalchemy.orm import Session

from constraint_scanner.core.enums import TradingMode
from constraint_scanner.core.exceptions import TradingModeDisabledError, TradingModeNotSupportedError, TradingValidationError
from constraint_scanner.core.types import RiskDecision
from constraint_scanner.db.models import Opportunity
from constraint_scanner.trading.order_builder import OrderBuildResult
from constraint_scanner.trading.order_tracker import OrderTrackingResult, PaperOrderTracker


@dataclass(frozen=True, slots=True)
class OrderRoutingResult:
    """Summary of routed order intents."""

    trading_mode: TradingMode
    order_count: int
    fill_count: int
    live_order_ids: tuple[int, ...]
    live_fill_ids: tuple[int, ...]


class OrderRouter:
    """Route built order requests into safe execution backends."""

    def __init__(self, *, logger: Any | None = None) -> None:
        self._logger = logger or structlog.get_logger(__name__)

    def route(
        self,
        *,
        session: Session,
        opportunity: Opportunity,
        build_result: OrderBuildResult,
        risk_decision: RiskDecision,
        trading_mode: TradingMode,
        submitted_at: datetime,
    ) -> OrderRoutingResult:
        """Route order requests according to the requested trading mode."""

        if not build_result.requests:
            raise TradingValidationError("no order requests were built for routing")

        if trading_mode is TradingMode.DISABLED:
            raise TradingModeDisabledError("trading mode is disabled")

        if trading_mode is TradingMode.PAPER:
            tracker = PaperOrderTracker(session, logger=self._logger)
            tracking_result = tracker.persist(
                opportunity=opportunity,
                order_requests=build_result.requests,
                risk_decision=risk_decision,
                simulation_run_id=build_result.simulation_run_id,
                submitted_at=submitted_at,
            )
            return self._routing_result(trading_mode=trading_mode, tracking_result=tracking_result)

        if trading_mode in (TradingMode.SHADOW, TradingMode.LIVE):
            raise TradingModeNotSupportedError(f"{trading_mode.value} routing is intentionally not implemented in v1")

        raise TradingModeNotSupportedError(f"unsupported trading mode: {trading_mode.value}")

    def _routing_result(
        self,
        *,
        trading_mode: TradingMode,
        tracking_result: OrderTrackingResult,
    ) -> OrderRoutingResult:
        return OrderRoutingResult(
            trading_mode=trading_mode,
            order_count=tracking_result.order_count,
            fill_count=tracking_result.fill_count,
            live_order_ids=tuple(record.live_order_id for record in tracking_result.tracked_orders),
            live_fill_ids=tuple(record.live_fill_id for record in tracking_result.tracked_orders),
        )
