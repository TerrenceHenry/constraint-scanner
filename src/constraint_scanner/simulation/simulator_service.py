from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from constraint_scanner.config.loader import get_settings
from constraint_scanner.config.models import SimulationSettings
from constraint_scanner.core.clock import utc_now
from constraint_scanner.db.models import Opportunity
from constraint_scanner.db.repositories.simulations import SimulationsRepository
from constraint_scanner.ingestion.ws_consumer import LatestBookCache
from constraint_scanner.simulation.engine import SimulationEngine


@dataclass(frozen=True, slots=True)
class SimulatorServiceResult:
    """Summary of a simulation run."""

    simulated_opportunities: int
    persisted_executions: int


class SimulatorService:
    """Run deterministic paper simulations for persisted opportunities."""

    def __init__(
        self,
        session_factory: sessionmaker,
        latest_book_cache: LatestBookCache,
        *,
        simulation_settings: SimulationSettings | None = None,
        engine: SimulationEngine | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._latest_book_cache = latest_book_cache
        active_settings = simulation_settings or get_settings().simulation
        self._engine = engine or SimulationEngine(settings=active_settings)

    def run(
        self,
        *,
        simulated_at: datetime | None = None,
        opportunity_ids: Collection[int] | None = None,
        limit: int = 100,
    ) -> SimulatorServiceResult:
        """Simulate open opportunities against the latest in-memory books."""

        active_simulated_at = simulated_at or utc_now()
        books = {token_id: polymarket_book.snapshot for token_id, polymarket_book in self._latest_book_cache.items()}

        with self._session_factory() as session:
            opportunities = self._load_opportunities(session=session, opportunity_ids=opportunity_ids, limit=limit)
            repository = SimulationsRepository(session)
            persisted_executions = 0

            for opportunity in opportunities:
                result = self._engine.simulate(
                    opportunity=opportunity,
                    books=books,
                    simulated_at=active_simulated_at,
                )
                repository.upsert_summary_execution(
                    opportunity_id=opportunity.id,
                    simulation_run_id=result.simulation_run_id,
                    defaults=self._build_summary_defaults(
                        opportunity=opportunity,
                        result=result,
                        executed_at=active_simulated_at,
                    ),
                )
                persisted_executions += 1

            session.commit()

        return SimulatorServiceResult(
            simulated_opportunities=len(opportunities),
            persisted_executions=persisted_executions,
        )

    def _load_opportunities(
        self,
        *,
        session: Session,
        opportunity_ids: Collection[int] | None,
        limit: int,
    ) -> list[Opportunity]:
        stmt = select(Opportunity).where(Opportunity.status == "open").order_by(Opportunity.detected_at.desc())
        if opportunity_ids is not None:
            stmt = stmt.where(Opportunity.id.in_(tuple(opportunity_ids)))
        else:
            stmt = stmt.limit(limit)
        return list(session.scalars(stmt))

    def _build_summary_defaults(
        self,
        *,
        opportunity: Opportunity,
        result,
        executed_at: datetime,
    ) -> dict[str, object]:
        return {
            "market_id": None,
            "token_id": None,
            "executed_at": executed_at,
            "side": None,
            "price": None,
            "quantity": None,
            "fees_usd": None,
            "pnl_impact_usd": result.expected_pnl_usd,
            "payload": {
                "record_type": "simulation_summary",
                "candidate_id": result.candidate_id,
                "simulation_run_id": result.simulation_run_id,
                "classification": result.classification.value,
                "fill_probability": str(result.fill_probability),
                "expected_pnl_usd": str(result.expected_pnl_usd),
                "downside_bound_usd": str(result.downside_bound_usd),
                "estimated_slippage_bps": str(result.estimated_slippage_bps),
                "incident_flags": list(result.incident_flags),
                "notes": list(result.notes),
                "result_json": result.details,
            },
        }
