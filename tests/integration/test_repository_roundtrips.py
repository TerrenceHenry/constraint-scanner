from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.exc import IntegrityError

from constraint_scanner.db.repositories import (
    ConstraintsRepository,
    GroupsRepository,
    MarketsRepository,
    OpportunitiesRepository,
    OrderbooksRepository,
    OrdersRepository,
    SimulationsRepository,
)


def test_market_and_orderbook_roundtrip(session) -> None:
    markets = MarketsRepository(session)
    orderbooks = OrderbooksRepository(session)

    market = markets.create_market(
        external_id="market-1",
        slug="market-1",
        question="Will the migration work?",
    )
    token = markets.create_token(
        market_id=market.id,
        external_id="token-yes",
        outcome_name="YES",
        outcome_index=0,
        symbol="YES",
    )

    observed_at = datetime.now(timezone.utc)
    orderbooks.create_top_snapshot(
        token_id=token.id,
        observed_at=observed_at,
        best_bid_price=Decimal("0.45"),
        best_bid_size=Decimal("100"),
        best_ask_price=Decimal("0.47"),
        best_ask_size=Decimal("120"),
        spread_bps=Decimal("20"),
        payload={"source": "test"},
    )
    orderbooks.replace_depth_snapshot(
        token_id=token.id,
        observed_at=observed_at,
        levels=[
            {"side": "ask", "level": 1, "price": Decimal("0.47"), "size": Decimal("120")},
            {"side": "bid", "level": 1, "price": Decimal("0.45"), "size": Decimal("100")},
        ],
    )
    session.commit()

    fetched_market = markets.get_market_by_external_id("market-1")
    latest_top = orderbooks.get_latest_top(token.id)
    depth = orderbooks.list_depth(token.id, observed_at)

    assert fetched_market is not None
    assert fetched_market.question == "Will the migration work?"
    assert latest_top is not None
    assert latest_top.best_ask_price == Decimal("0.47000000")
    assert [level.side for level in depth] == ["ask", "bid"]


def test_group_constraint_and_opportunity_roundtrip(session) -> None:
    markets = MarketsRepository(session)
    groups = GroupsRepository(session)
    constraints = ConstraintsRepository(session)
    opportunities = OpportunitiesRepository(session)
    simulations = SimulationsRepository(session)

    market = markets.create_market(
        external_id="market-2",
        slug="market-2",
        question="Will grouping work?",
    )
    token = markets.create_token(
        market_id=market.id,
        external_id="token-no",
        outcome_name="NO",
        outcome_index=1,
    )
    group = groups.create_group(group_key="group-1", group_type="event")
    groups.add_market_to_group(group_id=group.id, market_id=market.id, member_role="primary")
    constraint = constraints.create_constraint(
        group_id=group.id,
        name="sum-to-one",
        constraint_type="probability",
        definition={"kind": "sum_equals_one"},
    )
    opportunity = opportunities.create_opportunity(
        group_id=group.id,
        constraint_id=constraint.id,
        market_id=market.id,
        token_id=token.id,
        persistence_key="opp-roundtrip-1",
        detected_at=datetime.now(timezone.utc),
        first_seen_at=datetime.now(timezone.utc),
        last_seen_at=datetime.now(timezone.utc),
        status="open",
        score=Decimal("0.91"),
    )
    simulations.create_execution(
        opportunity_id=opportunity.id,
        market_id=market.id,
        token_id=token.id,
        executed_at=datetime.now(timezone.utc),
        side="buy",
        price=Decimal("0.42"),
        quantity=Decimal("10"),
    )
    session.commit()

    assert groups.get_group_by_key("group-1") is not None
    assert len(constraints.list_constraints_for_group(group.id)) == 1
    assert len(opportunities.list_open_opportunities()) == 1
    assert opportunity.scope_key == f"constraint:{constraint.id}"
    assert len(simulations.list_for_opportunity(opportunity.id)) == 1


