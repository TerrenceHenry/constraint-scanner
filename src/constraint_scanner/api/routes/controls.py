from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from constraint_scanner.api.dependencies import get_kill_switch, get_trading_mode_state
from constraint_scanner.core.enums import TradingMode
from constraint_scanner.risk.kill_switch import KillSwitch
from constraint_scanner.schemas.control import KillSwitchControlPayload, TradingControlPayload
from constraint_scanner.schemas.health import KillSwitchStateResponse, TradingModeStateResponse
from constraint_scanner.trading.mode_state import TradingModeState

router = APIRouter(prefix="/controls", tags=["controls"])


@router.post("/kill-switch", response_model=KillSwitchStateResponse)
def set_kill_switch(
    payload: KillSwitchControlPayload,
    kill_switch: KillSwitch = Depends(get_kill_switch),
) -> KillSwitchStateResponse:
    """Explicitly set the kill switch state."""

    if payload.active:
        snapshot = kill_switch.activate(reason=payload.reason or "operator_request")
    else:
        snapshot = kill_switch.clear()

    return KillSwitchStateResponse(
        active=snapshot.active,
        reason=snapshot.reason,
        updated_at=snapshot.updated_at,
    )


@router.post("/trading-mode", response_model=TradingModeStateResponse)
def set_trading_mode(
    payload: TradingControlPayload,
    trading_mode_state: TradingModeState = Depends(get_trading_mode_state),
) -> TradingModeStateResponse:
    """Set the runtime operator-selected trading mode safely."""

    if payload.mode is TradingMode.LIVE:
        if not payload.confirm_live:
            raise HTTPException(status_code=400, detail="live mode requires confirm_live=true")
        raise HTTPException(status_code=409, detail="live mode is not implemented in v1")

    snapshot = trading_mode_state.set_mode(payload.mode, reason=payload.reason or "operator_request")
    return TradingModeStateResponse(
        mode=snapshot.mode,
        reason=snapshot.reason,
        updated_at=snapshot.updated_at,
    )
