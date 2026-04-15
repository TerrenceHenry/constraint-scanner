from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from constraint_scanner.schemas.common import BookLevelPayload, SchemaModel


class BookLevelResponse(BookLevelPayload):
    """API response for a single executable book level."""


class OrderbookResponse(SchemaModel):
    """API response for a point-in-time order book snapshot."""

    token_id: int
    market_id: int | None = None
    observed_at: datetime
    bids: list[BookLevelResponse]
    asks: list[BookLevelResponse]
    midpoint_diagnostic: Decimal | None = None
    source: str = "unknown"
    sequence_number: int | None = None
