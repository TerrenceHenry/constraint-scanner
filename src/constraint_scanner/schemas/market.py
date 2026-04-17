from __future__ import annotations

from datetime import datetime

from pydantic import Field

from constraint_scanner.schemas.common import SchemaModel, TimestampedResponse


class TokenResponse(TimestampedResponse):
    """API response for a market token."""

    id: int
    market_id: int
    external_id: str
    symbol: str | None = None
    outcome_name: str
    outcome_index: int


class MarketResponse(TimestampedResponse):
    """API response for a market and its tokens."""

    id: int
    venue: str
    external_id: str
    slug: str | None = None
    question: str
    description: str | None = None
    status: str
    outcome_type: str | None = None
    event_start_at: datetime | None = None
    event_end_at: datetime | None = None
    tokens: list[TokenResponse] = Field(default_factory=list)


class MarketsListResponse(SchemaModel):
    """Collection response for markets."""

    items: list[MarketResponse]


class MarketPageResponse(SchemaModel):
    """Paginated authoritative market listing."""

    items: list[MarketResponse]
    total: int
    limit: int
    offset: int
