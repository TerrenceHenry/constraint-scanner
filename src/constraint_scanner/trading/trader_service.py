from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog
from sqlalchemy.orm import sessionmaker

from constraint_scanner.control_runtime import RuntimeControlState
from constraint_scanner.config.loader import get_settings
from constraint_scanner.config.models import TradingSettings
from constraint_scanner.core.clock import ensure_utc, utc_now
from constraint_scanner.core.enums import TradingMode
from constraint_scanner.core.exceptions import TradingModeDisabledError, TradingModeNotSupportedError, TradingValidationError
from constraint_scanner.core.types import RiskDecision
from constraint_scanner.db.models import Opportunity
from constraint_scanner.db.repositories.simulations import SimulationsRepository
from constraint_scanner.trading.order_builder import build_order_requests
from constraint_scanner.trading.order_router import OrderRouter


@dataclass(frozen=True, slots=True)
class TraderServiceResult:
    """Auditable summary of one attempted trading decision."""

    executed: bool
    reason_code: str
    reason: str
    trading_mode: TradingMode
    order_count: int = 0
    fill_count: int = 0
    live_order_ids: tuple[int, ...] = field(default_factory=tuple)
    live_fill_ids: tuple[int, ...] = field(default_factory=tuple)
    metadata: dict[str, object] = field(default_factory=dict)