def test_orders_and_fills_roundtrip(session) -> None:
    markets = MarketsRepository(session)
    orders = OrdersRepository(session)

    market = markets.create_market(
        external_id="market-3",
        slug="market-3",
        question="Will orders persist?",
    )
    token = markets.create_token(
        market_id=market.id,
        external_id="token-mid",
        outcome_name="MID",
        outcome_index=2,
    )
    order = orders.create_order(
        market_id=market.id,
        token_id=token.id,
        client_order_id="client-1",
        venue_order_id="venue-1",
        status="open",
        side="buy",
        order_type="limit",
        price=Decimal("0.50"),
        quantity=Decimal("25"),
        submitted_at=datetime.now(timezone.utc),
    )
    orders.create_fill(
        live_order_id=order.id,
        market_id=market.id,
        token_id=token.id,
        venue_fill_id="fill-1",
        filled_at=datetime.now(timezone.utc),
        price=Decimal("0.49"),
        quantity=Decimal("5"),
    )
    session.commit()

    fetched_order = orders.get_order_by_client_order_id("client-1")
    fills = orders.list_fills_for_order(order.id)

    assert fetched_order is not None
    assert fetched_order.venue_order_id == "venue-1"
    assert len(fills) == 1


def test_open_opportunity_uniqueness_is_enforced(session) -> None:
    markets = MarketsRepository(session)
    groups = GroupsRepository(session)
    constraints = ConstraintsRepository(session)
    opportunities = OpportunitiesRepository(session)

    market = markets.create_market(
        external_id="market-4",
        slug="market-4",
        question="Will uniqueness hold?",
    )
    token = markets.create_token(
        market_id=market.id,
        external_id="token-uniq",
        outcome_name="YES",
        outcome_index=0,
    )
    group = groups.create_group(group_key="group-uniq", group_type="event")
    constraint = constraints.create_constraint(
        group_id=group.id,
        name="binary_complement:group-uniq",
        constraint_type="binary_complement",
        definition={"kind": "binary_complement"},
    )
    detected_at = datetime.now(timezone.utc)

    opportunities.create_opportunity(
        group_id=group.id,
        constraint_id=constraint.id,
        market_id=market.id,
        token_id=token.id,
        persistence_key="opp-uniq",
        detected_at=detected_at,
        first_seen_at=detected_at,
        last_seen_at=detected_at,
        status="open",
    )
    session.commit()

    try:
        opportunities.create_opportunity(
            group_id=group.id,
            constraint_id=constraint.id,
            market_id=market.id,
            token_id=token.id,
            persistence_key="opp-uniq",
            detected_at=detected_at,
            first_seen_at=detected_at,
            last_seen_at=detected_at,
            status="open",
        )
    except IntegrityError:
        session.rollback()
    else:
        raise AssertionError("expected the open-opportunity uniqueness constraint to reject duplicates")


