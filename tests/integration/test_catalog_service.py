from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from constraint_scanner.catalog.catalog_service import CatalogService
from constraint_scanner.db.models import MarketGroup, MarketGroupMember
from constraint_scanner.db.repositories.markets import MarketsRepository


def _session_factory_from_session(session: Session) -> sessionmaker:
    return sessionmaker(bind=session.bind, autoflush=False, expire_on_commit=False, class_=Session)


def test_catalog_service_persists_groups_and_members(session: Session) -> None:
    markets = MarketsRepository(session)
    first_market = markets.create_market(
        external_id="m-1",
        slug="m-1",
        question="Will Trump win the US presidential election in 2028?",
    )
    second_market = markets.create_market(
        external_id="m-2",
        slug="m-2",
        question="Will Harris win the US presidential election in 2028?",
    )
    markets.create_token(market_id=first_market.id, external_id="t-1", outcome_name="Yes", outcome_index=0)
    markets.create_token(market_id=first_market.id, external_id="t-2", outcome_name="No", outcome_index=1)
    markets.create_token(market_id=second_market.id, external_id="t-3", outcome_name="Yes", outcome_index=0)
    markets.create_token(market_id=second_market.id, external_id="t-4", outcome_name="No", outcome_index=1)
    session.commit()

    service = CatalogService(_session_factory_from_session(session))
    result = service.run()

    groups = list(session.scalars(select(MarketGroup).order_by(MarketGroup.id)))
    members = list(session.scalars(select(MarketGroupMember).order_by(MarketGroupMember.id)))

    assert result.analyzed_markets == 2
    assert result.created_groups == 1
    assert len(groups) == 1
    assert groups[0].group_type == "catalog_exact"
    assert groups[0].criteria is not None
    assert groups[0].criteria["stage"] == "exact"
    assert len(members) == 2
