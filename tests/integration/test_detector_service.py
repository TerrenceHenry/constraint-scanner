from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from constraint_scanner.config.models import DetectionSettings
from constraint_scanner.db.models import LogicalConstraint, Opportunity
from constraint_scanner.db.repositories.groups import GroupsRepository
from constraint_scanner.db.repositories.markets import MarketsRepository
from constraint_scanner.core.clock import ensure_utc
from constraint_scanner.detection.detector_service import DetectorService
from constraint_scanner.ingestion.ws_consumer import LatestBookCache
from constraint_scanner.clients.models import PolymarketBook
from constraint_scanner.core.types import BookLevel, BookSnapshot


def _session_factory_from_session(session: Session) -> sessionmaker:
    return sessionmaker(bind=session.bind, autoflush=False, expire_on_commit=False, class_=Session)


class CaptureLogger:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def info(self, event: str, **kwargs: object) -> None:
        self.events.append((event, kwargs))


def _create_binary_complement_fixture(session: Session, *, suffix: str) -> tuple[int, int, int, int, int]:
    markets = MarketsRepository(session)
    groups = GroupsRepository(session)

    market_a = markets.create_market(external_id=f"m1-{suffix}", slug=f"m1-{suffix}", question="Will Alice win?")
    market_b = markets.create_market(external_id=f"m2-{suffix}", slug=f"m2-{suffix}", question="Will Alice lose?")
    token_a_yes = markets.create_token(market_id=market_a.id, external_id=f"m1y-{suffix}", outcome_name="Yes", outcome_index=0)
    markets.create_token(market_id=market_a.id, external_id=f"m1n-{suffix}", outcome_name="No", outcome_index=1)
    token_b_yes = markets.create_token(market_id=market_b.id, external_id=f"m2y-{suffix}", outcome_name="Yes", outcome_index=0)
    markets.create_token(market_id=market_b.id, external_id=f"m2n-{suffix}", outcome_name="No", outcome_index=1)
    group = groups.create_group(
        group_key=f"catalog-group-{suffix}",
        group_type="catalog_exact",
        label=f"Alice group {suffix}",
        criteria={"confidence": "0.90"},
    )
    groups.add_market_to_group(group_id=group.id, market_id=market_a.id, member_role="auto")
    groups.add_market_to_group(group_id=group.id, market_id=market_b.id, member_role="auto")
    session.add(
        LogicalConstraint(
            group_id=group.id,
            name=f"binary_complement:catalog-group-{suffix}",
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
    constraint = session.scalar(select(LogicalConstraint).where(LogicalConstraint.group_id == group.id))
    assert constraint is not None
    return constraint.id, market_a.id, market_b.id, token_a_yes.id, token_b_yes.id


def _seed_binary_books(
    cache: LatestBookCache,
    *,
    market_a_id: int,
    market_b_id: int,
    token_a_yes_id: int,
    token_b_yes_id: int,
    observed_at: datetime,
    ask_a: str,
    ask_b: str,
) -> None:
    cache.update(
        PolymarketBook(
            snapshot=BookSnapshot(
                token_id=token_a_yes_id,
                market_id=market_a_id,
                observed_at=observed_at,
                bids=(),
                asks=(BookLevel(price=Decimal(ask_a), size=Decimal("10")),),
                source="test",
            ),
            raw_payload={},
        )
    )
    cache.update(
        PolymarketBook(
            snapshot=BookSnapshot(
                token_id=token_b_yes_id,
                market_id=market_b_id,
                observed_at=observed_at,
                bids=(),
                asks=(BookLevel(price=Decimal(ask_b), size=Decimal("10")),),
                source="test",
            ),
            raw_payload={},
        )
    )


def _create_exact_one_fixture(session: Session, *, suffix: str) -> tuple[int, tuple[tuple[int, int], ...]]:
    markets = MarketsRepository(session)
    groups = GroupsRepository(session)

    markets_and_tokens: list[tuple[int, int, str]] = []
    for index, name in enumerate(("Alice", "Bob", "Carol"), start=1):
        market = markets.create_market(
            external_id=f"exact-{suffix}-{index}",
            slug=f"exact-{suffix}-{index}",
            question=f"Will {name} win the election in 2028?",
        )
        yes_token = markets.create_token(
            market_id=market.id,
            external_id=f"exact-{suffix}-{index}-yes",
            outcome_name="Yes",
            outcome_index=0,
        )
        markets.create_token(
            market_id=market.id,
            external_id=f"exact-{suffix}-{index}-no",
            outcome_name="No",
            outcome_index=1,
        )
        markets_and_tokens.append((market.id, yes_token.id, market.question))

    group = groups.create_group(
        group_key=f"catalog-exact-{suffix}",
        group_type="catalog_exact",
        label=f"Exact group {suffix}",
        criteria={"confidence": "0.90", "proven_exhaustive": True},
    )
    for market_id, _, _ in markets_and_tokens:
        groups.add_market_to_group(group_id=group.id, market_id=market_id, member_role="auto")

    session.add(
        LogicalConstraint(
            group_id=group.id,
            name=f"exact_one_of_n:catalog-exact-{suffix}",
            constraint_type="exact_one_of_n",
            definition={
                "template_type": "exact_one_of_n",
                "group_key": group.group_key,
                "members": [
                    {
                        "market_id": market_id,
                        "token_id": token_id,
                        "question": question,
                        "outcome_name": "Yes",
                        "role": "member",
                    }
                    for market_id, token_id, question in markets_and_tokens
                ],
                "assumptions": {
                    "reason": "explicit exact-one",
                    "exhaustiveness": {"guaranteed": True, "basis": "group_proven_exhaustive"},
                },
            },
            parameters={},
        )
    )
    session.commit()
    constraint = session.scalar(select(LogicalConstraint).where(LogicalConstraint.group_id == group.id))
    assert constraint is not None
    return constraint.id, tuple((market_id, token_id) for market_id, token_id, _ in markets_and_tokens)


def test_detector_service_persists_detected_opportunity(session: Session) -> None:
    markets = MarketsRepository(session)
    groups = GroupsRepository(session)

    market_a = markets.create_market(external_id="m1", slug="m1", question="Will Alice win?")
    market_b = markets.create_market(external_id="m2", slug="m2", question="Will Alice lose?")
    token_a_yes = markets.create_token(market_id=market_a.id, external_id="m1y", outcome_name="Yes", outcome_index=0)
    markets.create_token(market_id=market_a.id, external_id="m1n", outcome_name="No", outcome_index=1)
    token_b_yes = markets.create_token(market_id=market_b.id, external_id="m2y", outcome_name="Yes", outcome_index=0)
    markets.create_token(market_id=market_b.id, external_id="m2n", outcome_name="No", outcome_index=1)
    group = groups.create_group(
        group_key="catalog-group-1",
        group_type="catalog_exact",
        label="Alice group",
        criteria={"confidence": "0.90"},
    )
    groups.add_market_to_group(group_id=group.id, market_id=market_a.id, member_role="auto")
    groups.add_market_to_group(group_id=group.id, market_id=market_b.id, member_role="auto")
    session.add(
        LogicalConstraint(
            group_id=group.id,
            name="binary_complement:catalog-group-1",
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
                "assumptions": {"reason": "complement"},
            },
            parameters={},
        )
    )
    session.commit()

    cache = LatestBookCache()
    observed_at = datetime(2026, 4, 15, 19, 0, tzinfo=timezone.utc)
    cache.update(
        PolymarketBook(
            snapshot=BookSnapshot(
                token_id=token_a_yes.id,
                market_id=market_a.id,
                observed_at=observed_at,
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
                observed_at=observed_at,
                bids=(),
                asks=(BookLevel(price=Decimal("0.47"), size=Decimal("10")),),
                source="test",
            ),
            raw_payload={},
        )
    )

    service = DetectorService(_session_factory_from_session(session), cache)
    result = service.run(detected_at=observed_at)

    session.expire_all()
    opportunities = list(session.scalars(select(Opportunity).order_by(Opportunity.id)))

    assert result.detected_opportunities == 1
    assert len(opportunities) == 1
    assert opportunities[0].details is not None
    assert opportunities[0].status == "open"
    assert ensure_utc(opportunities[0].first_seen_at) == observed_at
    assert ensure_utc(opportunities[0].last_seen_at) == observed_at
    assert opportunities[0].closed_at is None
    assert opportunities[0].details["pricing"]["gross_buy_cost"] == "9.50"
    assert opportunities[0].details["lifecycle"]["seen_count"] == 1
    assert opportunities[0].details["pricing"]["legs"][0]["requested_quantity"] == "10"


def test_detector_service_closes_open_opportunity_when_not_observed(session: Session) -> None:
    markets = MarketsRepository(session)
    groups = GroupsRepository(session)

    market_a = markets.create_market(external_id="m1-close", slug="m1-close", question="Will Alice win?")
    market_b = markets.create_market(external_id="m2-close", slug="m2-close", question="Will Alice lose?")
    token_a_yes = markets.create_token(market_id=market_a.id, external_id="m1-close-y", outcome_name="Yes", outcome_index=0)
    markets.create_token(market_id=market_a.id, external_id="m1-close-n", outcome_name="No", outcome_index=1)
    token_b_yes = markets.create_token(market_id=market_b.id, external_id="m2-close-y", outcome_name="Yes", outcome_index=0)
    markets.create_token(market_id=market_b.id, external_id="m2-close-n", outcome_name="No", outcome_index=1)
    group = groups.create_group(
        group_key="catalog-group-close",
        group_type="catalog_exact",
        label="Alice group close",
        criteria={"confidence": "0.90"},
    )
    groups.add_market_to_group(group_id=group.id, market_id=market_a.id, member_role="auto")
    groups.add_market_to_group(group_id=group.id, market_id=market_b.id, member_role="auto")
    session.add(
        LogicalConstraint(
            group_id=group.id,
            name="binary_complement:catalog-group-close",
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
                "assumptions": {"reason": "complement"},
            },
            parameters={},
        )
    )
    session.commit()

    cache = LatestBookCache()
    first_seen = datetime(2026, 4, 15, 19, 0, tzinfo=timezone.utc)
    cache.update(
        PolymarketBook(
            snapshot=BookSnapshot(
                token_id=token_a_yes.id,
                market_id=market_a.id,
                observed_at=first_seen,
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
                observed_at=first_seen,
                bids=(),
                asks=(BookLevel(price=Decimal("0.47"), size=Decimal("10")),),
                source="test",
            ),
            raw_payload={},
        )
    )

    service = DetectorService(_session_factory_from_session(session), cache)
    service.run(detected_at=first_seen)

    second_run = datetime(2026, 4, 15, 19, 5, tzinfo=timezone.utc)
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

    service.run(detected_at=second_run)

    session.expire_all()
    opportunities = list(session.scalars(select(Opportunity).order_by(Opportunity.id)))

    assert len(opportunities) == 1
    assert opportunities[0].status == "closed"
    assert ensure_utc(opportunities[0].first_seen_at) == first_seen
    assert ensure_utc(opportunities[0].last_seen_at) == first_seen
    assert ensure_utc(opportunities[0].closed_at) == second_run
    assert opportunities[0].details["lifecycle"]["closed_at"] == second_run.isoformat()


