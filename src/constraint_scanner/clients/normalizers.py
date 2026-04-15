from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from constraint_scanner.clients.models import MarketStreamEvent, PolymarketBook, PolymarketMarket
from constraint_scanner.core.clock import utc_now
from constraint_scanner.core.text_utils import normalize_whitespace
from constraint_scanner.core.types import BookLevel, BookSnapshot


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            loaded = json.loads(stripped)
        except json.JSONDecodeError:
            return [value]
        return loaded if isinstance(loaded, list) else [loaded]
    return [value]


def _as_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    return Decimal(str(value))


def _parse_timestamp(value: Any) -> datetime:
    if value in (None, ""):
        return utc_now()
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    text = str(value)
    if text.isdigit():
        return datetime.fromtimestamp(float(text), tz=timezone.utc)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def _parse_token_id(value: Any) -> int:
    text = str(value)
    return int(text, 0)


def normalize_gamma_market(payload: dict[str, Any]) -> PolymarketMarket:
    """Convert a raw Gamma payload into a normalized market structure."""

    tags = []
    for item in _as_list(payload.get("tags")):
        if isinstance(item, dict):
            label = item.get("label") or item.get("name") or item.get("slug")
            if label:
                tags.append(str(label))
        elif item is not None:
            tags.append(str(item))

    return PolymarketMarket(
        market_id=str(payload.get("id") or payload.get("conditionId") or payload.get("slug")),
        slug=payload.get("slug"),
        question=normalize_whitespace(str(payload.get("question") or payload.get("title") or "")),
        description=payload.get("description"),
        active=bool(payload.get("active", False)),
        closed=bool(payload.get("closed", False)),
        archived=payload.get("archived"),
        accepting_orders=payload.get("acceptingOrders"),
        enable_order_book=payload.get("enableOrderBook"),
        outcomes=tuple(str(item) for item in _as_list(payload.get("outcomes"))),
        outcome_prices=tuple(
            decimal for decimal in (_as_decimal(item) for item in _as_list(payload.get("outcomePrices"))) if decimal is not None
        ),
        token_ids=tuple(str(item) for item in _as_list(payload.get("clobTokenIds"))),
        tags=tuple(tags),
        end_date_iso=payload.get("endDate") or payload.get("end_date_iso"),
        raw_payload=payload,
    )


def normalize_clob_book(payload: dict[str, Any]) -> PolymarketBook:
    """Convert a raw CLOB orderbook payload into typed internal structures."""

    asset_id = _parse_token_id(payload["asset_id"])
    bids = tuple(
        BookLevel(price=Decimal(str(level["price"])), size=Decimal(str(level["size"])))
        for level in payload.get("bids", [])
    )
    asks = tuple(
        BookLevel(price=Decimal(str(level["price"])), size=Decimal(str(level["size"])))
        for level in payload.get("asks", [])
    )
    bids = tuple(sorted(bids, key=lambda level: (-level.price, -level.size)))
    asks = tuple(sorted(asks, key=lambda level: (level.price, -level.size)))
    observed_at = _parse_timestamp(payload.get("timestamp"))
    snapshot = BookSnapshot(
        token_id=asset_id,
        market_id=None,
        observed_at=observed_at,
        bids=bids,
        asks=asks,
        source="polymarket-clob",
    )
    return PolymarketBook(
        snapshot=snapshot,
        market=payload.get("market"),
        book_hash=payload.get("hash"),
        tick_size=_as_decimal(payload.get("tick_size")),
        min_order_size=_as_decimal(payload.get("min_order_size")),
        last_trade_price=_as_decimal(payload.get("last_trade_price")),
        raw_payload=payload,
    )


def normalize_market_stream_event(payload: dict[str, Any]) -> MarketStreamEvent:
    """Normalize a public market-stream websocket message."""

    event_type = str(payload.get("event_type") or payload.get("type") or "unknown")
    asset_id = payload.get("asset_id")
    book = normalize_clob_book(payload) if event_type == "book" else None
    return MarketStreamEvent(
        event_type=event_type,
        asset_id=str(asset_id) if asset_id is not None else None,
        received_at=utc_now(),
        book=book,
        best_bid=_as_decimal(payload.get("best_bid")),
        best_ask=_as_decimal(payload.get("best_ask")),
        raw_payload=payload,
    )
