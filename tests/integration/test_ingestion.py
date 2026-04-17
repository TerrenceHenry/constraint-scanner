from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from constraint_scanner.clients.models import MarketStreamEvent, PolymarketBook, PolymarketMarket
from constraint_scanner.core.types import BookLevel, BookSnapshot
from constraint_scanner.db.models import RawFeedMessage
from constraint_scanner.db.repositories.markets import MarketsRepository
from constraint_scanner.db.repositories.orderbooks import OrderbooksRepository
from constraint_scanner.ingestion.feed_state import FeedState
from constraint_scanner.ingestion.market_bootstrap import MarketBootstrap
from constraint_scanner.ingestion.orderbook_snapshot import OrderbookSnapshotter
from constraint_scanner.ingestion.raw_archive import RawArchive
from constraint_scanner.ingestion.ws_consumer import LatestBookCache, WsConsumer


class StubGammaClient:
    def __init__(self, markets: list[PolymarketMarket]) -> None:
        self._markets = markets

    async def list_markets(self, **kwargs) -> list[PolymarketMarket]:
        return self._markets


class StubClobClient:
    def __init__(self, books: list[PolymarketBook]) -> None:
        self._books = books

    async def get_books(self, token_ids: list[str | int]) -> list[PolymarketBook]:
        requested = {int(str(token_id), 0) for token_id in token_ids}
        return [book for book in self._books if book.snapshot.token_id in requested]


class StubWsClient:
    def __init__(self, events: list[MarketStreamEvent]) -> None:
        self._events = events
        self.subscriptions: list[list[str | int]] = []

    async def subscribe(self, asset_ids) -> None:
        self.subscriptions.append(list(asset_ids))

    async def listen(self) -> AsyncIterator[MarketStreamEvent]:
        for event in self._events:
            yield event


def _session_factory_from_session(session: Session) -> sessionmaker:
    return sessionmaker(bind=session.bind, autoflush=False, expire_on_commit=False, class_=Session)


def test_market_bootstrap_upserts_markets_and_tokens(session: Session) -> None:
    gamma_client = StubGammaClient(
        [
            PolymarketMarket(
                market_id="market-1",
                slug="market-1",
                question="Will bootstrap work?",
                description="tradable",
                active=True,
                closed=False,
                archived=False,
                accepting_orders=True,
                enable_order_book=True,
                outcomes=("Yes", "No"),
                outcome_prices=(Decimal("0.45"), Decimal("0.55")),
                token_ids=("101", "102"),
                tags=("Test",),
            ),
            PolymarketMarket(
                market_id="market-2",
                slug="market-2",
                question="Inactive market",
                description=None,
                active=False,
                closed=False,
                archived=False,
                accepting_orders=True,
                enable_order_book=True,
                outcomes=("Up", "Down"),
                outcome_prices=(Decimal("0.5"), Decimal("0.5")),
                token_ids=("201", "202"),
                tags=(),
            ),
        ]
    )
    bootstrapper = MarketBootstrap(gamma_client, _session_factory_from_session(session))

    result = asyncio.run(bootstrapper.bootstrap(limit=10))

    repository = MarketsRepository(session)
    tradable_market = repository.get_market_by_external_id("market-1")
    tokens = repository.list_tokens_for_market(tradable_market.id if tradable_market else -1)

    assert tradable_market is not None
    assert len(result.market_ids) == 2
    assert len(result.token_ids) == 4
    assert len(result.tradable_market_ids) == 1
    assert len(result.tradable_token_ids) == 2
    assert [token.external_id for token in tokens] == ["101", "102"]
    assert [token.outcome_name for token in tokens] == ["Yes", "No"]


def test_orderbook_snapshot_persists_top_and_depth_rows(session: Session) -> None:
    external_asset_id = "8501497159083948713316135768103773293754490207922884688769443031624417212426"
    markets = MarketsRepository(session)
    orderbooks = OrderbooksRepository(session)
    market = markets.create_market(external_id="market-snap", slug="market-snap", question="Snapshot?")
    token = markets.create_token(
        market_id=market.id,
        external_id="101",
        asset_id=external_asset_id,
        outcome_name="YES",
        outcome_index=0,
    )
    session.commit()

    observed_at = datetime(2026, 4, 14, 12, 0, tzinfo=timezone.utc)
    book = PolymarketBook(
        snapshot=BookSnapshot(
                token_id=int(external_asset_id),
                market_id=market.id,
                observed_at=observed_at,
                bids=(BookLevel(price=Decimal("0.44"), size=Decimal("10")), BookLevel(price=Decimal("0.43"), size=Decimal("9"))),
                asks=(BookLevel(price=Decimal("0.46"), size=Decimal("12")), BookLevel(price=Decimal("0.47"), size=Decimal("8"))),
                source="test",
            ),
            raw_payload={"asset_id": external_asset_id},
        )
    snapshotter = OrderbookSnapshotter(
        StubClobClient([book]),
        _session_factory_from_session(session),
        max_depth_levels=1,
    )

    result = asyncio.run(snapshotter.fetch_and_persist([token.id]))

    latest_top = orderbooks.get_latest_top(token.id)
    depth = orderbooks.list_depth(token.id, observed_at)

    assert result.snapshot_count == 1
    assert result.token_ids == (token.id,)
    assert latest_top is not None
    assert latest_top.best_bid_price == Decimal("0.44000000")
    assert latest_top.best_ask_price == Decimal("0.46000000")
    assert [(level.side, level.level) for level in depth] == [("ask", 1), ("bid", 1)]


