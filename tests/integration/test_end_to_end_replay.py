from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from constraint_scanner.config.models import RiskSettings, Settings, TradingSettings
from constraint_scanner.control_runtime import RuntimeControlState
from constraint_scanner.core.enums import TradingMode
from constraint_scanner.db.models import LiveFill, LiveOrder, Opportunity, OrderbookTop, RawFeedMessage
from constraint_scanner.db.repositories.markets import MarketsRepository
from constraint_scanner.manual_constraints import seed_example_manual_constraints
from constraint_scanner.replay.replay_feed import ReplayFeedRunner
from constraint_scanner.risk.kill_switch import KillSwitch
from constraint_scanner.runtime import build_service_runtime
from constraint_scanner.trading.mode_state import TradingModeState


def _session_factory_from_engine(engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def _settings(*, trading_mode: TradingMode) -> Settings:
    return Settings(
        risk=RiskSettings(kill_switch=False),
        trading=TradingSettings(
            enabled=trading_mode is not TradingMode.DISABLED,
            mode=trading_mode,
            paper=trading_mode is TradingMode.PAPER,
            default_tif="IOC",
        ),
    )


def _runtime_controls(*, mode: TradingMode) -> RuntimeControlState:
    return RuntimeControlState(
        kill_switch=KillSwitch(active=False),
        trading_mode_state=TradingModeState(mode=mode, reason="test_default"),
    )


def _seed_replay_markets(session: Session) -> None:
    markets = MarketsRepository(session)
    market_win = markets.create_market(
        external_id="replay-win",
        slug="replay-win",
        question="Will Alice win the election?",
        status="active",
    )
    markets.create_token(
        market_id=market_win.id,
        external_id="900001",
        asset_id="900001",
        outcome_name="Yes",
        outcome_index=0,
    )
    markets.create_token(
        market_id=market_win.id,
        external_id="900003",
        asset_id="900003",
        outcome_name="No",
        outcome_index=1,
    )

    market_lose = markets.create_market(
        external_id="replay-lose",
        slug="replay-lose",
        question="Will Alice lose the election?",
        status="active",
    )
    markets.create_token(
        market_id=market_lose.id,
        external_id="900002",
        asset_id="900002",
        outcome_name="Yes",
        outcome_index=0,
    )
    markets.create_token(
        market_id=market_lose.id,
        external_id="900004",
        asset_id="900004",
        outcome_name="No",
        outcome_index=1,
    )
    session.commit()


def _replay_fixture_path() -> Path:
    return Path(__file__).resolve().parents[1] / "replay" / "binary_complement_sequence.jsonl"


def test_replay_sequence_produces_deterministic_detector_output(session: Session, migrated_engine) -> None:
    _seed_replay_markets(session)
    seed_result = seed_example_manual_constraints(_session_factory_from_engine(migrated_engine))
    assert "binary_complement" in seed_result.created_examples

    replay_runtime = build_service_runtime(
        settings=_settings(trading_mode=TradingMode.DISABLED),
        engine=migrated_engine,
        runtime_controls=_runtime_controls(mode=TradingMode.DISABLED),
    )
    try:
        replay_result = ReplayFeedRunner(replay_runtime).replay_jsonl(_replay_fixture_path())
        assert replay_result.replayed_events == 2
    finally:
        asyncio.run(replay_runtime.aclose())

    persisted_tops = list(session.scalars(select(OrderbookTop).order_by(OrderbookTop.token_id.asc())))
    archived_messages = list(session.scalars(select(RawFeedMessage)))
    assert len(persisted_tops) == 2
    assert archived_messages == []

    detected_at = datetime(2026, 4, 15, 19, 0, tzinfo=timezone.utc)
    detect_runtime_a = build_service_runtime(
        settings=_settings(trading_mode=TradingMode.DISABLED),
        engine=migrated_engine,
        runtime_controls=_runtime_controls(mode=TradingMode.DISABLED),
    )
    try:
        backfill_a = detect_runtime_a.backfill_latest_books_from_db()
        detect_result_a = detect_runtime_a.detector_service.run(detected_at=detected_at)
        assert backfill_a.loaded_books == 2
        assert detect_result_a.detected_opportunities == 1
    finally:
        asyncio.run(detect_runtime_a.aclose())

    first_opportunity = session.scalar(select(Opportunity).limit(1))
    assert first_opportunity is not None
    first_persistence_key = first_opportunity.persistence_key
    first_pricing = dict((first_opportunity.details or {}).get("pricing", {}))

    session.execute(delete(Opportunity))
    session.commit()

    detect_runtime_b = build_service_runtime(
        settings=_settings(trading_mode=TradingMode.DISABLED),
        engine=migrated_engine,
        runtime_controls=_runtime_controls(mode=TradingMode.DISABLED),
    )
    try:
        backfill_b = detect_runtime_b.backfill_latest_books_from_db()
        detect_result_b = detect_runtime_b.detector_service.run(detected_at=detected_at)
        assert backfill_b.loaded_books == 2
        assert detect_result_b.detected_opportunities == 1
    finally:
        asyncio.run(detect_runtime_b.aclose())

    second_opportunity = session.scalar(select(Opportunity).limit(1))
    assert second_opportunity is not None
    assert second_opportunity.persistence_key == first_persistence_key
    assert dict((second_opportunity.details or {}).get("pricing", {})) == first_pricing
    assert Decimal(second_opportunity.details["pricing"]["gross_buy_cost"]) == Decimal("9.50")


def test_replay_sequence_can_be_simulated_and_paper_routed(session: Session, migrated_engine) -> None:
    _seed_replay_markets(session)
    seed_result = seed_example_manual_constraints(_session_factory_from_engine(migrated_engine))
    assert "binary_complement" in seed_result.created_examples

    replay_runtime = build_service_runtime(
        settings=_settings(trading_mode=TradingMode.PAPER),
        engine=migrated_engine,
        runtime_controls=_runtime_controls(mode=TradingMode.PAPER),
    )
    try:
        replay_result = ReplayFeedRunner(replay_runtime).replay_jsonl(_replay_fixture_path())
        assert replay_result.replayed_events == 2
    finally:
        asyncio.run(replay_runtime.aclose())

    runtime = build_service_runtime(
        settings=_settings(trading_mode=TradingMode.PAPER),
        engine=migrated_engine,
        runtime_controls=_runtime_controls(mode=TradingMode.PAPER),
    )
    try:
        backfill = runtime.backfill_latest_books_from_db()
        detected_at = datetime(2026, 4, 15, 19, 0, tzinfo=timezone.utc)
        detect_result = runtime.detector_service.run(detected_at=detected_at)
        simulate_result = runtime.simulator_service.run(simulated_at=detected_at)
        trader_result = runtime.run_trader_once(submitted_at=detected_at)
    finally:
        asyncio.run(runtime.aclose())

    session.expire_all()
    orders = list(session.scalars(select(LiveOrder).order_by(LiveOrder.id.asc())))
    fills = list(session.scalars(select(LiveFill).order_by(LiveFill.id.asc())))

    assert backfill.loaded_books == 2
    assert detect_result.detected_opportunities == 1
    assert simulate_result.simulated_opportunities == 1
    assert simulate_result.persisted_executions == 1
    assert trader_result.evaluated_opportunities == 1
    assert trader_result.approved_opportunities == 1
    assert trader_result.executed_trades == 1
    assert len(orders) == 2
    assert len(fills) == 2
    assert all(order.venue_order_id is None for order in orders)
    assert all(order.status == "paper_filled" for order in orders)
    assert all(fill.venue_fill_id.startswith("paper_fill_") for fill in fills)
    assert orders[0].raw_request["execution_mode"] == "paper"
    assert trader_result.attempts[0].risk_decision.reason_code == "approved"
