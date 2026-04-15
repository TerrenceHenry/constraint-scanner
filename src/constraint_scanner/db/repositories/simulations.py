from __future__ import annotations

from sqlalchemy import desc
from sqlalchemy import select
from sqlalchemy.orm import Session

from constraint_scanner.core.clock import ensure_utc
from constraint_scanner.core.ids import make_prefixed_id
from constraint_scanner.db.models import SimulatedExecution


class SimulationsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_execution(self, **values: object) -> SimulatedExecution:
        normalized = dict(values)
        if "simulation_run_id" not in normalized:
            normalized["simulation_run_id"] = make_prefixed_id(
                "legacy-simrun",
                normalized.get("opportunity_id"),
                normalized.get("market_id"),
                normalized.get("token_id"),
                ensure_utc(normalized["executed_at"]).isoformat() if "executed_at" in normalized else "unknown",
                normalized.get("side", "unknown"),
            )
        normalized.setdefault("summary_record", False)
        execution = SimulatedExecution(**normalized)
        self.session.add(execution)
        self.session.flush()
        return execution

    def create_executions(self, executions: list[dict[str, object]]) -> list[SimulatedExecution]:
        """Persist a deterministic batch of simulated execution rows."""

        return [self.create_execution(**values) for values in executions]

    def upsert_summary_execution(
        self,
        *,
        opportunity_id: int,
        simulation_run_id: str,
        defaults: dict[str, object],
    ) -> SimulatedExecution:
        """Create or update the authoritative summary row for one simulation run."""

        existing = self.get_by_run_id(
            opportunity_id=opportunity_id,
            simulation_run_id=simulation_run_id,
        )
        if existing is not None:
            existing.summary_record = True
            for field_name, field_value in defaults.items():
                setattr(existing, field_name, field_value)
            self.session.flush()
            return existing

        return self.create_execution(
            opportunity_id=opportunity_id,
            simulation_run_id=simulation_run_id,
            summary_record=True,
            **defaults,
        )

    def list_for_opportunity(self, opportunity_id: int) -> list[SimulatedExecution]:
        stmt = (
            select(SimulatedExecution)
            .where(SimulatedExecution.opportunity_id == opportunity_id)
            .order_by(SimulatedExecution.executed_at, SimulatedExecution.id)
        )
        return list(self.session.scalars(stmt))

    def list_summaries_for_opportunity(self, opportunity_id: int) -> list[SimulatedExecution]:
        """List authoritative simulation summaries for one opportunity."""

        stmt = (
            select(SimulatedExecution)
            .where(
                SimulatedExecution.opportunity_id == opportunity_id,
                SimulatedExecution.summary_record.is_(True),
            )
            .order_by(SimulatedExecution.executed_at, SimulatedExecution.id)
        )
        return list(self.session.scalars(stmt))

    def get_latest_summary_for_opportunity(self, opportunity_id: int) -> SimulatedExecution | None:
        """Return the unambiguous latest authoritative simulation result."""

        stmt = (
            select(SimulatedExecution)
            .where(
                SimulatedExecution.opportunity_id == opportunity_id,
                SimulatedExecution.summary_record.is_(True),
            )
            .order_by(desc(SimulatedExecution.executed_at), desc(SimulatedExecution.id))
            .limit(1)
        )
        return self.session.scalar(stmt)

    def get_by_run_id(self, *, opportunity_id: int, simulation_run_id: str) -> SimulatedExecution | None:
        """Return one simulation summary by stable run identifier."""

        stmt = select(SimulatedExecution).where(
            SimulatedExecution.opportunity_id == opportunity_id,
            SimulatedExecution.simulation_run_id == simulation_run_id,
        )
        return self.session.scalar(stmt)
