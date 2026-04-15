from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from constraint_scanner.db.models import LogicalConstraint


class ConstraintsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_constraint(self, **values: object) -> LogicalConstraint:
        constraint = LogicalConstraint(**values)
        self.session.add(constraint)
        self.session.flush()
        return constraint

    def get_constraint_by_group_and_name(self, group_id: int, name: str) -> LogicalConstraint | None:
        stmt = select(LogicalConstraint).where(
            LogicalConstraint.group_id == group_id,
            LogicalConstraint.name == name,
        )
        return self.session.scalar(stmt)

    def upsert_constraint(
        self,
        *,
        group_id: int,
        name: str,
        constraint_type: str,
        definition: dict[str, object],
        parameters: dict[str, object] | None = None,
        status: str = "active",
    ) -> LogicalConstraint:
        constraint = self.get_constraint_by_group_and_name(group_id, name)
        if constraint is None:
            constraint = LogicalConstraint(
                group_id=group_id,
                name=name,
                constraint_type=constraint_type,
                status=status,
                definition=definition,
                parameters=parameters or {},
            )
            self.session.add(constraint)
        else:
            preserved_parameters = {
                key: value
                for key, value in (constraint.parameters or {}).items()
                if key.startswith("manual_")
            }
            constraint.constraint_type = constraint_type
            constraint.status = status
            constraint.definition = definition
            merged_parameters = dict(parameters or {})
            merged_parameters.update(preserved_parameters)
            constraint.parameters = merged_parameters
        self.session.flush()
        return constraint

    def delete_generated_constraints_for_group_ids(
        self,
        group_ids: list[int],
        *,
        constraint_types: list[str],
    ) -> None:
        if not group_ids:
            return
        stmt = delete(LogicalConstraint).where(
            LogicalConstraint.group_id.in_(group_ids),
            LogicalConstraint.constraint_type.in_(constraint_types),
        )
        self.session.execute(stmt)

    def get_constraint(self, constraint_id: int) -> LogicalConstraint | None:
        return self.session.get(LogicalConstraint, constraint_id)

    def list_constraints_for_group(self, group_id: int) -> list[LogicalConstraint]:
        stmt = (
            select(LogicalConstraint)
            .where(LogicalConstraint.group_id == group_id)
            .order_by(LogicalConstraint.id)
        )
        return list(self.session.scalars(stmt))
