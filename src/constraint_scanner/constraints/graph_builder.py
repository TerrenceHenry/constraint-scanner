from __future__ import annotations

import re
from dataclasses import dataclass, replace

from sqlalchemy import select
from sqlalchemy.orm import selectinload, sessionmaker

from constraint_scanner.constraints.template_registry import TemplateRegistry, get_template_registry
from constraint_scanner.constraints.types import TemplateContext, TemplateMarketRef
from constraint_scanner.core.enums import TemplateType
from constraint_scanner.db.models import Market, MarketGroup, MarketGroupMember
from constraint_scanner.db.repositories.constraints import ConstraintsRepository

_WIN_PATTERN = re.compile(r"^will\s+(?P<subject>.+?)\s+win\s+(?P<anchor>.+)$")
_LOSE_PATTERN = re.compile(r"^will\s+(?P<subject>.+?)\s+lose\s+(?P<anchor>.+)$")
_FIELD_TERMS = ("field", "rest of field", "other candidate", "other candidates", "any other")


@dataclass(frozen=True, slots=True)
class GraphBuildResult:
    """Summary of graph builder persistence."""

    created_constraints: int
    contexts_built: int


class GraphBuilder:
    """Build explicit logical constraints from conservative grouped-market heuristics."""

    def __init__(
        self,
        session_factory: sessionmaker,
        *,
        registry: TemplateRegistry | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._registry = registry or get_template_registry()

    def run(self) -> GraphBuildResult:
        """Build and persist deterministic template instances from safe groupings."""

        with self._session_factory() as session:
            stmt = (
                select(MarketGroup)
                .options(
                    selectinload(MarketGroup.members)
                    .selectinload(MarketGroupMember.market)
                    .selectinload(Market.tokens)
                )
                .order_by(MarketGroup.id)
            )
            groups = [
                group
                for group in session.scalars(stmt)
                if group.group_type in {"catalog_exact", "catalog_lexical"}
            ]
            repository = ConstraintsRepository(session)

            built_contexts = 0
            created_constraints = 0
            for group in groups:
                context = self._build_context_for_group(group)
                if context is None:
                    continue
                context = self._with_exhaustiveness_assumptions(group, context, repository)
                template = self._registry.get(context.template_type)
                validation = template.validate(context)
                if not validation.valid:
                    continue

                constraint_name = f"{context.template_type.value}:{group.group_key}"
                repository.upsert_constraint(
                    group_id=group.id,
                    name=constraint_name,
                    constraint_type=context.template_type.value,
                    definition={
                        "template_type": context.template_type.value,
                        "group_key": context.group_key,
                        "members": [
                            {
                                "market_id": member.market_id,
                                "token_id": member.token_id,
                                "question": member.question,
                                "outcome_name": member.outcome_name,
                                "role": member.role,
                            }
                            for member in context.members
                        ],
                        "assumptions": context.assumptions,
                        "states": [
                            {
                                "state_id": state.state_id,
                                "label": state.label,
                                "payouts_by_token": {str(token_id): str(value) for token_id, value in state.payouts_by_token.items()},
                            }
                            for state in template.build_states(context)
                        ],
                    },
                    parameters={
                        "generated_by": "graph_builder_v1",
                        "manual_override": False,
                    },
                )
                built_contexts += 1
                created_constraints += 1
            session.commit()

        return GraphBuildResult(created_constraints=created_constraints, contexts_built=built_contexts)

    def _build_context_for_group(self, group: MarketGroup) -> TemplateContext | None:
        markets = [member.market for member in sorted(group.members, key=lambda item: item.market_id) if member.market is not None]
        if not markets:
            return None

        if len(markets) == 1:
            return self._native_exact_one_of_n_context(group, markets[0])

        if any(not self._is_binary_market(market) for market in markets):
            return None

        if len(markets) == 2:
            complement_context = self._binary_complement_context(group, markets)
            if complement_context is not None:
                return complement_context

        one_vs_field_context = self._one_vs_field_context(group, markets)
        if one_vs_field_context is not None:
            return one_vs_field_context

        exact_one_context = self._exact_one_of_n_context(group, markets)
        if exact_one_context is not None:
            return exact_one_context

        return None

    def _is_binary_market(self, market: Market) -> bool:
        outcomes = {token.outcome_name.strip().lower() for token in market.tokens}
        return outcomes == {"yes", "no"}

    def _yes_token_for_market(self, market: Market):
        return next((token for token in market.tokens if token.outcome_name.strip().lower() == "yes"), None)

    def _native_exact_one_of_n_context(self, group: MarketGroup, market: Market) -> TemplateContext | None:
        tokens = tuple(sorted(market.tokens, key=lambda token: token.outcome_index))
        if len(tokens) < 2:
            return None
        outcome_names = {token.outcome_name.strip().lower() for token in tokens}
        if outcome_names == {"yes", "no"}:
            return None

        return TemplateContext(
            template_type=TemplateType.EXACT_ONE_OF_N,
            group_id=group.id,
            group_key=group.group_key,
            members=tuple(
                TemplateMarketRef(
                    market_id=market.id,
                    token_id=token.id,
                    question=market.question,
                    outcome_name=token.outcome_name,
                    role="member",
                )
                for token in tokens
            ),
            assumptions={
                "source_group_type": group.group_type,
                "reason": "native market-defined multi-outcome set",
                "exhaustiveness": {
                    "guaranteed": True,
                    "basis": "native_market_defined",
                    "market_id": market.id,
                },
            },
        )

    def _binary_complement_context(self, group: MarketGroup, markets: list[Market]) -> TemplateContext | None:
        left, right = markets
        left_match = _WIN_PATTERN.match(left.question.lower())
        right_match = _LOSE_PATTERN.match(right.question.lower())
        if left_match and right_match and left_match.group("subject") == right_match.group("subject") and left_match.group("anchor") == right_match.group("anchor"):
            pass
        else:
            left_match = _LOSE_PATTERN.match(left.question.lower())
            right_match = _WIN_PATTERN.match(right.question.lower())
            if not (
                left_match
                and right_match
                and left_match.group("subject") == right_match.group("subject")
                and left_match.group("anchor") == right_match.group("anchor")
            ):
                return None

        left_token = self._yes_token_for_market(left)
        right_token = self._yes_token_for_market(right)
        if left_token is None or right_token is None:
            return None

        return TemplateContext(
            template_type=TemplateType.BINARY_COMPLEMENT,
            group_id=group.id,
            group_key=group.group_key,
            members=(
                TemplateMarketRef(left.id, left_token.id, left.question, left_token.outcome_name),
                TemplateMarketRef(right.id, right_token.id, right.question, right_token.outcome_name),
            ),
            assumptions={
                "source_group_type": group.group_type,
                "reason": "explicit win/lose complement pairing",
            },
        )

    def _one_vs_field_context(self, group: MarketGroup, markets: list[Market]) -> TemplateContext | None:
        if len(markets) != 2:
            return None
        anchor = self._shared_winner_anchor(markets)
        if anchor is None:
            return None

        one_members: list[TemplateMarketRef] = []
        field_members: list[TemplateMarketRef] = []
        for market in markets:
            yes_token = self._yes_token_for_market(market)
            if yes_token is None:
                return None
            role = "field" if any(term in market.question.lower() for term in _FIELD_TERMS) else "one"
            reference = TemplateMarketRef(market.id, yes_token.id, market.question, yes_token.outcome_name, role=role)
            if role == "field":
                field_members.append(reference)
            else:
                one_members.append(reference)

        if len(field_members) != 1 or len(one_members) != 1:
            return None

        members = (*one_members, *field_members)
        return TemplateContext(
            template_type=TemplateType.ONE_VS_FIELD,
            group_id=group.id,
            group_key=group.group_key,
            members=tuple(members),
            assumptions={
                "source_group_type": group.group_type,
                "shared_anchor": anchor,
                "reason": "winner-market anchor with explicit field member",
            },
        )

    def _exact_one_of_n_context(self, group: MarketGroup, markets: list[Market]) -> TemplateContext | None:
        anchor = self._shared_winner_anchor(markets)
        if anchor is None:
            return None
        if any(any(term in market.question.lower() for term in _FIELD_TERMS) for market in markets):
            return None

        members: list[TemplateMarketRef] = []
        for market in markets:
            yes_token = self._yes_token_for_market(market)
            if yes_token is None:
                return None
            members.append(TemplateMarketRef(market.id, yes_token.id, market.question, yes_token.outcome_name))

        return TemplateContext(
            template_type=TemplateType.EXACT_ONE_OF_N,
            group_id=group.id,
            group_key=group.group_key,
            members=tuple(members),
            assumptions={
                "source_group_type": group.group_type,
                "shared_anchor": anchor,
                "reason": "winner-market anchor shared across binary yes/no markets",
            },
        )

    def _shared_winner_anchor(self, markets: list[Market]) -> str | None:
        anchors: list[str] = []
        for market in markets:
            match = _WIN_PATTERN.match(market.question.lower())
            if match is None:
                return None
            anchors.append(match.group("anchor").strip())
        if len(set(anchors)) != 1:
            return None
        return anchors[0]

    def _with_exhaustiveness_assumptions(
        self,
        group: MarketGroup,
        context: TemplateContext,
        repository: ConstraintsRepository,
    ) -> TemplateContext:
        assumptions = dict(context.assumptions)
        if context.template_type is TemplateType.BINARY_COMPLEMENT:
            assumptions["exhaustiveness"] = {
                "guaranteed": True,
                "basis": "binary_complement",
            }
            return replace(context, assumptions=assumptions)

        existing_exhaustiveness = assumptions.get("exhaustiveness", {})
        if isinstance(existing_exhaustiveness, dict) and existing_exhaustiveness.get("guaranteed") is True:
            return context

        if self._group_has_proven_exhaustive_flag(group):
            assumptions["exhaustiveness"] = {
                "guaranteed": True,
                "basis": "group_proven_exhaustive",
            }
            return replace(context, assumptions=assumptions)

        existing = repository.get_constraint_by_group_and_name(group.id, f"{context.template_type.value}:{group.group_key}")
        parameters = existing.parameters if existing is not None else {}
        if isinstance(parameters, dict) and parameters.get("manual_exhaustive") is True:
            assumptions["exhaustiveness"] = {
                "guaranteed": True,
                "basis": "manual_constraint_override",
            }
            return replace(context, assumptions=assumptions)

        return context

    def _group_has_proven_exhaustive_flag(self, group: MarketGroup) -> bool:
        criteria = group.criteria or {}
        return isinstance(criteria, dict) and criteria.get("proven_exhaustive") is True
