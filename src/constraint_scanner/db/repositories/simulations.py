from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from constraint_scanner.db.models import SimulatedExecution


class SimulationsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_execution(self, **values: object) -> SimulatedExecution:
        execution = SimulatedExecution(**values)
        self.session.add(execution)
        self.session.flush()
        return execution

    def list_for_opportunity(self, opportunity_id: int) -> list[SimulatedExecution]:
        stmt = (
            select(SimulatedExecution)
            .where(SimulatedExecution.opportunity_id == opportunity_id)
            .order_by(SimulatedExecution.executed_at)
        )
        return list(self.session.scalars(stmt))