def test_summary_upsert_repairs_non_summary_row_and_latest_summary_can_see_it(session) -> None:
    markets = MarketsRepository(session)
    groups = GroupsRepository(session)
    constraints = ConstraintsRepository(session)
    opportunities = OpportunitiesRepository(session)
    simulations = SimulationsRepository(session)

    market = markets.create_market(
        external_id="market-5",
        slug="market-5",
        question="Will simulation summary repair work?",
    )
    token = markets.create_token(
        market_id=market.id,
        external_id="token-sim-repair",
        outcome_name="YES",
        outcome_index=0,
    )
    group = groups.create_group(group_key="group-sim-repair", group_type="event")
    constraint = constraints.create_constraint(
        group_id=group.id,
        name="sim-summary-repair",
        constraint_type="binary_complement",
        definition={"kind": "binary_complement"},
    )
    observed_at = datetime.now(timezone.utc)
    opportunity = opportunities.create_opportunity(
        group_id=group.id,
        constraint_id=constraint.id,
        market_id=market.id,
        token_id=token.id,
        persistence_key="opp-sim-repair",
        detected_at=observed_at,
        first_seen_at=observed_at,
        last_seen_at=observed_at,
        status="open",
    )
    repaired_run_id = "simrun-repair-1"

    existing = simulations.create_execution(
        opportunity_id=opportunity.id,
        simulation_run_id=repaired_run_id,
        summary_record=False,
        market_id=market.id,
        token_id=token.id,
        executed_at=observed_at,
        side="buy",
        price=Decimal("0.40"),
        quantity=Decimal("5"),
        payload={"record_type": "legacy_leg"},
    )
    assert existing.summary_record is False

    repaired = simulations.upsert_summary_execution(
        opportunity_id=opportunity.id,
        simulation_run_id=repaired_run_id,
        defaults={
            "executed_at": observed_at,
            "side": None,
            "price": None,
            "quantity": None,
            "market_id": None,
            "token_id": None,
            "fees_usd": None,
            "pnl_impact_usd": Decimal("1.25"),
            "payload": {"record_type": "simulation_summary", "classification": "fragile"},
        },
    )
    session.commit()

    latest = simulations.get_latest_summary_for_opportunity(opportunity.id)

    assert repaired.id == existing.id
    assert repaired.summary_record is True
    assert latest is not None
    assert latest.id == repaired.id
    assert latest.payload["record_type"] == "simulation_summary"


def test_summary_upsert_create_and_update_behavior_remains_stable(session) -> None:
    markets = MarketsRepository(session)
    groups = GroupsRepository(session)
    constraints = ConstraintsRepository(session)
    opportunities = OpportunitiesRepository(session)
    simulations = SimulationsRepository(session)

    market = markets.create_market(
        external_id="market-6",
        slug="market-6",
        question="Will summary upsert stay stable?",
    )
    token = markets.create_token(
        market_id=market.id,
        external_id="token-sim-stable",
        outcome_name="NO",
        outcome_index=1,
    )
    group = groups.create_group(group_key="group-sim-stable", group_type="event")
    constraint = constraints.create_constraint(
        group_id=group.id,
        name="sim-summary-stable",
        constraint_type="binary_complement",
        definition={"kind": "binary_complement"},
    )
    first_seen = datetime.now(timezone.utc)
    opportunity = opportunities.create_opportunity(
        group_id=group.id,
        constraint_id=constraint.id,
        market_id=market.id,
        token_id=token.id,
        persistence_key="opp-sim-stable",
        detected_at=first_seen,
        first_seen_at=first_seen,
        last_seen_at=first_seen,
        status="open",
    )
    run_id = "simrun-stable-1"

    created = simulations.upsert_summary_execution(
        opportunity_id=opportunity.id,
        simulation_run_id=run_id,
        defaults={
            "executed_at": first_seen,
            "side": None,
            "price": None,
            "quantity": None,
            "market_id": None,
            "token_id": None,
            "fees_usd": None,
            "pnl_impact_usd": Decimal("0.50"),
            "payload": {"record_type": "simulation_summary", "classification": "robust"},
        },
    )

    updated_at = datetime.now(timezone.utc)
    updated = simulations.upsert_summary_execution(
        opportunity_id=opportunity.id,
        simulation_run_id=run_id,
        defaults={
            "executed_at": updated_at,
            "side": None,
            "price": None,
            "quantity": None,
            "market_id": None,
            "token_id": None,
            "fees_usd": None,
            "pnl_impact_usd": Decimal("0.25"),
            "payload": {"record_type": "simulation_summary", "classification": "fragile"},
        },
    )
    session.commit()

    summaries = simulations.list_summaries_for_opportunity(opportunity.id)

    assert created.id == updated.id
    assert updated.summary_record is True
    assert len(summaries) == 1
    assert summaries[0].payload["classification"] == "fragile"
    assert summaries[0].pnl_impact_usd == Decimal("0.2500")
