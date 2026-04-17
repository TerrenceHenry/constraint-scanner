from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from constraint_scanner.api.app import create_app
from constraint_scanner.control_runtime import RuntimeControlState
from constraint_scanner.config.models import IngestionSettings, RiskSettings, Settings, TradingSettings
from constraint_scanner.core.clock import utc_now
from constraint_scanner.core.enums import TradingMode
from constraint_scanner.core.types import RiskDecision
from constraint_scanner.db.models import LogicalConstraint, Opportunity
from constraint_scanner.db.repositories.groups import GroupsRepository
from constraint_scanner.db.repositories.markets import MarketsRepository
from constraint_scanner.db.repositories.opportunities import OpportunitiesRepository
from constraint_scanner.db.repositories.simulations import SimulationsRepository
from constraint_scanner.ingestion.feed_state import FeedState
from constraint_scanner.risk.kill_switch import KillSwitch
from constraint_scanner.trading.mode_state import TradingModeState
from constraint_scanner.trading.trader_service import TraderService


def _session_factory_from_engine(engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def _runtime_controls(*, mode: TradingMode, kill_switch_active: bool = False) -> RuntimeControlState:
    return RuntimeControlState(
        kill_switch=KillSwitch(active=kill_switch_active),
        trading_mode_state=TradingModeState(mode=mode, reason="test_default"),
    )


def _seed_operator_data(session: Session) -> dict[str, int]:
    markets = MarketsRepository(session)
    groups = GroupsRepository(session)
    opportunities = OpportunitiesRepository(session)
    simulations = SimulationsRepository(session)

    market = markets.create_market(
        external_id="api-market-1",
        slug="api-market-1",
        question="Will the operator API return authoritative data?",
    )
    token_yes = markets.create_token(
        market_id=market.id,
        external_id="api-token-yes",
        outcome_name="YES",
        outcome_index=0,
    )
    markets.create_token(
        market_id=market.id,
        external_id="api-token-no",
        outcome_name="NO",
        outcome_index=1,
    )
    group = groups.create_group(group_key="api-group-1", group_type="event", label="API group")
    constraint = LogicalConstraint(
        group_id=group.id,
        name="api-constraint",
        constraint_type="binary_complement",
        definition={"kind": "binary_complement"},
    )
    session.add(constraint)
    session.flush()

    detected_at = datetime(2026, 4, 15, 19, 0, tzinfo=timezone.utc)
    opportunity = opportunities.create_opportunity(
        group_id=group.id,
        constraint_id=constraint.id,
        market_id=market.id,
        token_id=token_yes.id,
        persistence_key="api-opp-1",
        detected_at=detected_at,
        first_seen_at=detected_at,
        last_seen_at=detected_at,
        status="open",
        score=Decimal("0.9100"),
        edge_bps=Decimal("40.0000"),
        expected_value_usd=Decimal("1.2500"),
        details={
            "template_type": "binary_complement",
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
                        "consumed_depth": [],
                    }
                ],
            },
            "ranking": {
                "confidence_score": "0.90",
            },
        },
    )
    closed_opportunity = opportunities.create_opportunity(
        group_id=group.id,
        constraint_id=constraint.id,
        market_id=market.id,
        token_id=token_yes.id,
        persistence_key="api-opp-closed",
        detected_at=detected_at.replace(minute=1),
        first_seen_at=detected_at.replace(minute=1),
        last_seen_at=detected_at.replace(minute=2),
        closed_at=detected_at.replace(minute=3),
        status="closed",
        score=Decimal("0.1000"),
        edge_bps=Decimal("1.0000"),
        expected_value_usd=Decimal("0.0100"),
        details={
            "template_type": "binary_complement",
            "pricing": {
                "gross_buy_cost": "1",
                "net_cost": "1",
                "legs": [],
            },
            "ranking": {
                "confidence_score": "0.10",
            },
        },
    )
    simulations.upsert_summary_execution(
        opportunity_id=opportunity.id,
        simulation_run_id="sim-api-old",
        defaults={
            "executed_at": detected_at,
            "side": None,
            "price": None,
            "quantity": None,
            "market_id": None,
            "token_id": None,
            "fees_usd": None,
            "pnl_impact_usd": Decimal("0.50"),
            "payload": {
                "record_type": "simulation_summary",
                "simulation_run_id": "sim-api-old",
                "classification": "fragile",
                "fill_probability": "0.6",
                "expected_pnl_usd": "0.50",
                "downside_bound_usd": "0.10",
                "estimated_slippage_bps": "5",
                "incident_flags": ["partial_fill"],
                "notes": [],
                "result_json": {"pnl": {"expected_pnl_usd": "0.50", "downside_bound_usd": "0.10"}},
            },
        },
    )
    simulations.upsert_summary_execution(
        opportunity_id=opportunity.id,
        simulation_run_id="sim-api-new",
        defaults={
            "executed_at": detected_at.replace(minute=5),
            "side": None,
            "price": None,
            "quantity": None,
            "market_id": None,
            "token_id": None,
            "fees_usd": None,
            "pnl_impact_usd": Decimal("1.25"),
            "payload": {
                "record_type": "simulation_summary",
                "simulation_run_id": "sim-api-new",
                "classification": "robust",
                "fill_probability": "0.95",
                "expected_pnl_usd": "1.25",
                "downside_bound_usd": "0.80",
                "estimated_slippage_bps": "2",
                "incident_flags": [],
                "notes": [],
                "result_json": {"pnl": {"expected_pnl_usd": "1.25", "downside_bound_usd": "0.80"}},
            },
        },
    )
    session.commit()
    return {
        "market_id": market.id,
        "opportunity_id": opportunity.id,
        "closed_opportunity_id": closed_opportunity.id,
        "token_id": token_yes.id,
    }


