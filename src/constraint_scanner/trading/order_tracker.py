from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy.orm import Session

from constraint_scanner.core.clock import ensure_utc
from constraint_scanner.core.ids import make_prefixed_id
from constraint_scanner.core.types import OrderRequest, RiskDecision
from constraint_scanner.db.models import Opportunity
from constraint_scanner.db.repositories.orders import OrdersRepository


@dataclass(frozen=True, slots=True)
class TrackedOrderRecord:
    """Persisted paper order and synthetic fill identifiers."""

    live_order_id: int
    live_fill_id: int
    client_order_id: str
    venue_fill_id: str


@dataclass(frozen=True, slots=True)
class OrderTrackingResult:
    """Summary of persisted synthetic order and fill rows."""

    tracked_orders: tuple[TrackedOrderRecord, ...]
    order_count: int
    fill_count: int


class PaperOrderTracker:
    """Persist fully auditable synthetic paper orders and fills."""

    def __init__(self, session: Session, *, logger: Any | None = None) -> None:
        self._repository = OrdersRepository(session)
        self._logger = logger or structlog.get_logger(__name__)

    def persist(
        self,
        *,
        opportunity: Opportunity,
        order_requests: tuple[OrderRequest, ...],
        risk_decision: RiskDecision,
        simulation_run_id: str,
        submitted_at: datetime,
    ) -> OrderTrackingResult:
        """Persist paper execution intent and immediate synthetic fills."""

        active_submitted_at = ensure_utc(submitted_at)
        tracked_orders: list[TrackedOrderRecord] = []

        for index, order_request in enumerate(order_requests, start=1):
            fill_id = make_prefixed_id("paper_fill", order_request.client_order_id, index)
            order = self._repository.create_order(
                opportunity_id=opportunity.id,
                market_id=order_request.market_id,
                token_id=order_request.token_id,
                client_order_id=order_request.client_order_id,
                venue_order_id=None,
                status="paper_filled",
                side=order_request.side,
                order_type="limit",
                price=order_request.price,
                quantity=order_request.quantity,
                submitted_at=active_submitted_at,
                acknowledged_at=active_submitted_at,
                raw_request=self._raw_request_json(
                    opportunity=opportunity,
                    order_request=order_request,
                    risk_decision=risk_decision,
                    simulation_run_id=simulation_run_id,
                    submitted_at=active_submitted_at,
                ),
                raw_response=self._raw_response_json(
                    fill_id=fill_id,
                    order_request=order_request,
                    submitted_at=active_submitted_at,
                ),
            )
            fill = self._repository.create_fill(
                live_order_id=order.id,
                market_id=order_request.market_id,
                token_id=order_request.token_id,
                venue_fill_id=fill_id,
                filled_at=active_submitted_at,
                price=order_request.price,
                quantity=order_request.quantity,
                fee_usd=Decimal("0"),
                realized_pnl_usd=None,
                payload={
                    "record_type": "paper_fill",
                    "execution_mode": "paper",
                    "synthetic": True,
                    "simulation_run_id": simulation_run_id,
                    "client_order_id": order_request.client_order_id,
                    "fill_policy": "immediate_full_fill_at_requested_limit_price",
                    "submitted_at": active_submitted_at.isoformat(),
                    "order_metadata": dict(order_request.metadata),
                },
            )
            self._logger.info(
                "paper_order_persisted",
                opportunity_id=opportunity.id,
                live_order_id=order.id,
                live_fill_id=fill.id,
                client_order_id=order_request.client_order_id,
                simulation_run_id=simulation_run_id,
            )
            tracked_orders.append(
                TrackedOrderRecord(
                    live_order_id=order.id,
                    live_fill_id=fill.id,
                    client_order_id=order_request.client_order_id,
                    venue_fill_id=fill_id,
                )
            )

        return OrderTrackingResult(
            tracked_orders=tuple(tracked_orders),
            order_count=len(tracked_orders),
            fill_count=len(tracked_orders),
        )

    def _raw_request_json(
        self,
        *,
        opportunity: Opportunity,
        order_request: OrderRequest,
        risk_decision: RiskDecision,
        simulation_run_id: str,
        submitted_at: datetime,
    ) -> dict[str, object]:
        return {
            "record_type": "paper_order_intent",
            "execution_mode": "paper",
            "synthetic": True,
            "opportunity_id": opportunity.id,
            "simulation_run_id": simulation_run_id,
            "risk_decision": {
                "approved": risk_decision.approved,
                "reason_code": risk_decision.reason_code,
                "max_size_usd": str(risk_decision.max_size_usd) if risk_decision.max_size_usd is not None else None,
                "metadata": dict(risk_decision.metadata),
            },
            "submitted_at": submitted_at.isoformat(),
            "order_request": {
                "client_order_id": order_request.client_order_id,
                "market_id": order_request.market_id,
                "token_id": order_request.token_id,
                "side": order_request.side,
                "price": str(order_request.price),
                "quantity": str(order_request.quantity),
                "time_in_force": order_request.time_in_force,
                "metadata": dict(order_request.metadata),
            },
        }

    def _raw_response_json(
        self,
        *,
        fill_id: str,
        order_request: OrderRequest,
        submitted_at: datetime,
    ) -> dict[str, object]:
        return {
            "record_type": "paper_order_acknowledgement",
            "execution_mode": "paper",
            "synthetic": True,
            "venue_order_id": None,
            "status": "paper_filled",
            "acknowledged_at": submitted_at.isoformat(),
            "synthetic_fill": {
                "venue_fill_id": fill_id,
                "filled_at": submitted_at.isoformat(),
                "price": str(order_request.price),
                "quantity": str(order_request.quantity),
                "fee_usd": "0",
                "synthetic": True,
            },
        }
