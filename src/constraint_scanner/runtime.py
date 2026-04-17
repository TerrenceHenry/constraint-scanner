from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from constraint_scanner.clients.clob_client import ClobClient
from constraint_scanner.clients.gamma_client import GammaClient
from constraint_scanner.clients.ws_market_client import WsMarketClient
from constraint_scanner.config.loader import get_settings
from constraint_scanner.config.models import Settings
from constraint_scanner.control_runtime import RuntimeControlState
from constraint_scanner.core.clock import utc_now
from constraint_scanner.core.types import RiskDecision
from constraint_scanner.db.models import LiveOrder, Opportunity
from constraint_scanner.db.session import get_engine, make_session_factory
from constraint_scanner.detection.detector_service import DetectorService
from constraint_scanner.ingestion.backfill import BookCacheBackfill, BookCacheBackfillResult
from constraint_scanner.ingestion.feed_state import FeedState
from constraint_scanner.ingestion.market_feed_service import MarketFeedService
from constraint_scanner.ingestion.raw_archive import RawArchive
from constraint_scanner.ingestion.ws_consumer import LatestBookCache
from constraint_scanner.risk.exposure import build_exposure_state
from constraint_scanner.risk.policy import RiskPolicy
from constraint_scanner.simulation.simulator_service import SimulatorService
from constraint_scanner.trading.trader_service import TraderService, TraderServiceResult


@dataclass(frozen=True, slots=True)
class PaperTradeAttempt:
    """One risk-evaluated trading attempt over an open opportunity."""

    opportunity_id: int
    risk_decision: RiskDecision
    trade_result: TraderServiceResult


@dataclass(frozen=True, slots=True)
class PaperTradingRunResult:
    """Summary of one manual trader pass over open opportunities."""

    evaluated_opportunities: int
    approved_opportunities: int
    executed_trades: int
    attempts: tuple[PaperTradeAttempt, ...] = field(default_factory=tuple)


@dataclass(slots=True)
class ServiceRuntime:
    """Shared authoritative runtime used by API, CLI, and replay paths."""

    settings: Settings
    engine: Engine
    session_factory: sessionmaker[Session]
    runtime_controls: RuntimeControlState
    feed_state: FeedState
    latest_book_cache: LatestBookCache
    raw_archive: RawArchive
    market_feed_service: MarketFeedService
    detector_service: DetectorService
    simulator_service: SimulatorService
    risk_policy: RiskPolicy
    trader_service: TraderService
    book_backfill: BookCacheBackfill
    gamma_client: GammaClient
    clob_client: ClobClient
    ws_client: WsMarketClient
    owns_engine: bool = False

    def backfill_latest_books_from_db(self, *, token_ids: Collection[int] | None = None) -> BookCacheBackfillResult:
        """Hydrate the canonical live cache from persisted orderbook rows."""

        return self.book_backfill.load(token_ids=token_ids)

    def run_trader_once(
        self,
        *,
        opportunity_ids: Collection[int] | None = None,
        submitted_at: datetime | None = None,
    ) -> PaperTradingRunResult:
        """Risk-evaluate and route currently open opportunities through the trader."""

        active_submitted_at = submitted_at or utc_now()
        with self.session_factory() as session:
            opportunities = self._load_open_opportunities(session, opportunity_ids=opportunity_ids)
            open_order_count = int(session.scalar(select(func.count()).select_from(LiveOrder)) or 0)
            approved_count = 0
            executed_count = 0
            attempts: list[PaperTradeAttempt] = []

            for opportunity in opportunities:
                current_exposure = build_exposure_state(
                    [candidate for candidate in opportunities if candidate.id != opportunity.id],
                    open_order_count=open_order_count,
                )
                risk_decision = self.risk_policy.evaluate_with_repository(
                    opportunity=opportunity,
                    simulations_repository=self._simulations_repository(session),
                    current_exposure=current_exposure,
                    trading_mode=self.runtime_controls.trading_mode_state.snapshot().mode,
                    evaluated_at=active_submitted_at,
                )
                if risk_decision.approved:
                    approved_count += 1

                trade_result = self.trader_service.execute_opportunity(
                    opportunity=opportunity,
                    risk_decision=risk_decision,
                    submitted_at=active_submitted_at,
                )
                if trade_result.executed:
                    executed_count += 1
                    open_order_count += trade_result.order_count
                attempts.append(
                    PaperTradeAttempt(
                        opportunity_id=opportunity.id,
                        risk_decision=risk_decision,
                        trade_result=trade_result,
                    )
                )

        return PaperTradingRunResult(
            evaluated_opportunities=len(opportunities),
            approved_opportunities=approved_count,
            executed_trades=executed_count,
            attempts=tuple(attempts),
        )

    async def aclose(self) -> None:
        """Close external client resources and dispose the owned engine."""

        await self.gamma_client.aclose()
        await self.clob_client.aclose()
        await self.ws_client.aclose()
        if self.owns_engine:
            self.engine.dispose()

    def _load_open_opportunities(
        self,
        session: Session,
        *,
        opportunity_ids: Collection[int] | None,
    ) -> list[Opportunity]:
        stmt = (
            select(Opportunity)
            .where(Opportunity.status == "open")
            .order_by(Opportunity.detected_at.asc(), Opportunity.id.asc())
        )
        if opportunity_ids is not None:
            stmt = stmt.where(Opportunity.id.in_(tuple(sorted({int(opportunity_id) for opportunity_id in opportunity_ids}))))
        return list(session.scalars(stmt))

    def _simulations_repository(self, session: Session):
        from constraint_scanner.db.repositories.simulations import SimulationsRepository

        return SimulationsRepository(session)