def _build_client(migrated_engine, *, feed_state: FeedState, runtime_controls: RuntimeControlState) -> TestClient:
    settings = Settings(
        ingestion=IngestionSettings(stale_after_seconds=30),
        risk=RiskSettings(kill_switch=False),
        trading=TradingSettings(enabled=False, mode=TradingMode.DISABLED),
    )
    app = create_app(
        settings=settings,
        engine=migrated_engine,
        session_factory=_session_factory_from_engine(migrated_engine),
        feed_state=feed_state,
        runtime_controls=runtime_controls,
    )
    return TestClient(app)


def test_health_route_reports_db_feed_and_controls(session: Session, migrated_engine) -> None:
    seeded = _seed_operator_data(session)
    feed_state = FeedState(stale_after_seconds=30)
    feed_state.mark_seen(seeded["token_id"], utc_now())
    runtime_controls = _runtime_controls(mode=TradingMode.DISABLED)

    with _build_client(
        migrated_engine,
        feed_state=feed_state,
        runtime_controls=runtime_controls,
    ) as client:
        response = client.get("/health")

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["db"]["ok"] is True
        assert payload["feed"]["healthy"] is True
        assert payload["trading_mode"]["mode"] == "disabled"
        assert payload["kill_switch"]["active"] is False

        kill_switch_response = client.post("/controls/kill-switch", json={"active": True, "reason": "manual"})
        assert kill_switch_response.status_code == 200
        assert kill_switch_response.json()["active"] is True

        trading_mode_response = client.post("/controls/trading-mode", json={"mode": "paper", "reason": "operator"})
        assert trading_mode_response.status_code == 200
        assert trading_mode_response.json()["mode"] == "paper"

        refreshed = client.get("/health")
        refreshed_payload = refreshed.json()
        assert refreshed_payload["kill_switch"]["active"] is True
        assert refreshed_payload["trading_mode"]["mode"] == "paper"


def test_list_routes_use_latest_authoritative_records(session: Session, migrated_engine) -> None:
    seeded = _seed_operator_data(session)
    feed_state = FeedState(stale_after_seconds=30)
    runtime_controls = _runtime_controls(mode=TradingMode.DISABLED)

    with _build_client(
        migrated_engine,
        feed_state=feed_state,
        runtime_controls=runtime_controls,
    ) as client:
        markets_response = client.get("/markets")
        assert markets_response.status_code == 200
        assert markets_response.json()["items"][0]["external_id"] == "api-market-1"

        opportunities_response = client.get("/opportunities")
        assert opportunities_response.status_code == 200
        assert opportunities_response.json()["total"] == 1
        opportunity_item = opportunities_response.json()["items"][0]
        assert opportunity_item["id"] == seeded["opportunity_id"]
        assert opportunity_item["latest_simulation"]["simulation_run_id"] == "sim-api-new"
        assert opportunity_item["latest_simulation"]["summary_record"] is True

        closed_response = client.get("/opportunities", params={"status": "closed"})
        assert closed_response.status_code == 200
        assert closed_response.json()["total"] == 1
        assert closed_response.json()["items"][0]["id"] == seeded["closed_opportunity_id"]

        simulations_response = client.get("/simulations")
        assert simulations_response.status_code == 200
        simulation_item = simulations_response.json()["items"][0]
        assert simulations_response.json()["total"] == 1
        assert simulation_item["simulation_run_id"] == "sim-api-new"
        assert simulation_item["classification"] == "robust"


