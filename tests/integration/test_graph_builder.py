from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from constraint_scanner.constraints.graph_builder import GraphBuilder
from constraint_scanner.core.enums import TemplateType
from constraint_scanner.db.models import LogicalConstraint
from constraint_scanner.db.repositories.constraints import ConstraintsRepository
from constraint_scanner.db.repositories.groups import GroupsRepository
from constraint_scanner.db.repositories.markets import MarketsRepository


def _session_factory_from_session(session: Session) -> sessionmaker:
    return sessionmaker(bind=session.bind, autoflush=False, expire_on_commit=False, class_=Session)


def test_graph_builder_persists_native_exact_one_constraint_and_preserves_manual_fields(session: Session) -> None:
    markets = MarketsRepository(session)
    groups = GroupsRepository(session)
    constraints = ConstraintsRepository(session)

    market = markets.create_market(
        external_id="m-native",
        slug="m-native",
        question="Who will win the election in 2028?",
        outcome_type="multi",
    )
    token_a = markets.create_token(market_id=market.id, external_id="ta", outcome_name="Alice", outcome_index=0)
    markets.create_token(market_id=market.id, external_id="tb", outcome_name="Bob", outcome_index=1)
    markets.create_token(market_id=market.id, external_id="tc", outcome_name="Carol", outcome_index=2)
    group = groups.create_group(group_key="catalog-native-1", group_type="catalog_exact", label="Election market")
    groups.add_market_to_group(group_id=group.id, market_id=market.id, member_role="auto")
    session.commit()

    constraints.create_constraint(
        group_id=group.id,
        name=f"{TemplateType.EXACT_ONE_OF_N.value}:{group.group_key}",
        constraint_type=TemplateType.EXACT_ONE_OF_N.value,
        definition={"stale": True},
        parameters={"manual_override": True, "manual_notes": "keep me"},
    )
    session.commit()

    builder = GraphBuilder(_session_factory_from_session(session))
    result = builder.run()

    session.expire_all()
    rebuilt = session.scalar(
        select(LogicalConstraint).where(
            LogicalConstraint.group_id == group.id,
            LogicalConstraint.name == f"{TemplateType.EXACT_ONE_OF_N.value}:{group.group_key}",
        )
    )

    assert result.contexts_built == 1
    assert rebuilt is not None
    assert rebuilt.constraint_type == TemplateType.EXACT_ONE_OF_N.value
    assert rebuilt.parameters is not None
    assert rebuilt.parameters["manual_override"] is True
    assert rebuilt.parameters["manual_notes"] == "keep me"
    assert rebuilt.definition["members"][0]["token_id"] == token_a.id
    assert rebuilt.definition["assumptions"]["exhaustiveness"]["basis"] == "native_market_defined"


def test_graph_builder_refuses_partial_candidate_subset_without_explicit_override(session: Session) -> None:
    markets = MarketsRepository(session)
    groups = GroupsRepository(session)

    market_a = markets.create_market(
        external_id="m-a",
        slug="m-a",
        question="Will Alice win the presidency in 2028?",
    )
    market_b = markets.create_market(
        external_id="m-b",
        slug="m-b",
        question="Will Bob win the presidency in 2028?",
    )
    markets.create_token(market_id=market_a.id, external_id="ta-yes", outcome_name="Yes", outcome_index=0)
    markets.create_token(market_id=market_a.id, external_id="ta-no", outcome_name="No", outcome_index=1)
    markets.create_token(market_id=market_b.id, external_id="tb-yes", outcome_name="Yes", outcome_index=0)
    markets.create_token(market_id=market_b.id, external_id="tb-no", outcome_name="No", outcome_index=1)
    group = groups.create_group(group_key="catalog-group-1", group_type="catalog_exact", label="Election group")
    groups.add_market_to_group(group_id=group.id, market_id=market_a.id, member_role="auto")
    groups.add_market_to_group(group_id=group.id, market_id=market_b.id, member_role="auto")
    session.commit()

    builder = GraphBuilder(_session_factory_from_session(session))
    result = builder.run()

    session.expire_all()
    constraints = list(session.scalars(select(LogicalConstraint).where(LogicalConstraint.group_id == group.id)))

    assert result.contexts_built == 0
    assert constraints == []


def test_graph_builder_allows_explicit_exhaustive_override_for_grouped_candidates(session: Session) -> None:
    markets = MarketsRepository(session)
    groups = GroupsRepository(session)

    market_a = markets.create_market(
        external_id="m-override-a",
        slug="m-override-a",
        question="Will Alice win the presidency in 2028?",
    )
    market_b = markets.create_market(
        external_id="m-override-b",
        slug="m-override-b",
        question="Will Bob win the presidency in 2028?",
    )
    token_a_yes = markets.create_token(market_id=market_a.id, external_id="toa-yes", outcome_name="Yes", outcome_index=0)
    markets.create_token(market_id=market_a.id, external_id="toa-no", outcome_name="No", outcome_index=1)
    markets.create_token(market_id=market_b.id, external_id="tob-yes", outcome_name="Yes", outcome_index=0)
    markets.create_token(market_id=market_b.id, external_id="tob-no", outcome_name="No", outcome_index=1)
    group = groups.create_group(
        group_key="catalog-group-override",
        group_type="catalog_exact",
        label="Election override group",
        criteria={"proven_exhaustive": True},
    )
    groups.add_market_to_group(group_id=group.id, market_id=market_a.id, member_role="auto")
    groups.add_market_to_group(group_id=group.id, market_id=market_b.id, member_role="auto")
    session.commit()

    builder = GraphBuilder(_session_factory_from_session(session))
    result = builder.run()

    session.expire_all()
    constraint = session.scalar(
        select(LogicalConstraint).where(
            LogicalConstraint.group_id == group.id,
            LogicalConstraint.name == f"{TemplateType.EXACT_ONE_OF_N.value}:{group.group_key}",
        )
    )

    assert result.contexts_built == 1
    assert constraint is not None
    assert constraint.definition["members"][0]["token_id"] == token_a_yes.id
    assert constraint.definition["assumptions"]["exhaustiveness"]["basis"] == "group_proven_exhaustive"