def build_service_runtime(
    *,
    settings: Settings | None = None,
    engine: Engine | None = None,
    session_factory: sessionmaker[Session] | None = None,
    runtime_controls: RuntimeControlState | None = None,
    feed_state: FeedState | None = None,
    latest_book_cache: LatestBookCache | None = None,
    gamma_client: GammaClient | None = None,
    clob_client: ClobClient | None = None,
    ws_client: WsMarketClient | None = None,
) -> ServiceRuntime:
    """Build the shared runtime used by API, CLI, and replay workflows."""

    active_settings = settings or get_settings()
    active_engine = engine or get_engine(
        url=active_settings.database.sqlalchemy_url(),
        echo=active_settings.database.echo,
    )
    active_session_factory = session_factory or make_session_factory(active_engine)
    active_runtime_controls = runtime_controls or RuntimeControlState.from_settings(active_settings)
    active_feed_state = feed_state or FeedState(stale_after_seconds=active_settings.ingestion.stale_after_seconds)
    active_latest_book_cache = latest_book_cache or LatestBookCache()
    active_gamma_client = gamma_client or GammaClient()
    active_clob_client = clob_client or ClobClient(base_url=active_settings.polymarket.rest_base_url)
    active_ws_client = ws_client or WsMarketClient(ws_url=active_settings.polymarket.websocket_url)
    raw_archive = RawArchive(
        active_session_factory,
        enabled=active_settings.ingestion.archive_raw_messages,
    )
    market_feed_service = MarketFeedService(
        session_factory=active_session_factory,
        gamma_client=active_gamma_client,
        clob_client=active_clob_client,
        ws_client=active_ws_client,
        settings=active_settings.ingestion,
        feed_state=active_feed_state,
        latest_book_cache=active_latest_book_cache,
        raw_archive=raw_archive,
    )
    detector_service = DetectorService(
        active_session_factory,
        active_latest_book_cache,
        detection_settings=active_settings.detection,
    )
    simulator_service = SimulatorService(
        active_session_factory,
        active_latest_book_cache,
        simulation_settings=active_settings.simulation,
    )
    risk_policy = RiskPolicy(
        kill_switch=active_runtime_controls.kill_switch,
    )
    trader_service = TraderService(
        active_session_factory,
        trading_settings=active_settings.trading,
        runtime_controls=active_runtime_controls,
    )
    book_backfill = BookCacheBackfill(
        active_session_factory,
        latest_book_cache=active_latest_book_cache,
        feed_state=active_feed_state,
    )

    return ServiceRuntime(
        settings=active_settings,
        engine=active_engine,
        session_factory=active_session_factory,
        runtime_controls=active_runtime_controls,
        feed_state=active_feed_state,
        latest_book_cache=active_latest_book_cache,
        raw_archive=raw_archive,
        market_feed_service=market_feed_service,
        detector_service=detector_service,
        simulator_service=simulator_service,
        risk_policy=risk_policy,
        trader_service=trader_service,
        book_backfill=book_backfill,
        gamma_client=active_gamma_client,
        clob_client=active_clob_client,
        ws_client=active_ws_client,
        owns_engine=engine is None and session_factory is None,
    )
