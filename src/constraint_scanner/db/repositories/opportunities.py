from __future__ import annotations

from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from sqlalchemy.orm import Session

from constraint_scanner.db.models import Opportunity


class OpportunitiesRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_opportunity(self, **values: object) -> Opportunity:
        values = self._with_scope_key(values)
        opportunity = Opportunity(**values)
        self.session.add(opportunity)
        self.session.flush()
        return opportunity

    def list_open_for_constraint(self, constraint_id: int) -> list[Opportunity]:
        stmt = (
            select(Opportunity)
            .where(
                Opportunity.constraint_id == constraint_id,
                Opportunity.status == "open",
            )
            .order_by(Opportunity.first_seen_at.asc(), Opportunity.id.asc())
        )
        return list(self.session.scalars(stmt))

    def get_open_by_persistence_key(self, *, constraint_id: int, persistence_key: str) -> Opportunity | None:
        scope_key = self._scope_key_for_constraint(constraint_id)
        stmt = select(Opportunity).where(
            Opportunity.scope_key == scope_key,
            Opportunity.persistence_key == persistence_key,
            Opportunity.status == "open",
        )
        return self.session.scalar(stmt)

    def upsert_open_opportunity(
        self,
        *,
        constraint_id: int,
        persistence_key: str,
        defaults: dict[str, object],
    ) -> Opportunity:
        scope_key = self._scope_key_for_constraint(constraint_id)
        existing = self.get_open_by_persistence_key(
            constraint_id=constraint_id,
            persistence_key=persistence_key,
        )
        if existing is not None:
            for field_name, field_value in defaults.items():
                setattr(existing, field_name, field_value)
            self.session.flush()
            return existing

        try:
            with self.session.begin_nested():
                opportunity = Opportunity(
                    constraint_id=constraint_id,
                    scope_key=scope_key,
                    persistence_key=persistence_key,
                    **defaults,
                )
                self.session.add(opportunity)
                self.session.flush()
                return opportunity
        except IntegrityError:
            existing = self.get_open_by_persistence_key(
                constraint_id=constraint_id,
                persistence_key=persistence_key,
            )
            if existing is None:
                raise
            for field_name, field_value in defaults.items():
                setattr(existing, field_name, field_value)
            self.session.flush()
            return existing

    def close_open_for_constraint(
        self,
        *,
        constraint_id: int,
        observed_persistence_keys: set[str],
        closed_at: datetime,
    ) -> list[Opportunity]:
        closed: list[Opportunity] = []
        for existing in self.list_open_for_constraint(constraint_id):
            if existing.persistence_key in observed_persistence_keys:
                continue
            existing.status = "closed"
            existing.closed_at = closed_at
            details = dict(existing.details or {})
            lifecycle = details.get("lifecycle")
            if isinstance(lifecycle, dict):
                lifecycle = dict(lifecycle)
                lifecycle["closed_at"] = closed_at.isoformat()
                details["lifecycle"] = lifecycle
                existing.details = details
            closed.append(existing)
        self.session.flush()
        return closed

    def get_opportunity(self, opportunity_id: int) -> Opportunity | None:
        return self.session.get(Opportunity, opportunity_id)

    def list_open_opportunities(self, *, limit: int = 100) -> list[Opportunity]:
        stmt = (
            select(Opportunity)
            .where(Opportunity.status == "open")
            .order_by(Opportunity.detected_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt))

    def _with_scope_key(self, values: dict[str, object]) -> dict[str, object]:
        enriched = dict(values)
        scope_key = enriched.get("scope_key")
        constraint_id = enriched.get("constraint_id")

        if scope_key is None:
            if isinstance(constraint_id, int):
                enriched["scope_key"] = self._scope_key_for_constraint(constraint_id)
            else:
                raise ValueError("opportunity persistence requires a non-null scope_key or constraint_id")
        return enriched

    def _scope_key_for_constraint(self, constraint_id: int) -> str:
        return f"constraint:{constraint_id}"
