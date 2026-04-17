from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import sessionmaker

from constraint_scanner.clients.models import MarketStreamEvent, PolymarketBook
from constraint_scanner.clients.ws_market_client import WsMarketClient
from constraint_scanner.db.repositories.markets import MarketsRepository
from constraint_scanner.db.repositories.orderbooks import OrderbooksRepository
from constraint_scanner.ingestion.feed_state import FeedState
from constraint_scanner.ingestion.raw_archive import RawArchive
from constraint_scanner.ingestion.token_resolution import resolve_event_to_internal_token


class LatestBookCache:
    """Deterministic in-memory latest-book cache keyed by token ID."""

    def __init__(self) -> None:
        self._books: dict[int, PolymarketBook] = {}

    def update(self, book: PolymarketBook) -> None:
        """Replace a token's book only when the incoming snapshot is at least as recent."""

        current = self._books.get(book.snapshot.token_id)
        if current is None or book.snapshot.observed_at >= current.snapshot.observed_at:
            self._books[book.snapshot.token_id] = book

    def get(self, token_id: int) -> PolymarketBook | None:
        """Return the current cached book for a token."""

        return self._books.get(token_id)

    def items(self) -> tuple[tuple[int, PolymarketBook], ...]:
        """Return a deterministic snapshot of the cache."""

        return tuple(sorted(self._books.items(), key=lambda item: item[0]))


@dataclass(frozen=True, slots=True)
class WsConsumerResult:
    """Summary of a websocket consume pass."""

    processed_events: int


class WsConsumer:
    """Consume public websocket events, maintain cache, and persist snapshots."""

    def __init__(
        self,
        ws_client: WsMarketClient,
        session_factory: sessionmaker,
        *,
        feed_state: FeedState,
        latest_book_cache: LatestBookCache | None = None,
        raw_archive: RawArchive | None = None,
        max_depth_levels: int = 10,
    ) -> None:
        self._ws_client = ws_client
        self._session_factory = session_factory
        self._feed_state = feed_state
        self._latest_book_cache = latest_book_cache or LatestBookCache()
        self._raw_archive = raw_archive
        self._max_depth_levels = max_depth_levels

    @property
    def latest_book_cache(self) -> LatestBookCache:
        """Expose the canonical live in-memory book cache."""

        return self._latest_book_cache

    async def consume(self, *, asset_ids: Iterable[str | int], event_limit: int | None = None) -> WsConsumerResult:
        """Consume websocket events and persist canonical live book state."""

        await self._ws_client.subscribe(list(asset_ids))
        processed_events = 0

        async for event in self._ws_client.listen():
            self.handle_event(event)
            processed_events += 1
            if event_limit is not None and processed_events >= event_limit:
                break

        return WsConsumerResult(processed_events=processed_events)

    def handle_event(self, event: MarketStreamEvent, *, archive: bool = True) -> None:
        """Consume one normalized event into the canonical live state."""

        with self._session_factory() as session:
            markets = MarketsRepository(session)
            resolved_event, resolved_token_id = resolve_event_to_internal_token(markets, event)

            if archive and self._raw_archive is not None:
                self._raw_archive.archive(
                    source="polymarket",
                    channel="market",
                    message_type=event.event_type,
                    received_at=event.received_at,
                    payload=event.raw_payload,
                    token_id=resolved_token_id,
                )

            if resolved_event.book is None:
                session.commit()
                return

            self._latest_book_cache.update(resolved_event.book)
            self._feed_state.mark_seen(resolved_event.book.snapshot.token_id, resolved_event.book.snapshot.observed_at)

            repository = OrderbooksRepository(session)
            self._persist_book(repository, resolved_event.book)
            session.commit()

    def _persist_book(self, repository: OrderbooksRepository, book: PolymarketBook) -> None:
        best_bid = book.snapshot.bids[0] if book.snapshot.bids else None
        best_ask = book.snapshot.asks[0] if book.snapshot.asks else None
        spread_bps = None
        if best_bid is not None and best_ask is not None:
            spread_bps = (best_ask.price - best_bid.price) * Decimal("10000")

        repository.create_top_snapshot(
            token_id=book.snapshot.token_id,
            observed_at=book.snapshot.observed_at,
            best_bid_price=best_bid.price if best_bid else None,
            best_bid_size=best_bid.size if best_bid else None,
            best_ask_price=best_ask.price if best_ask else None,
            best_ask_size=best_ask.size if best_ask else None,
            spread_bps=spread_bps,
            payload=book.raw_payload,
        )
        levels = [
            {
                "side": "bid",
                "level": index,
                "price": level.price,
                "size": level.size,
                "payload": {"source": "websocket"},
            }
            for index, level in enumerate(book.snapshot.bids[: self._max_depth_levels], start=1)
        ]
        levels.extend(
            {
                "side": "ask",
                "level": index,
                "price": level.price,
                "size": level.size,
                "payload": {"source": "websocket"},
            }
            for index, level in enumerate(book.snapshot.asks[: self._max_depth_levels], start=1)
        )
        repository.replace_depth_snapshot(
            token_id=book.snapshot.token_id,
            observed_at=book.snapshot.observed_at,
            levels=levels,
        )
