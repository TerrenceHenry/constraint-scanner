from __future__ import annotations

from sqlalchemy.orm import sessionmaker

from constraint_scanner.clients.clob_client import ClobClient
from constraint_scanner.clients.gamma_client import GammaClient
from constraint_scanner.clients.ws_market_client import WsMarketClient
from constraint_scanner.config.models import IngestionSettings
from constraint_scanner.ingestion.feed_state import FeedState
from constraint_scanner.ingestion.market_bootstrap import MarketBootstrap, MarketBootstrapResult
from constraint_scanner.ingestion.orderbook_snapshot import OrderbookSnapshotResult, OrderbookSnapshotter
from constraint_scanner.ingestion.raw_archive import RawArchive
from constraint_scanner.ingestion.ws_consumer import LatestBookCache, WsConsumer, WsConsumerResult


class MarketFeedService:
    """Orchestrate market bootstrap, initial snapshots, and websocket ingestion."""

    def __init__(
        self,
        *,
        session_factory: sessionmaker,
        gamma_client: GammaClient,
        clob_client: ClobClient,
        ws_client: WsMarketClient,
        settings: IngestionSettings,
    ) -> None:
        self.feed_state = FeedState(stale_after_seconds=settings.stale_after_seconds)
        self.latest_book_cache = LatestBookCache()
        self.raw_archive = RawArchive(
            session_factory,
            enabled=settings.archive_raw_messages,
        )
        self.bootstrapper = MarketBootstrap(gamma_client, session_factory)
        self.snapshotter = OrderbookSnapshotter(
            clob_client,
            session_factory,
            max_depth_levels=settings.max_depth_levels,
        )
        self.consumer = WsConsumer(
            ws_client,
            session_factory,
            feed_state=self.feed_state,
            latest_book_cache=self.latest_book_cache,
            raw_archive=self.raw_archive,
            max_depth_levels=settings.max_depth_levels,
        )
        self._ws_client = ws_client

    async def bootstrap(self, *, limit: int) -> MarketBootstrapResult:
        """Bootstrap active markets and tokens."""

        return await self.bootstrapper.bootstrap(limit=limit)

    async def snapshot_books(self, token_ids: list[str | int]) -> OrderbookSnapshotResult:
        """Fetch and persist initial orderbook state."""

        result = await self.snapshotter.fetch_and_persist(token_ids)
        for book in result.books:
            self.latest_book_cache.update(book)
            self.feed_state.mark_seen(book.snapshot.token_id, book.snapshot.observed_at)
        return result

    async def consume_live(self, *, asset_ids: list[str | int], event_limit: int | None = None) -> WsConsumerResult:
        """Consume live market websocket events."""

        return await self.consumer.consume(asset_ids=asset_ids, event_limit=event_limit)

    async def run_once(self) -> tuple[MarketBootstrapResult, OrderbookSnapshotResult]:
        """Bootstrap tradable markets and persist their initial books."""

        bootstrap_result = await self.bootstrap(limit=100)
        snapshot_result = await self.snapshot_books(list(bootstrap_result.tradable_token_ids))
        return bootstrap_result, snapshot_result

    async def shutdown(self) -> None:
        """Shutdown websocket resources."""

        await self._ws_client.aclose()
