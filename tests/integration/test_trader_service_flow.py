from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from constraint_scanner.config.models import TradingSettings
from constraint_scanner.core.enums import TradingMode
from constraint_scanner.core.types import RiskDecision
from constraint_scanner.db.models import LogicalConstraint, LiveFill, LiveOrder
from constraint_scanner.db.repositories.groups import GroupsRepository
from constraint_scanner.db.repositories.markets import MarketsRepository
from constraint_scanner.db.repositories.opportunities import OpportunitiesRepository
from constraint_scanner.db.repositories.simulations import SimulationsRepository
from constraint_scanner.risk.kill_switch import KillSwitch
from constraint_scanner.trading.trader_service import TraderService


def _session_factory_from_session(session: Session) -> sessionmaker:
    return sessionmaker(bind=session.bind, autoflush=False, expire_on_commit=False, class_=Session)


def _approved_decision(max_size_usd: str = "10") -> RiskDecision:
    return RiskDecision(
        approved=True,
        reason_code="approved",
        reason="approved",
        max_size_usd=Decimal(max_size_usd),
        metadata={
            "simulation_run_id": "sim-trade-1",
            "approval_summary": {
                "simulation_classification": "robust",
            },
        },
    )


def _rejected_decision() -> RiskDecision:
    return RiskDecision(
        approved=False,
        reason_code="simulation_not_robust",
        reason="simulation not robust",
        max_size_usd=None,
        metadata={"simulation_run_id": "sim-trade-1"},
    )


def _persist_summary(
    session: Session,
    *,
    opportunity_id: int,
    simulation_run_id: str,
    executed_at: datetime,
    classification: str = "robust",
) -> None:
    simulations = SimulationsRepository(session)
    simulations.upsert_summary_execution(
        opportunity_id=opportunity_id,
        simulation_run_id=simulation_run_id,
        defaults={
            "executed_at": executed_at,
            "side": None,
            "price": None,
            "quantity": None,
            "market_id": None,
            "token_id": None,
            "fees_usd": None,
            "pnl_impact_usd": Decimal("1"),
            "payload": {
                "record_type": "simulation_summary",
                "simulation_run_id": simulation_run_id,
                "classification": classification,
                "incident_flags": [],
                "result_json": {
                    "pnl": {
                        "expected_pnl_usd": "1.00",
                        "downside_bound_usd": "0.50",
                    }
                },
            },
        },
    )


def _build_opportunity(session: Session, *, label: str = "trade"):
    markets = MarketsRepository(session)
    groups = GroupsRepository(session)
    opportunities = OpportunitiesRepository(session)

    market = markets.create_market(
        external_id=f"{label}-m1",
        slug=f"{label}-m1",
        question="Will the trade scaffold work?",
    )
    token_yes = markets.create_token(
        market_id=market.id,
        external_id=f"{label}-token-yes",
        outcome_name="YES",
        outcome_index=0,
    )
    token_no = markets.create_token(
        market_id=market.id,
        external_id=f"{label}-token-no",
        outcome_name="NO",
        outcome_index=1,
    )
    group = groups.create_group(group_key=f"{label}-group-1", group_type="event")
    constraint = LogicalConstraint(
        group_id=group.id,
        name=f"{label}-constraint",
        constraint_type="binary_complement",
        definition={"kind": "binary_complement"},
    )
    session.add(constraint)
    session.flush()

    detected_at = datetime(2026, 4, 15, 17, 0, tzinfo=timezone.utc)
    opportunity = opportunities.create_opportunity(
        group_id=group.id,
        constraint_id=constraint.id,
        market_id=market.id,
        token_id=token_yes.id,
        persistence_key=f"{label}-opp-1",
        detected_at=detected_at,
        first_seen_at=detected_at,
        last_seen_at=detected_at,
        status="open",
        edge_bps=Decimal("50"),
        details={
            "pricing": {
                "gross_buy_cost": "10",
                "net_cost": "10",
                "legs": [
                    {
                        "market_id": market.id,
                        "token_id": token_yes.id,
                        "role": "member",
                        "side": "buy",
                        "requested_quantity": "10",
                        "filled_quantity": "10",
                        "weighted_average_price": "0.40",
                        "total_notional": "4",
                        "consumed_depth": [{"price": "0.40", "available_quantity": "10", "filled_quantity": "10"}],
                    },
                    {
                        "market_id": market.id,
                        "token_id": token_no.id,
                        "role": "member",
                        "side": "buy",
                        "requested_quantity": "20",
                        "filled_quantity": "20",
                        "weighted_average_price": "0.30",
                        "total_notional": "6",
                        "consumed_depth": [{"price": "0.30", "available_quantity": "20", "filled_quantity": "20"}],
                    },
                ],
            },
            "ranking": {"confidence_score": "0.90"},
        },
    )
    session.commit()
    return opportunity


