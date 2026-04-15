from __future__ import annotations

from datetime import datetime

from pydantic import Field

from constraint_scanner.core.enums import TradingMode
from constraint_scanner.schemas.common import SchemaModel


class IngestionControlPayload(SchemaModel):
    """Payload for enabling or disabling ingestion flows."""

    enabled: bool
    reason: str | None = None


class DetectionControlPayload(SchemaModel):
    """Payload for enabling or disabling template-based detection."""

    enabled: bool
    reason: str | None = None
    template_scope: list[str] = Field(default_factory=list)


class TradingControlPayload(SchemaModel):
    """Payload for controlling the trading subsystem."""

    mode: TradingMode
    reason: str | None = None
    confirm_live: bool = False


class ReplayControlPayload(SchemaModel):
    """Payload for deterministic replay controls."""

    replay_id: str
    start_at: datetime | None = None
    end_at: datetime | None = None
    speed_multiplier: float = 1.0
