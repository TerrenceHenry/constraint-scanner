from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from constraint_scanner.clients.models import PolymarketBook
from constraint_scanner.config.models import SimulationSettings
from constraint_scanner.core.clock import ensure_utc
from constraint_scanner.core.types import BookLevel, BookSnapshot
from constraint_scanner.db.models import LogicalConstraint, Opportunity
from constraint_scanner.db.repositories.groups import GroupsRepository
from constraint_scanner.db.repositories.markets import MarketsRepository
from constraint_scanner.db.repositories.simulations import SimulationsRepository
from constraint_scanner.detection.detector_service import DetectorService
from constraint_scanner.ingestion.ws_consumer import LatestBookCache
from constraint_scanner.simulation.simulator_service import SimulatorService


def _session_factory_from_session(session: Session) -> sessionmaker:
    return sessionmaker(bind=session.bind, autoflush=False, expire_on_commit=False, class_=Session)


def test_simulator_service_persists_execution_rows_for_detected_opportunity(session: Session) -> None:
    markets = MarketsRepository(session)
    groups = GroupsRepository(session)

    market_a = markets.create_market(external_id="sim-m1", slug="sim-m1", question="Will Alice win?")
    market_b = markets.create_market(external_id="sim-m2", slug="sim-m2", question="Will Alice lose?")
    token_a_yes = markets.create_token(market_id=market_a.id, external_id="sim-m1-y", outcome_name="Yes", outcome_index=0)
    markets.create_token(market_id=market_a.id, external_id="sim-m1-n", outcome_name="No", outcome_index=1)
    token_b_yes = markets.create_token(market_id=market_b.id, external_id="sim-m2-y", outcome_name="Yes", outcome_index=0)
    markets.create_token(market_id=market_b.id, external_id="sim-m2-n", outcome_name="No", outcome_index=1)
    group = groups.create_group(
        group_key="sim-catalog-group",
        group_type="catalog_exact",
        label="Sim Alice group",
        criteria={"confidence": "0.90"},
    )
    groups.add_market_to_group(group_id=group.id, market_id=market_a.id, member_role="auto")
    groups.add_market_to_group(group_id=group.id, market_id=market_b.id, member_role="auto")
    session.add(
        LogicalConstraint(
            group_id=group.id,
            name="binary_complement:sim-catalog-group",
            constraint_type="binary_complement",
            definition={
                "template_type": "binary_complement",
                "group_key": group.group_key,
                "members": [
                    {
                        "market_id": market_a.id,
                        "token_id": token_a_yes.id,
                        "question": market_a.question,
                        "outcome_name": "Yes",
                        "role": "member",
                    },
                    {
                        "market_id": market_b.id,
                        "token_id": token_b_yes.id,
                        "question": market_b.question,
                        "outcome_name": "Yes",
                        "role": "member",
                    },
                ],
                "assumptions": {
                    "reason": "complement",
                    "exhaustiveness": {"guaranteed": True, "basis": "binary_complement"},
                },
            },
            parameters={},
        )
    )
    session.commit()

    cache = LatestBookCache()
    detected_at = datetime(2026, 4, 15, 13, 0, tzinfo=timezone.utc)
    cache.update(
        PolymarketBook(
            snapshot=BookSnapshot(
                token_id=token_a_yes.id,
                market_id=market_a.id,
                observed_at=detected_at,
                bids=(),
                asks=(BookLevel(price=Decimal("0.48"), size=Decimal("10")),),
                source="test",
            ),
            raw_payload={},
        )
    )
    cache.update(
        PolymarketBook(
            snapshot=BookSnapshot(
                token_id=token_b_yes.id,
                market_id=market_b.id,
                observed_at=detected_at,
                bids=(),
                asks=(BookLevel(price=Decimal("0.47"), size=Decimal("10")),),
                source="test",
            ),
            raw_payload={},
        )
    )

    detector_service = DetectorService(_session_factory_from_session(session), cache)
    detect_result = detector_service.run(detected_at=detected_at)

    simulator_service = SimulatorService(
        _session_factory_from_session(session),
        cache,
        simulation_settings=SimulationSettings(
            slippage_bps=0,
            per_extra_level_slippage_bps=0,
            stale_quote_seconds=30,
        ),
    )
    simulate_result = simulator_service.run(simulated_at=detected_at)

    second_run = datetime(2026, 4, 15, 13, 5, tzinfo=timezone.utc)
    cache.update(
        PolymarketBook(
            snapshot=BookSnapshot(
                token_id=token_a_yes.id,
                market_id=market_a.id,
                observed_at=second_run,
                bids=(),
                asks=(BookLevel(price=Decimal("0.60"), size=Decimal("10")),),
                source="test",
            ),
            raw_payload={},
        )
    )
    cache.update(
        PolymarketBook(
            snapshot=BookSnapshot(
                token_id=token_b_yes.id,
                market_id=market_b.id,
                observed_at=second_run,
                bids=(),
                asks=(BookLevel(price=Decimal("0.50"), size=Decimal("10")),),
                source="test",
            ),
            raw_payload={},
        )
    )
    second_simulate_result = simulator_service.run(simulated_at=second_run)

    session.expire_all()
    opportunity = session.scalar(select(Opportunity).limit(1))
    assert opportunity is not None
    repository = SimulationsRepository(session)
    executions = repository.list_summaries_for_opportunity(opportunity.id)
    latest = repository.get_latest_summary_for_opportunity(opportunity.id)

    assert detect_result.detected_opportunities == 1
    assert simulate_result.simulated_opportunities == 1
    assert simulate_result.persisted_executions == 1
    assert second_simulate_result.persisted_executions == 1
    assert len(executions) == 2
    assert all(execution.summary_record is True for execution in executions)
    assert executions[0].payload["record_type"] == "simulation_summary"
    assert executions[0].payload["result_json"]["pricing"]["legs"][0]["filled_quantity"] == "10"
    assert latest is not None
    assert ensure_utc(latest.executed_at) == second_run
    assert latest.payload["classification"] == "non_executable"
