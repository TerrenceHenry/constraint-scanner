from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import selectinload, sessionmaker

from constraint_scanner.core.enums import TemplateType
from constraint_scanner.db.models import Market
from constraint_scanner.db.repositories.constraints import ConstraintsRepository
from constraint_scanner.db.repositories.groups import GroupsRepository

_WIN_PATTERN = re.compile(r"^will\s+(?P<subject>.+?)\s+win\s+(?P<anchor>.+)$", re.IGNORECASE)
_LOSE_PATTERN = re.compile(r"^will\s+(?P<subject>.+?)\s+lose\s+(?P<anchor>.+)$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ManualConstraintSeedResult:
    """Summary of example manual constraints seeded into the catalog."""

    created_groups: int
    created_constraints: int
    created_examples: tuple[str, ...]
    skipped_examples: tuple[str, ...]


def seed_example_manual_constraints(session_factory: sessionmaker) -> ManualConstraintSeedResult:
    """Seed a small deterministic set of manual example constraints from existing markets."""

    created_groups = 0
    created_constraints = 0
    created_examples: list[str] = []
    skipped_examples: list[str] = []

    with session_factory() as session:
        groups = GroupsRepository(session)
        constraints = ConstraintsRepository(session)
        markets = list(
            session.scalars(
                select(Market)
                .options(selectinload(Market.tokens))
                .order_by(Market.id.asc())
            )
        )

        native_multi_outcome = next((market for market in markets if _is_native_multi_outcome_market(market)), None)
        if native_multi_outcome is None:
            skipped_examples.append("native_exact_one_of_n:no_compatible_multi_outcome_market")
        else:
            group = groups.upsert_group(
                group_key=f"manual:native-exact-one:{native_multi_outcome.id}",
                defaults={
                    "group_type": "manual",
                    "label": f"Manual native exact-one example for market {native_multi_outcome.id}",
                    "criteria": {
                        "confidence": "1.0",
                        "manual": True,
                        "proven_exhaustive": True,
                    },
                },
            )
            groups.replace_group_members(
                group.id,
                [
                    {
                        "market_id": native_multi_outcome.id,
                        "member_role": "manual_example",
                        "metadata_payload": {"example": "native_exact_one_of_n"},
                    }
                ],
            )
            constraints.upsert_constraint(
                group_id=group.id,
                name=f"manual:exact_one_of_n:{native_multi_outcome.id}",
                constraint_type=TemplateType.EXACT_ONE_OF_N.value,
                definition={
                    "template_type": TemplateType.EXACT_ONE_OF_N.value,
                    "group_key": group.group_key,
                    "members": [
                        {
                            "market_id": native_multi_outcome.id,
                            "token_id": token.id,
                            "question": native_multi_outcome.question,
                            "outcome_name": token.outcome_name,
                            "role": "member",
                        }
                        for token in sorted(native_multi_outcome.tokens, key=lambda token: token.outcome_index)
                    ],
                    "assumptions": {
                        "reason": "manual native exact-one example",
                        "exhaustiveness": {
                            "guaranteed": True,
                            "basis": "manual_constraint_override",
                        },
                    },
                },
                parameters={
                    "manual_override": True,
                    "manual_exhaustive": True,
                    "seed_example": "native_exact_one_of_n",
                },
            )
            created_groups += 1
            created_constraints += 1
            created_examples.append("native_exact_one_of_n")

        complement_pair = _find_binary_complement_pair(markets)
        if complement_pair is None:
            skipped_examples.append("binary_complement:no_matching_win_lose_pair")
        else:
            left_market, right_market = complement_pair
            left_yes = _yes_token(left_market)
            right_yes = _yes_token(right_market)
            if left_yes is None or right_yes is None:
                skipped_examples.append("binary_complement:missing_yes_token")
            else:
                group = groups.upsert_group(
                    group_key=f"manual:binary-complement:{left_market.id}:{right_market.id}",
                    defaults={
                        "group_type": "manual",
                        "label": f"Manual binary complement example {left_market.id}/{right_market.id}",
                        "criteria": {
                            "confidence": "1.0",
                            "manual": True,
                        },
                    },
                )
                groups.replace_group_members(
                    group.id,
                    [
                        {
                            "market_id": left_market.id,
                            "member_role": "manual_example",
                            "metadata_payload": {"example": "binary_complement", "role": "left"},
                        },
                        {
                            "market_id": right_market.id,
                            "member_role": "manual_example",
                            "metadata_payload": {"example": "binary_complement", "role": "right"},
                        },
                    ],
                )
                constraints.upsert_constraint(
                    group_id=group.id,
                    name=f"manual:binary_complement:{left_market.id}:{right_market.id}",
                    constraint_type=TemplateType.BINARY_COMPLEMENT.value,
                    definition={
                        "template_type": TemplateType.BINARY_COMPLEMENT.value,
                        "group_key": group.group_key,
                        "members": [
                            {
                                "market_id": left_market.id,
                                "token_id": left_yes.id,
                                "question": left_market.question,
                                "outcome_name": left_yes.outcome_name,
                                "role": "member",
                            },
                            {
                                "market_id": right_market.id,
                                "token_id": right_yes.id,
                                "question": right_market.question,
                                "outcome_name": right_yes.outcome_name,
                                "role": "member",
                            },
                        ],
                        "assumptions": {
                            "reason": "manual binary complement example",
                            "exhaustiveness": {
                                "guaranteed": True,
                                "basis": "manual_constraint_override",
                            },
                        },
                    },
                    parameters={
                        "manual_override": True,
                        "manual_exhaustive": True,
                        "seed_example": "binary_complement",
                    },
                )
                created_groups += 1
                created_constraints += 1
                created_examples.append("binary_complement")

        session.commit()

    return ManualConstraintSeedResult(
        created_groups=created_groups,
        created_constraints=created_constraints,
        created_examples=tuple(created_examples),
        skipped_examples=tuple(skipped_examples),
    )


def _is_native_multi_outcome_market(market: Market) -> bool:
    tokens = sorted(market.tokens, key=lambda token: token.outcome_index)
    if len(tokens) < 2:
        return False
    outcome_names = {token.outcome_name.strip().lower() for token in tokens}
    return outcome_names != {"yes", "no"}


def _find_binary_complement_pair(markets: list[Market]) -> tuple[Market, Market] | None:
    binary_markets = [market for market in markets if _is_binary_yes_no_market(market)]
    for left_market in binary_markets:
        left_win = _WIN_PATTERN.match(left_market.question or "")
        left_lose = _LOSE_PATTERN.match(left_market.question or "")
        for right_market in binary_markets:
            if right_market.id == left_market.id:
                continue
            right_win = _WIN_PATTERN.match(right_market.question or "")
            right_lose = _LOSE_PATTERN.match(right_market.question or "")
            if left_win and right_lose:
                if left_win.group("subject") == right_lose.group("subject") and left_win.group("anchor") == right_lose.group("anchor"):
                    return left_market, right_market
            if left_lose and right_win:
                if left_lose.group("subject") == right_win.group("subject") and left_lose.group("anchor") == right_win.group("anchor"):
                    return left_market, right_market
    return None


def _is_binary_yes_no_market(market: Market) -> bool:
    outcome_names = {token.outcome_name.strip().lower() for token in market.tokens}
    return outcome_names == {"yes", "no"}


def _yes_token(market: Market):
    return next((token for token in market.tokens if token.outcome_name.strip().lower() == "yes"), None)