def test_detector_service_uses_runtime_confidence_threshold_and_logs_rejection(session: Session) -> None:
    _, market_a_id, market_b_id, token_a_yes_id, token_b_yes_id = _create_binary_complement_fixture(
        session,
        suffix="cfg-confidence",
    )
    cache = LatestBookCache()
    observed_at = datetime(2026, 4, 15, 20, 0, tzinfo=timezone.utc)
    _seed_binary_books(
        cache,
        market_a_id=market_a_id,
        market_b_id=market_b_id,
        token_a_yes_id=token_a_yes_id,
        token_b_yes_id=token_b_yes_id,
        observed_at=observed_at,
        ask_a="0.48",
        ask_b="0.47",
    )
    logger = CaptureLogger()
    service = DetectorService(
        _session_factory_from_session(session),
        cache,
        detection_settings=DetectionSettings(
            confidence_threshold=0.95,
            min_edge_bps=0.0,
            max_legs=8,
        ),
        logger=logger,
    )

    result = service.run(detected_at=observed_at)

    opportunities = list(session.scalars(select(Opportunity).order_by(Opportunity.id)))
    assert result.detected_opportunities == 0
    assert result.rejected_constraints == 1
    assert opportunities == []
    assert len(logger.events) == 1
    event_name, payload = logger.events[0]
    assert event_name == "constraint_detection_rejected"
    assert payload["detector_name"] == "combinatorial"
    assert payload["template_type"] == "binary_complement"
    assert payload["reason_code"] == "confidence_below_threshold"
    assert payload["thresholds"] == {
        "confidence_threshold": "0.95",
        "min_edge_bps": "0.0",
        "max_legs": 8,
    }
    assert payload["summary_metrics"]["confidence_score"] == "0.90"