class TraderService:
    """Route only risk-approved opportunities into safe trading backends."""

    def __init__(
        self,
        session_factory: sessionmaker,
        *,
        trading_settings: TradingSettings | None = None,
        order_router: OrderRouter | None = None,
        runtime_controls: RuntimeControlState,
        logger: Any | None = None,
    ) -> None:
        settings = get_settings()
        self._session_factory = session_factory
        self._trading_settings = trading_settings or settings.trading
        self._logger = logger or structlog.get_logger(__name__)
        self._order_router = order_router or OrderRouter(logger=self._logger)
        self._runtime_controls = runtime_controls

    def execute_opportunity(
        self,
        *,
        opportunity: Opportunity,
        risk_decision: RiskDecision,
        trading_mode: TradingMode | None = None,
        submitted_at: datetime | None = None,
    ) -> TraderServiceResult:
        """Execute a single approved opportunity into the configured trading mode."""

        trading_mode_snapshot = self._runtime_controls.trading_mode_state.snapshot()
        configured_mode = trading_mode_snapshot.mode
        active_mode = trading_mode or configured_mode
        active_submitted_at = ensure_utc(submitted_at or utc_now())
        kill_switch_snapshot = self._runtime_controls.kill_switch.snapshot()
        simulation_run_id = risk_decision.metadata.get("simulation_run_id")
        base_metadata = {
            "opportunity_id": opportunity.id,
            "trading_mode": active_mode.value,
            "submitted_at": active_submitted_at.isoformat(),
            "simulation_run_id": simulation_run_id,
            "runtime_trading_mode": {
                "mode": trading_mode_snapshot.mode.value,
                "reason": trading_mode_snapshot.reason,
                "updated_at": trading_mode_snapshot.updated_at,
            },
            "kill_switch": {
                "active": kill_switch_snapshot.active,
                "reason": kill_switch_snapshot.reason,
                "updated_at": kill_switch_snapshot.updated_at,
            },
        }

        if kill_switch_snapshot.active:
            return self._reject(
                reason_code="kill_switch_active",
                reason="kill switch is active",
                trading_mode=active_mode,
                metadata=base_metadata,
            )
        if not risk_decision.approved or risk_decision.reason_code != "approved":
            return self._reject(
                reason_code="risk_not_approved",
                reason="trader requires a risk-approved opportunity",
                trading_mode=active_mode,
                metadata=base_metadata | {"risk_reason_code": risk_decision.reason_code},
            )
        if trading_mode is not None and trading_mode is not configured_mode:
            return self._reject(
                reason_code="trading_mode_mismatch",
                reason="requested trading mode does not match configured runtime mode",
                trading_mode=active_mode,
                metadata=base_metadata | {"configured_trading_mode": configured_mode.value},
            )
        if not isinstance(simulation_run_id, str) or not simulation_run_id:
            return self._reject(
                reason_code="simulation_link_missing",
                reason="risk approval metadata must include an authoritative simulation_run_id",
                trading_mode=active_mode,
                metadata=base_metadata,
            )
        if risk_decision.max_size_usd is None:
            return self._reject(
                reason_code="approved_notional_missing",
                reason="risk approval must include a positive max_size_usd",
                trading_mode=active_mode,
                metadata=base_metadata,
            )
        if risk_decision.max_size_usd <= 0:
            return self._reject(
                reason_code="approved_notional_non_positive",
                reason="risk approval max_size_usd must be positive",
                trading_mode=active_mode,
                metadata=base_metadata | {"approved_notional_usd": str(risk_decision.max_size_usd)},
            )
        if active_mode is TradingMode.DISABLED:
            return self._reject(
                reason_code="trading_disabled",
                reason="trading mode is disabled",
                trading_mode=active_mode,
                metadata=base_metadata,
            )

        try:
            with self._session_factory() as session:
                simulations = SimulationsRepository(session)
                simulation_row = simulations.get_any_by_run_id(simulation_run_id)
                if simulation_row is None:
                    return self._reject(
                        reason_code="simulation_link_not_found",
                        reason="simulation_run_id does not exist in persisted simulation history",
                        trading_mode=active_mode,
                        metadata=base_metadata,
                    )
                if simulation_row.opportunity_id != opportunity.id:
                    return self._reject(
                        reason_code="simulation_link_opportunity_mismatch",
                        reason="simulation_run_id belongs to a different opportunity",
                        trading_mode=active_mode,
                        metadata=base_metadata | {"linked_opportunity_id": simulation_row.opportunity_id},
                    )
                if not simulation_row.summary_record:
                    return self._reject(
                        reason_code="simulation_link_not_summary",
                        reason="simulation_run_id is not an authoritative summary row",
                        trading_mode=active_mode,
                        metadata=base_metadata | {"linked_summary_record": simulation_row.summary_record},
                    )
                latest_summary = simulations.get_latest_summary_for_opportunity(opportunity.id)
                if latest_summary is None:
                    return self._reject(
                        reason_code="simulation_link_latest_missing",
                        reason="no latest authoritative simulation summary exists for this opportunity",
                        trading_mode=active_mode,
                        metadata=base_metadata,
                    )
                if latest_summary.id != simulation_row.id:
                    return self._reject(
                        reason_code="simulation_link_stale",
                        reason="risk approval does not point to the latest authoritative simulation summary",
                        trading_mode=active_mode,
                        metadata=base_metadata
                        | {
                            "latest_simulation_run_id": latest_summary.simulation_run_id,
                            "linked_simulation_run_id": simulation_row.simulation_run_id,
                        },
                    )

                build_result = build_order_requests(
                    opportunity=opportunity,
                    risk_decision=risk_decision,
                    trading_mode=active_mode,
                    tif=self._trading_settings.default_tif,
                    submitted_at=active_submitted_at,
                )
                routing_result = self._order_router.route(
                    session=session,
                    opportunity=opportunity,
                    build_result=build_result,
                    risk_decision=risk_decision,
                    trading_mode=active_mode,
                    submitted_at=active_submitted_at,
                )
                session.commit()
        except TradingValidationError as exc:
            return self._reject(
                reason_code="trading_validation_error",
                reason=str(exc),
                trading_mode=active_mode,
                metadata=base_metadata,
            )
        except TradingModeDisabledError:
            return self._reject(
                reason_code="trading_disabled",
                reason="trading mode is disabled",
                trading_mode=active_mode,
                metadata=base_metadata,
            )
        except TradingModeNotSupportedError as exc:
            return self._reject(
                reason_code="trading_mode_not_implemented",
                reason=str(exc),
                trading_mode=active_mode,
                metadata=base_metadata,
            )

        result = TraderServiceResult(
            executed=True,
            reason_code="executed",
            reason="orders routed successfully",
            trading_mode=active_mode,
            order_count=routing_result.order_count,
            fill_count=routing_result.fill_count,
            live_order_ids=routing_result.live_order_ids,
            live_fill_ids=routing_result.live_fill_ids,
            metadata=base_metadata
            | {
                "client_order_count": len(build_result.requests),
                "gross_buy_cost": str(build_result.gross_buy_cost),
                "approved_notional_usd": str(build_result.approved_notional_usd),
                "scale_factor": str(build_result.scale_factor),
                "rounded_total_notional_usd": str(build_result.rounded_total_notional_usd),
                "latest_simulation_run_id": simulation_run_id,
            },
        )
        self._logger.info(
            "opportunity_traded",
            opportunity_id=opportunity.id,
            simulation_run_id=simulation_run_id,
            trading_mode=active_mode.value,
            order_count=result.order_count,
            fill_count=result.fill_count,
        )
        return result

    def _reject(
        self,
        *,
        reason_code: str,
        reason: str,
        trading_mode: TradingMode,
        metadata: dict[str, object],
    ) -> TraderServiceResult:
        self._logger.info(
            "opportunity_trade_rejected",
            reason_code=reason_code,
            **metadata,
        )
        return TraderServiceResult(
            executed=False,
            reason_code=reason_code,
            reason=reason,
            trading_mode=trading_mode,
            metadata=dict(metadata),
        )