def test_trader_service_disabled_mode_rejects(session: Session) -> None:
    opportunity = _build_opportunity(session)
    service = TraderService(
        _session_factory_from_session(session),
        trading_settings=TradingSettings(enabled=False, mode=TradingMode.DISABLED),
        kill_switch=KillSwitch(active=False),
    )

    result = service.execute_opportunity(
        opportunity=opportunity,
        risk_decision=_approved_decision(),
        submitted_at=datetime(2026, 4, 15, 17, 1, tzinfo=timezone.utc),
    )

    session.expire_all()
    assert result.executed is False
    assert result.reason_code == "trading_disabled"
    assert session.scalars(select(LiveOrder)).all() == []


def test_trader_service_paper_mode_creates_synthetic_order_records(session: Session) -> None:
    opportunity = _build_opportunity(session)
    _persist_summary(
        session,
        opportunity_id=opportunity.id,
        simulation_run_id="sim-trade-1",
        executed_at=datetime(2026, 4, 15, 17, 1, tzinfo=timezone.utc),
    )
    session.commit()
    service = TraderService(
        _session_factory_from_session(session),
        trading_settings=TradingSettings(enabled=True, mode=TradingMode.PAPER, default_tif="IOC"),
        kill_switch=KillSwitch(active=False),
    )

    result = service.execute_opportunity(
        opportunity=opportunity,
        risk_decision=_approved_decision(),
        submitted_at=datetime(2026, 4, 15, 17, 2, tzinfo=timezone.utc),
    )

    session.expire_all()
    orders = list(session.scalars(select(LiveOrder).where(LiveOrder.opportunity_id == opportunity.id).order_by(LiveOrder.id)))
    fills = list(session.scalars(select(LiveFill).order_by(LiveFill.id)))

    assert result.executed is True
    assert result.reason_code == "executed"
    assert result.order_count == 2
    assert result.fill_count == 2
    assert len(orders) == 2
    assert len(fills) == 2
    assert all(order.status == "paper_filled" for order in orders)
    assert all(order.venue_order_id is None for order in orders)
    assert orders[0].raw_request["record_type"] == "paper_order_intent"
    assert orders[0].raw_request["execution_mode"] == "paper"
    assert orders[0].raw_request["risk_decision"]["reason_code"] == "approved"
    assert orders[0].raw_request["order_request"]["time_in_force"] == "IOC"
    assert orders[0].raw_response["record_type"] == "paper_order_acknowledgement"
    assert orders[0].raw_response["venue_order_id"] is None
    assert orders[0].raw_response["synthetic_fill"]["quantity"] == "10.00000000"
    assert fills[0].venue_fill_id.startswith("paper_fill_")
    assert fills[0].payload["record_type"] == "paper_fill"
    assert fills[0].payload["execution_mode"] == "paper"
    assert fills[0].payload["synthetic"] is True


def test_trader_service_non_approved_opportunities_do_not_route(session: Session) -> None:
    opportunity = _build_opportunity(session)
    service = TraderService(
        _session_factory_from_session(session),
        trading_settings=TradingSettings(enabled=True, mode=TradingMode.PAPER),
        kill_switch=KillSwitch(active=False),
    )

    result = service.execute_opportunity(
        opportunity=opportunity,
        risk_decision=_rejected_decision(),
        submitted_at=datetime(2026, 4, 15, 17, 3, tzinfo=timezone.utc),
    )

    session.expire_all()
    assert result.executed is False
    assert result.reason_code == "risk_not_approved"
    assert session.scalars(select(LiveOrder)).all() == []


def test_trader_service_rejects_missing_approved_notional(session: Session) -> None:
    opportunity = _build_opportunity(session)
    _persist_summary(
        session,
        opportunity_id=opportunity.id,
        simulation_run_id="sim-trade-1",
        executed_at=datetime(2026, 4, 15, 17, 1, tzinfo=timezone.utc),
    )
    session.commit()
    service = TraderService(
        _session_factory_from_session(session),
        trading_settings=TradingSettings(enabled=True, mode=TradingMode.PAPER),
        kill_switch=KillSwitch(active=False),
    )
    decision = RiskDecision(
        approved=True,
        reason_code="approved",
        reason="approved",
        max_size_usd=None,
        metadata={"simulation_run_id": "sim-trade-1"},
    )

    result = service.execute_opportunity(
        opportunity=opportunity,
        risk_decision=decision,
        submitted_at=datetime(2026, 4, 15, 17, 4, tzinfo=timezone.utc),
    )

    assert result.executed is False
    assert result.reason_code == "approved_notional_missing"
    assert session.scalars(select(LiveOrder)).all() == []


