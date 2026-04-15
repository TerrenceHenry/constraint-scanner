from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from constraint_scanner.core.clock import ensure_utc
from constraint_scanner.core.types import BookSnapshot


@dataclass(frozen=True, slots=True)
class PolymarketMarket:
    """Normalized Gamma market payload."""

    market_id: str
    slug: str | None
    question: str
    description: str | None
    active: bool
    closed: bool
    archived: bool | None
    accepting_orders: bool | None
    enable_order_book: bool | None
    outcomes: tuple[str, ...] = field(default_factory=tuple)
    outcome_prices: tuple[Decimal, ...] = field(default_factory=tuple)
    token_ids: tuple[str, ...] = field(default_factory=tuple)
    tags: tuple[str, ...] = field(default_factory=tuple)
    end_date_iso: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PolymarketBook:
    """Normalized CLOB book response with a domain snapshot attached."""

    snapshot: BookSnapshot
    market: str | None = None
    book_hash: str | None = None
    tick_size: Decimal | None = None
    min_order_size: Decimal | None = None
    last_trade_price: Decimal | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MarketStreamEvent:
    """Normalized websocket event from the public market stream."""

    event_type: str
    asset_id: str | None
    received_at: datetime
    book: PolymarketBook | None = None
    best_bid: Decimal | None = None
    best_ask: Decimal | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "received_at", ensure_utc(self.received_at))
