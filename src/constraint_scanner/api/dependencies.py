from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker

from constraint_scanner.control_runtime import RuntimeControlState
from constraint_scanner.config.models import Settings
from constraint_scanner.ingestion.feed_state import FeedState
from constraint_scanner.risk.kill_switch import KillSwitch
from constraint_scanner.runtime import ServiceRuntime
from constraint_scanner.trading.mode_state import TradingModeState


def get_settings(request: Request) -> Settings:
    """Return the active application settings."""

    return request.app.state.settings


def get_session_factory(request: Request) -> sessionmaker[Session]:
    """Return the active session factory."""

    return request.app.state.session_factory


def get_db_session(request: Request) -> Iterator[Session]:
    """Yield a request-scoped SQLAlchemy session."""

    session_factory = get_session_factory(request)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def get_feed_state(request: Request) -> FeedState:
    """Return the shared feed freshness tracker."""

    return request.app.state.feed_state


def get_runtime_controls(request: Request) -> RuntimeControlState:
    """Return the authoritative runtime control state container."""

    return request.app.state.runtime_controls


def get_service_runtime(request: Request) -> ServiceRuntime | None:
    """Return the shared service runtime when the app was built with one."""

    return getattr(request.app.state, "service_runtime", None)


def get_kill_switch(request: Request) -> KillSwitch:
    """Return the shared kill switch controller."""

    return get_runtime_controls(request).kill_switch


def get_trading_mode_state(request: Request) -> TradingModeState:
    """Return the shared runtime trading mode controller."""

    return get_runtime_controls(request).trading_mode_state