def test_orderbook_snapshot_is_idempotent_for_same_token_and_timestamp(session: Session) -> None:
    external_asset_id = "8501497159083948713316135768103773293754490207922884688769443031624417212426"
    markets = MarketsRepository(session)
    orderbooks = OrderbooksRepository(session)
    market = markets.create_market(external_id="market-repeat", slug="market-repeat", question="Repeat?")
    token = markets.create_token(
        market_id=market.id,
        external_id="201",
        asset_id=external_asset_id,
        outcome_name="YES",
        outcome_index=0,
    )
    session.commit()

    observed_at = datetime(2026, 4, 17, 17, 57, 56, 255000, tzinfo=timezone.utc)
    first_book = PolymarketBook(
        snapshot=BookSnapshot(
            token_id=int(external_asset_id),
            market_id=market.id,
            observed_at=observed_at,
            bids=(BookLevel(price=Decimal("0.012"), size=Decimal("11355.01")),),
            asks=(BookLevel(price=Decimal("0.013"), size=Decimal("1375.29")),),
            source="test",
        ),
        raw_payload={"asset_id": external_asset_id, "snapshot": 1},
    )
    second_book = PolymarketBook(
        snapshot=BookSnapshot(
            token_id=int(external_asset_id),
            market_id=market.id,
            observed_at=observed_at,
            bids=(BookLevel(price=Decimal("0.014"), size=Decimal("9000.00")),),
            asks=(BookLevel(price=Decimal("0.015"), size=Decimal("1200.00")),),
            source="test",
        ),
        raw_payload={"asset_id": external_asset_id, "snapshot": 2},
    )
    snapshotter = OrderbookSnapshotter(
        StubClobClient([first_book]),
        _session_factory_from_session(session),
        max_depth_levels=1,
    )
    replay_snapshotter = OrderbookSnapshotter(
        StubClobClient([second_book]),
        _session_factory_from_session(session),
        max_depth_levels=1,
    )

    first_result = asyncio.run(snapshotter.fetch_and_persist([token.id]))
    second_result = asyncio.run(replay_snapshotter.fetch_and_persist([token.id]))

    persisted_top = orderbooks.get_top_snapshot(token_id=token.id, observed_at=observed_at)
    depth = orderbooks.list_depth(token.id, observed_at)

    assert first_result.snapshot_count == 1
    assert second_result.snapshot_count == 1
    assert persisted_top is not None
    assert persisted_top.best_bid_price == Decimal("0.01400000")
    assert persisted_top.best_ask_price == Decimal("0.01500000")
    assert persisted_top.payload == {"asset_id": external_asset_id, "snapshot": 2}
    assert len(depth) == 2
    assert depth[0].price == Decimal("0.01500000")
    assert depth[1].price == Decimal("0.01400000")


def test_ws_consumer_updates_cache_and_archives_raw_messages(session: Session) -> None:
    markets = MarketsRepository(session)
    market = markets.create_market(external_id="market-live", slug="market-live", question="Live?")
    token = markets.create_token(
        market_id=market.id,
        external_id="token-live",
        outcome_name="YES",
        outcome_index=0,
    )
    session.commit()

    observed_at = datetime(2026, 4, 14, 12, 5, tzinfo=timezone.utc)
    event = MarketStreamEvent(
        event_type="book",
        asset_id=str(token.id),
        received_at=observed_at,
        book=PolymarketBook(
            snapshot=BookSnapshot(
                token_id=token.id,
                market_id=market.id,
                observed_at=observed_at,
                bids=(BookLevel(price=Decimal("0.51"), size=Decimal("20")),),
                asks=(BookLevel(price=Decimal("0.53"), size=Decimal("25")),),
                source="ws",
            ),
            raw_payload={"asset_id": str(token.id), "event_type": "book"},
        ),
        raw_payload={"asset_id": str(token.id), "event_type": "book"},
    )

    feed_state = FeedState(stale_after_seconds=30)
    latest_book_cache = LatestBookCache()
    consumer = WsConsumer(
        StubWsClient([event]),
        _session_factory_from_session(session),
        feed_state=feed_state,
        latest_book_cache=latest_book_cache,
        raw_archive=RawArchive(_session_factory_from_session(session), enabled=True),
        max_depth_levels=2,
    )

    result = asyncio.run(consumer.consume(asset_ids=[token.id], event_limit=1))

    archived_messages = list(session.scalars(select(RawFeedMessage).order_by(RawFeedMessage.id)))
    orderbooks = OrderbooksRepository(session)
    latest_top = orderbooks.get_latest_top(token.id)

    assert result.processed_events == 1
    assert latest_book_cache.get(token.id) is not None
    assert feed_state.status(now=observed_at + timedelta(seconds=5)).healthy is True
    assert len(archived_messages) == 1
    assert archived_messages[0].message_type == "book"
    assert latest_top is not None
    assert latest_top.best_bid_price == Decimal("0.51000000")


def test_feed_state_reports_stale_tokens() -> None:
    now = datetime(2026, 4, 14, 12, 10, tzinfo=timezone.utc)
    state = FeedState(stale_after_seconds=10)

    state.mark_seen(1, now - timedelta(seconds=30))
    state.mark_seen(2, now - timedelta(seconds=5))

    status = state.status(now=now)

    assert status.healthy is False
    assert status.stale_token_ids == (1,)