def test_opportunity_detail_route_uses_latest_authoritative_summary(session: Session, migrated_engine) -> None:
    seeded = _seed_operator_data(session)
    feed_state = FeedState(stale_after_seconds=30)
    runtime_controls = _runtime_controls(mode=TradingMode.DISABLED)

    with _build_client(
        migrated_engine,
        feed_state=feed_state,
        runtime_controls=runtime_controls,
    ) as client:
        response = client.get(f"/opportunities/{seeded['opportunity_id']}")

        assert response.status_code == 200
        payload = response.json()
        assert payload["id"] == seeded["opportunity_id"]
        assert payload["details"]["pricing"]["gross_buy_cost"] == "10"
        assert payload["latest_simulation"]["simulation_run_id"] == "sim-api-new"
        assert payload["latest_simulation"]["expected_pnl_usd"] == "1.25"


def test_control_route_payload_validation(session: Session, migrated_engine) -> None:
    _seed_operator_data(session)
    feed_state = FeedState(stale_after_seconds=30)
    runtime_controls = _runtime_controls(mode=TradingMode.DISABLED)

    with _build_client(
        migrated_engine,
        feed_state=feed_state,
        runtime_controls=runtime_controls,
    ) as client:
        invalid_mode = client.post("/controls/trading-mode", json={"mode": "unsafe"})
        assert invalid_mode.status_code == 422

        missing_active = client.post("/controls/kill-switch", json={})
        assert missing_active.status_code == 422

        unconfirmed_live = client.post("/controls/trading-mode", json={"mode": "live"})
        assert unconfirmed_live.status_code == 400


def test_api_controls_mutate_the_runtime_state_used_by_trader(session: Session, migrated_engine) -> None:
    seeded = _seed_operator_data(session)
    feed_state = FeedState(stale_after_seconds=30)
    runtime_controls = _runtime_controls(mode=TradingMode.DISABLED)
    service = TraderService(
        _session_factory_from_engine(migrated_engine),
        trading_settings=TradingSettings(enabled=False, mode=TradingMode.DISABLED, default_tif="IOC"),
        runtime_controls=runtime_controls,
    )
    opportunity = session.get(Opportunity, seeded["opportunity_id"])
    assert opportunity is not None
    decision = RiskDecision(
        approved=True,
        reason_code="approved",
        reason="approved",
        max_size_usd=Decimal("10"),
        metadata={"simulation_run_id": "sim-api-new"},
    )

    with _build_client(
        migrated_engine,
        feed_state=feed_state,
        runtime_controls=runtime_controls,
    ) as client:
        disabled_result = service.execute_opportunity(
            opportunity=opportunity,
            risk_decision=decision,
            submitted_at=datetime(2026, 4, 15, 19, 7, tzinfo=timezone.utc),
        )
        assert disabled_result.executed is False
        assert disabled_result.reason_code == "trading_disabled"

        mode_response = client.post("/controls/trading-mode", json={"mode": "paper", "reason": "operator"})
        assert mode_response.status_code == 200

        paper_result = service.execute_opportunity(
            opportunity=opportunity,
            risk_decision=decision,
            submitted_at=datetime(2026, 4, 15, 19, 8, tzinfo=timezone.utc),
        )
        assert paper_result.executed is True
        assert paper_result.trading_mode is TradingMode.PAPER

        kill_response = client.post("/controls/kill-switch", json={"active": True, "reason": "manual"})
        assert kill_response.status_code == 200

        killed_result = service.execute_opportunity(
            opportunity=opportunity,
            risk_decision=decision,
            submitted_at=datetime(2026, 4, 15, 19, 9, tzinfo=timezone.utc),
        )
        assert killed_result.executed is False
        assert killed_result.reason_code == "kill_switch_active"
