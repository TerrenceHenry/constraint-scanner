from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from constraint_scanner.clients.models import PolymarketBook
from constraint_scanner.core.types import BookLevel, BookSnapshot
from constraint_scanner.db.models import OrderbookTop
from constraint_scanner.db.repositories.markets import MarketsRepository
from constraint_scanner.db.repositories.orderbooks import OrderbooksRepository
from constraint_scanner.ingestion.feed_state import FeedState
from constraint_scanner.ingestion.ws_consumer import LatestBookCache


@dataclass(frozen=True, slots=True)
class BookCacheBackfillResult:
    """Summary of a DB-to-cache book backfill pass."""

    loaded_books: int
    token_ids: tuple[int, ...]


class BookCacheBackfill:
    """Hydrate the in-memory latest-book cache from persisted orderbook snapshots."""

    def __init__(
        self,
        session_factory: sessionmaker,
        *,
        latest_book_cache: LatestBookCache,
        feed_state: FeedState,
    ) -> None:
        self._session_factory = session_factory
        self._latest_book_cache = latest_book_cache
        self._feed_state = feed_state

    def load(self, *, token_ids: Collection[int] | None = None) -> BookCacheBackfillResult:
        """Load the latest persisted orderbooks into the canonical live cache."""

        requested_ids = tuple(sorted({int(token_id) for token_id in token_ids})) if token_ids is not None else None
        loaded_token_ids: list[int] = []

        with self._session_factory() as session:
            orderbooks = OrderbooksRepository(session)
            markets = MarketsRepository(session)
            tokens_to_load = requested_ids or tuple(self._discover_token_ids(session))

            for token_id in tokens_to_load:
                top = orderbooks.get_latest_top(token_id)
                if top is None:
                    continue

                token = markets.get_token(token_id)
                depth_rows = orderbooks.list_depth(token_id, top.observed_at)
                bids = tuple(
                    BookLevel(price=row.price, size=row.size)
                    for row in sorted(
                        (row for row in depth_rows if row.side == "bid"),
                        key=lambda row: (-row.price, -row.size, row.level),
                    )
                )
                asks = tuple(
                    BookLevel(price=row.price, size=row.size)
                    for row in sorted(
                        (row for row in depth_rows if row.side == "ask"),
                        key=lambda row: (row.price, -row.size, row.level),
                    )
                )
                book = PolymarketBook(
                    snapshot=BookSnapshot(
                        token_id=token_id,
                        market_id=token.market_id if token is not None else None,
                        observed_at=top.observed_at,
                        bids=bids,
                        asks=asks,
                        source=str((top.payload or {}).get("source") or "db-backfill"),
                    ),
                    raw_payload=top.payload or {},
                )
                self._latest_book_cache.update(book)
                self._feed_state.mark_seen(token_id, top.observed_at)
                loaded_token_ids.append(token_id)

        return BookCacheBackfillResult(
            loaded_books=len(loaded_token_ids),
            token_ids=tuple(loaded_token_ids),
        )

    def _discover_token_ids(self, session) -> tuple[int, ...]:
        stmt = select(OrderbookTop.token_id).distinct().order_by(OrderbookTop.token_id)
        return tuple(session.scalars(stmt))