def test_trader_service_rejects_zero_approved_notional(session: Session) -> None:
    opportunity = _build_opportunity(session)
    _persist_summary(
        session,
        opportunity_id=opportunity.id,
        simulation_run_id="sim-trade-1",
        executed_at=datetime(2026, 4, 15, 17, 1, tzinfo=timezone.utc),
    )
    session.commit()
    service = TraderService(
        _session_factory_from_session(session),
        trading_settings=TradingSettings(enabled=True, mode=TradingMode.PAPER),
        kill_switch=KillSwitch(active=False),
    )
    decision = RiskDecision(
        approved=True,
        reason_code="approved",
        reason="approved",
        max_size_usd=Decimal("0"),
        metadata={"simulation_run_id": "sim-trade-1"},
    )

    result = service.execute_opportunity(
        opportunity=opportunity,
        risk_decision=decision,
        submitted_at=datetime(2026, 4, 15, 17, 4, tzinfo=timezone.utc),
    )

    assert result.executed is False
    assert result.reason_code == "approved_notional_non_positive"
    assert session.scalars(select(LiveOrder)).all() == []


def test_trader_service_rejects_fabricated_simulation_run_id(session: Session) -> None:
    opportunity = _build_opportunity(session)
    _persist_summary(
        session,
        opportunity_id=opportunity.id,
        simulation_run_id="sim-trade-real",
        executed_at=datetime(2026, 4, 15, 17, 1, tzinfo=timezone.utc),
    )
    session.commit()
    service = TraderService(
        _session_factory_from_session(session),
        trading_settings=TradingSettings(enabled=True, mode=TradingMode.PAPER),
        kill_switch=KillSwitch(active=False),
    )
    decision = RiskDecision(
        approved=True,
        reason_code="approved",
        reason="approved",
        max_size_usd=Decimal("10"),
        metadata={"simulation_run_id": "sim-trade-fake"},
    )

    result = service.execute_opportunity(
        opportunity=opportunity,
        risk_decision=decision,
        submitted_at=datetime(2026, 4, 15, 17, 5, tzinfo=timezone.utc),
    )

    assert result.executed is False
    assert result.reason_code == "simulation_link_not_found"
    assert session.scalars(select(LiveOrder)).all() == []


def test_trader_service_rejects_stale_simulation_run_id(session: Session) -> None:
    opportunity = _build_opportunity(session)
    _persist_summary(
        session,
        opportunity_id=opportunity.id,
        simulation_run_id="sim-trade-old",
        executed_at=datetime(2026, 4, 15, 17, 1, tzinfo=timezone.utc),
    )
    _persist_summary(
        session,
        opportunity_id=opportunity.id,
        simulation_run_id="sim-trade-new",
        executed_at=datetime(2026, 4, 15, 17, 2, tzinfo=timezone.utc),
    )
    session.commit()
    service = TraderService(
        _session_factory_from_session(session),
        trading_settings=TradingSettings(enabled=True, mode=TradingMode.PAPER),
        kill_switch=KillSwitch(active=False),
    )
    decision = RiskDecision(
        approved=True,
        reason_code="approved",
        reason="approved",
        max_size_usd=Decimal("10"),
        metadata={"simulation_run_id": "sim-trade-old"},
    )

    result = service.execute_opportunity(
        opportunity=opportunity,
        risk_decision=decision,
        submitted_at=datetime(2026, 4, 15, 17, 6, tzinfo=timezone.utc),
    )

    assert result.executed is False
    assert result.reason_code == "simulation_link_stale"
    assert result.metadata["latest_simulation_run_id"] == "sim-trade-new"
    assert session.scalars(select(LiveOrder)).all() == []


def test_trader_service_rejects_simulation_run_id_for_different_opportunity(session: Session) -> None:
    first_opportunity = _build_opportunity(session, label="trade-first")
    second_opportunity = _build_opportunity(session, label="trade-second")
    _persist_summary(
        session,
        opportunity_id=second_opportunity.id,
        simulation_run_id="sim-trade-other",
        executed_at=datetime(2026, 4, 15, 17, 7, tzinfo=timezone.utc),
    )
    session.commit()
    service = TraderService(
        _session_factory_from_session(session),
        trading_settings=TradingSettings(enabled=True, mode=TradingMode.PAPER),
        kill_switch=KillSwitch(active=False),
    )
    decision = RiskDecision(
        approved=True,
        reason_code="approved",
        reason="approved",
        max_size_usd=Decimal("10"),
        metadata={"simulation_run_id": "sim-trade-other"},
    )

    result = service.execute_opportunity(
        opportunity=first_opportunity,
        risk_decision=decision,
        submitted_at=datetime(2026, 4, 15, 17, 8, tzinfo=timezone.utc),
    )

    assert result.executed is False
    assert result.reason_code == "simulation_link_opportunity_mismatch"
    assert result.metadata["linked_opportunity_id"] == second_opportunity.id
    assert session.scalars(select(LiveOrder)).all() == []