def test_detector_service_uses_runtime_min_edge_threshold(session: Session) -> None:
    _, market_a_id, market_b_id, token_a_yes_id, token_b_yes_id = _create_binary_complement_fixture(
        session,
        suffix="cfg-edge",
    )
    cache = LatestBookCache()
    observed_at = datetime(2026, 4, 15, 20, 5, tzinfo=timezone.utc)
    _seed_binary_books(
        cache,
        market_a_id=market_a_id,
        market_b_id=market_b_id,
        token_a_yes_id=token_a_yes_id,
        token_b_yes_id=token_b_yes_id,
        observed_at=observed_at,
        ask_a="0.48",
        ask_b="0.47",
    )
    service = DetectorService(
        _session_factory_from_session(session),
        cache,
        detection_settings=DetectionSettings(
            confidence_threshold=0.80,
            min_edge_bps=600.0,
            max_legs=8,
        ),
    )

    result = service.run(detected_at=observed_at)

    opportunities = list(session.scalars(select(Opportunity).order_by(Opportunity.id)))
    assert result.detected_opportunities == 0
    assert result.rejected_constraints == 1
    assert opportunities == []


def test_detector_service_uses_runtime_max_legs_threshold(session: Session) -> None:
    _, market_token_pairs = _create_exact_one_fixture(session, suffix="cfg-max-legs")
    cache = LatestBookCache()
    observed_at = datetime(2026, 4, 15, 20, 10, tzinfo=timezone.utc)
    for index, (market_id, token_id) in enumerate(market_token_pairs):
        cache.update(
            PolymarketBook(
                snapshot=BookSnapshot(
                    token_id=token_id,
                    market_id=market_id,
                    observed_at=observed_at,
                    bids=(),
                    asks=(BookLevel(price=Decimal(f"0.3{index}"), size=Decimal("10")),),
                    source="test",
                ),
                raw_payload={},
            )
        )

    service = DetectorService(
        _session_factory_from_session(session),
        cache,
        detection_settings=DetectionSettings(
            confidence_threshold=0.80,
            min_edge_bps=0.0,
            max_legs=2,
        ),
    )

    result = service.run(detected_at=observed_at)

    opportunities = list(session.scalars(select(Opportunity).order_by(Opportunity.id)))
    assert result.detected_opportunities == 0
    assert result.rejected_constraints == 1
    assert opportunities == []
