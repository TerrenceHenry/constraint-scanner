from __future__ import annotations

from datetime import datetime

from constraint_scanner.core.enums import TradingMode
from constraint_scanner.schemas.common import SchemaModel


class DbHealthResponse(SchemaModel):
    """Database connectivity status."""

    ok: bool
    detail: str


class FeedHealthResponse(SchemaModel):
    """Current ingestion feed freshness state."""

    healthy: bool
    latest_update_at: datetime | None = None
    stale_token_ids: list[int]


class KillSwitchStateResponse(SchemaModel):
    """Current kill switch state."""

    active: bool
    reason: str | None = None
    updated_at: str | None = None


class TradingModeStateResponse(SchemaModel):
    """Current operator-selected trading mode."""

    mode: TradingMode
    reason: str | None = None
    updated_at: str | None = None


class HealthResponse(SchemaModel):
    """Operator health endpoint response."""

    status: str
    db: DbHealthResponse
    feed: FeedHealthResponse
    trading_mode: TradingModeStateResponse
    kill_switch: KillSwitchStateResponse
