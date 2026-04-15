from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from constraint_scanner.core.enums import TradingMode
from constraint_scanner.db.models import LogicalConstraint
from constraint_scanner.db.repositories.groups import GroupsRepository
from constraint_scanner.db.repositories.markets import MarketsRepository
from constraint_scanner.db.repositories.opportunities import OpportunitiesRepository
from constraint_scanner.db.repositories.simulations import SimulationsRepository
from constraint_scanner.risk.exposure import build_exposure_state
from constraint_scanner.risk.kill_switch import KillSwitch
from constraint_scanner.risk.policy import RiskPolicy, RiskPolicySettings


def test_risk_policy_uses_latest_authoritative_simulation_summary(session: Session) -> None:
    markets = MarketsRepository(session)
    groups = GroupsRepository(session)
    opportunities = OpportunitiesRepository(session)
    simulations = SimulationsRepository(session)

    market = markets.create_market(
        external_id="risk-m1",
        slug="risk-m1",
        question="Will risk use latest simulation?",
    )
    token = markets.create_token(
        market_id=market.id,
        external_id="risk-token-yes",
        outcome_name="YES",
        outcome_index=0,
    )
    group = groups.create_group(group_key="risk-group-1", group_type="event")
    constraint = LogicalConstraint(
        group_id=group.id,
        name="risk-constraint",
        constraint_type="binary_complement",
        definition={"kind": "binary_complement"},
    )
    session.add(constraint)
    session.flush()

    observed_at = datetime(2026, 4, 15, 15, 0, tzinfo=timezone.utc)
    opportunity = opportunities.create_opportunity(
        group_id=group.id,
        constraint_id=constraint.id,
        market_id=market.id,
        token_id=token.id,
        persistence_key="risk-opp-1",
        detected_at=observed_at,
        first_seen_at=observed_at,
        last_seen_at=observed_at,
        status="open",
        edge_bps=Decimal("40"),
        details={
            "pricing": {
                "gross_buy_cost": "100",
                "net_cost": "100",
                "legs": [
                    {
                        "market_id": market.id,
                        "token_id": token.id,
                        "side": "buy",
                        "total_notional": "100",
                    }
                ],
            },
            "ranking": {
                "confidence_score": "0.90",
            },
        },
    )

    simulations.upsert_summary_execution(
        opportunity_id=opportunity.id,
        simulation_run_id="simrun-old",
        defaults={
            "executed_at": observed_at,
            "side": None,
            "price": None,
            "quantity": None,
            "market_id": None,
            "token_id": None,
            "fees_usd": None,
            "pnl_impact_usd": Decimal("1"),
            "payload": {
                "record_type": "simulation_summary",
                "simulation_run_id": "simrun-old",
                "classification": "robust",
                "incident_flags": [],
                "result_json": {},
            },
        },
    )
    simulations.upsert_summary_execution(
        opportunity_id=opportunity.id,
        simulation_run_id="simrun-new",
        defaults={
            "executed_at": observed_at.replace(minute=5),
            "side": None,
            "price": None,
            "quantity": None,
            "market_id": None,
            "token_id": None,
            "fees_usd": None,
            "pnl_impact_usd": Decimal("0"),
            "payload": {
                "record_type": "simulation_summary",
                "simulation_run_id": "simrun-new",
                "classification": "fragile",
                "incident_flags": [],
                "result_json": {},
            },
        },
    )
    session.commit()

    policy = RiskPolicy(
        settings=RiskPolicySettings(),
        kill_switch=KillSwitch(active=False),
    )

    decision = policy.evaluate_with_repository(
        opportunity=opportunity,
        simulations_repository=simulations,
        current_exposure=build_exposure_state([]),
        trading_mode=TradingMode.PAPER,
        evaluated_at=observed_at,
    )

    assert decision.approved is False
    assert decision.reason_code == "simulation_not_robust"
    assert decision.metadata["simulation_run_id"] == "simrun-new"
