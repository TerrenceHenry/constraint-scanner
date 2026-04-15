from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy.orm import sessionmaker

from constraint_scanner.config.loader import get_settings
from constraint_scanner.config.models import DetectionSettings
from constraint_scanner.core.clock import utc_now
from constraint_scanner.core.enums import TemplateType
from constraint_scanner.db.repositories.opportunities import OpportunitiesRepository
from constraint_scanner.detection.combinatorial import CombinatorialDetector, CombinatorialDetectorSettings
from constraint_scanner.detection.constraint_service import ConstraintService
from constraint_scanner.detection.persistence import merge_persistence_state
from constraint_scanner.ingestion.ws_consumer import LatestBookCache


@dataclass(frozen=True, slots=True)
class DetectorServiceResult:
    """Summary of a detector run."""

    evaluated_constraints: int
    detected_opportunities: int
    rejected_constraints: int


class DetectorService:
    """Run combinatorial detection over latest books and persisted constraint state."""

    def __init__(
        self,
        session_factory: sessionmaker,
        latest_book_cache: LatestBookCache,
        *,
        detection_settings: DetectionSettings | None = None,
        detector: CombinatorialDetector | None = None,
        constraint_service: ConstraintService | None = None,
        logger: Any | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._latest_book_cache = latest_book_cache
        active_detection_settings = detection_settings or get_settings().detection
        self._detector = detector or CombinatorialDetector(
            settings=CombinatorialDetectorSettings.from_detection_settings(active_detection_settings)
        )
        self._constraint_service = constraint_service or ConstraintService()
        self._logger = logger or structlog.get_logger(__name__)

    def run(
        self,
        *,
        detected_at: datetime | None = None,
        constraint_ids: Collection[int] | None = None,
    ) -> DetectorServiceResult:
        """Evaluate persisted logical constraints against the latest book cache."""

        active_detected_at = detected_at or utc_now()
        books = {token_id: polymarket_book.snapshot for token_id, polymarket_book in self._latest_book_cache.items()}

        with self._session_factory() as session:
            constraints = self._constraint_service.load_enabled_constraints(
                session,
                template_types=(
                    TemplateType.BINARY_COMPLEMENT,
                    TemplateType.EXACT_ONE_OF_N,
                    TemplateType.ONE_VS_FIELD,
                ),
                constraint_ids=constraint_ids,
            )
            repository = OpportunitiesRepository(session)
            detected_count = 0
            rejected_count = 0

            for constraint in constraints:
                open_opportunities = repository.list_open_for_constraint(constraint.constraint_id)
                open_by_key = {
                    opportunity.persistence_key: opportunity
                    for opportunity in open_opportunities
                }
                observed_keys: set[str] = set()
                outcome = self._detector.detect(
                    context=constraint.context,
                    books=books,
                    confidence_score=constraint.confidence_score,
                    detected_at=active_detected_at,
                )
                if outcome.finding is None:
                    self._log_rejection(constraint=constraint, outcome=outcome)
                    repository.close_open_for_constraint(
                        constraint_id=constraint.constraint_id,
                        observed_persistence_keys=observed_keys,
                        closed_at=active_detected_at,
                    )
                    rejected_count += 1
                    continue

                observed_keys.add(outcome.finding.persistence_key)
                existing = open_by_key.get(outcome.finding.persistence_key)

                lifecycle = merge_persistence_state(
                    existing_details=existing.details if existing is not None else None,
                    existing_first_seen_at=existing.first_seen_at if existing is not None else None,
                    persistence_key=outcome.finding.persistence_key,
                    detected_at=active_detected_at,
                )
                details = dict(outcome.finding.detail_json)
                details["lifecycle"] = lifecycle.as_detail_json()

                repository.upsert_open_opportunity(
                    constraint_id=constraint.constraint_id,
                    persistence_key=outcome.finding.persistence_key,
                    defaults={
                        "group_id": constraint.group_id,
                        "market_id": None,
                        "token_id": None,
                        "detected_at": active_detected_at,
                        "first_seen_at": lifecycle.first_seen_at,
                        "last_seen_at": lifecycle.last_seen_at,
                        "closed_at": None,
                        "status": "open",
                        "score": outcome.finding.ranking_score,
                        "edge_bps": outcome.finding.net_edge_pct * Decimal("10000"),
                        "expected_value_usd": outcome.finding.candidate.expected_value_usd,
                        "details": details,
                    },
                )
                repository.close_open_for_constraint(
                    constraint_id=constraint.constraint_id,
                    observed_persistence_keys=observed_keys,
                    closed_at=active_detected_at,
                )
                detected_count += 1

            session.commit()

        return DetectorServiceResult(
            evaluated_constraints=len(constraints),
            detected_opportunities=detected_count,
            rejected_constraints=rejected_count,
        )

    def _log_rejection(self, *, constraint, outcome) -> None:
        rejection = outcome.rejection
        self._logger.info(
            "constraint_detection_rejected",
            constraint_id=constraint.constraint_id,
            detector_name=self._detector.detector_name,
            template_type=constraint.template_type.value,
            reason_code=rejection.reason_code if rejection is not None else "unspecified_rejection",
            reason=outcome.rejection_reason,
            thresholds=self._detector.settings.thresholds_for_log(),
            summary_metrics=rejection.summary_metrics if rejection is not None else {},
        )
