from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import sessionmaker

from constraint_scanner.clients.clob_client import ClobClient
from constraint_scanner.clients.models import PolymarketBook
from constraint_scanner.db.repositories.orderbooks import OrderbooksRepository


@dataclass(frozen=True, slots=True)
class OrderbookSnapshotResult:
    """Summary of persisted orderbook snapshots."""

    snapshot_count: int
    token_ids: tuple[int, ...]
    books: tuple[PolymarketBook, ...]


class OrderbookSnapshotter:
    """Fetch initial public books and persist top/depth snapshots."""

    def __init__(self, clob_client: ClobClient, session_factory: sessionmaker, *, max_depth_levels: int = 10) -> None:
        self._clob_client = clob_client
        self._session_factory = session_factory
        self._max_depth_levels = max_depth_levels

    async def fetch_and_persist(self, token_ids: list[str | int]) -> OrderbookSnapshotResult:
        """Fetch initial books and persist best-book plus depth rows."""

        books = await self._clob_client.get_books([str(token_id) for token_id in sorted(token_ids, key=str)])
        with self._session_factory() as session:
            repository = OrderbooksRepository(session)
            for book in books:
                self._persist_book(repository, book)
            session.commit()

        return OrderbookSnapshotResult(
            snapshot_count=len(books),
            token_ids=tuple(book.snapshot.token_id for book in books),
            books=tuple(books),
        )

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
                "payload": {"source": "snapshot"},
            }
            for index, level in enumerate(book.snapshot.bids[: self._max_depth_levels], start=1)
        ]
        levels.extend(
            {
                "side": "ask",
                "level": index,
                "price": level.price,
                "size": level.size,
                "payload": {"source": "snapshot"},
            }
            for index, level in enumerate(book.snapshot.asks[: self._max_depth_levels], start=1)
        )
        repository.replace_depth_snapshot(
            token_id=book.snapshot.token_id,
            observed_at=book.snapshot.observed_at,
            levels=levels,
        )
