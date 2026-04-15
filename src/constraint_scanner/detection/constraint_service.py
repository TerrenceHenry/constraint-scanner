from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from constraint_scanner.constraints.types import TemplateContext, TemplateMarketRef
from constraint_scanner.core.enums import TemplateType
from constraint_scanner.db.models import LogicalConstraint


@dataclass(frozen=True, slots=True)
class LoadedConstraint:
    """Detector-ready logical constraint with normalized context metadata."""

    constraint_id: int
    group_id: int | None
    template_type: TemplateType
    context: TemplateContext
    confidence_score: Decimal


class ConstraintService:
    """Load active logical constraints and normalize them for detector use."""

    def load_enabled_constraints(
        self,
        session: Session,
        *,
        template_types: Collection[TemplateType] | None = None,
        constraint_ids: Collection[int] | None = None,
    ) -> tuple[LoadedConstraint, ...]:
        """Return active logical constraints as detector-ready contexts."""

        stmt = (
            select(LogicalConstraint)
            .options(selectinload(LogicalConstraint.group))
            .where(LogicalConstraint.status == "active")
            .order_by(LogicalConstraint.id)
        )
        if constraint_ids:
            stmt = stmt.where(LogicalConstraint.id.in_(tuple(constraint_ids)))

        allowed_template_types = tuple(template_types) if template_types is not None else None
        loaded: list[LoadedConstraint] = []
        for constraint in session.scalars(stmt):
            try:
                template_type = TemplateType(constraint.constraint_type)
            except ValueError:
                continue
            if allowed_template_types is not None and template_type not in allowed_template_types:
                continue

            loaded.append(
                LoadedConstraint(
                    constraint_id=constraint.id,
                    group_id=constraint.group_id,
                    template_type=template_type,
                    context=self._context_from_constraint(constraint),
                    confidence_score=self._confidence_from_constraint(constraint),
                )
            )
        return tuple(loaded)

    def _context_from_constraint(self, constraint: LogicalConstraint) -> TemplateContext:
        definition = constraint.definition
        members = tuple(
            TemplateMarketRef(
                market_id=int(member["market_id"]),
                token_id=int(member["token_id"]),
                question=str(member["question"]),
                outcome_name=str(member["outcome_name"]),
                role=str(member.get("role", "member")),
            )
            for member in definition["members"]
        )
        return TemplateContext(
            template_type=TemplateType(definition["template_type"]),
            group_id=constraint.group_id,
            group_key=str(definition["group_key"]),
            members=members,
            assumptions=dict(definition.get("assumptions", {})),
        )

    def _confidence_from_constraint(self, constraint: LogicalConstraint) -> Decimal:
        group = constraint.group
        if group is None or group.criteria is None:
            return Decimal("1")
        value = group.criteria.get("confidence")
        return Decimal(str(value)) if value is not None else Decimal("1")
