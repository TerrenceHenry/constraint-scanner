from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from constraint_scanner.api.dependencies import get_db_session, get_feed_state, get_kill_switch, get_trading_mode_state
from constraint_scanner.ingestion.feed_state import FeedState
from constraint_scanner.risk.kill_switch import KillSwitch
from constraint_scanner.schemas.health import (
    DbHealthResponse,
    FeedHealthResponse,
    HealthResponse,
    KillSwitchStateResponse,
    TradingModeStateResponse,
)
from constraint_scanner.trading.mode_state import TradingModeState

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(
    session: Session = Depends(get_db_session),
    feed_state: FeedState = Depends(get_feed_state),
    kill_switch: KillSwitch = Depends(get_kill_switch),
    trading_mode_state: TradingModeState = Depends(get_trading_mode_state),
) -> HealthResponse:
    """Return authoritative operator health, control, and feed status."""

    db_ok = True
    db_detail = "ok"
    try:
        session.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - defensive health fallback
        db_ok = False
        db_detail = str(exc)

    feed_status = feed_state.status()
    kill_switch_snapshot = kill_switch.snapshot()
    trading_mode_snapshot = trading_mode_state.snapshot()
    overall_status = "ok" if db_ok and feed_status.healthy else "degraded"

    return HealthResponse(
        status=overall_status,
        db=DbHealthResponse(ok=db_ok, detail=db_detail),
        feed=FeedHealthResponse(
            healthy=feed_status.healthy,
            latest_update_at=feed_status.latest_update_at,
            stale_token_ids=list(feed_status.stale_token_ids),
        ),
        trading_mode=TradingModeStateResponse(
            mode=trading_mode_snapshot.mode,
            reason=trading_mode_snapshot.reason,
            updated_at=trading_mode_snapshot.updated_at,
        ),
        kill_switch=KillSwitchStateResponse(
            active=kill_switch_snapshot.active,
            reason=kill_switch_snapshot.reason,
            updated_at=kill_switch_snapshot.updated_at,
        ),
    )
