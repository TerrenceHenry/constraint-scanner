from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from constraint_scanner.constraints.types import TemplateContext
from constraint_scanner.core.types import BookSnapshot, OpportunityCandidate


@dataclass(frozen=True, slots=True)
class RankedFinding:
    """Auditable detected opportunity plus ranking and detail payload."""

    candidate: OpportunityCandidate
    ranking_score: Decimal
    confidence_score: Decimal
    max_executable_notional: Decimal
    net_edge_pct: Decimal
    detail_json: dict[str, Any] = field(default_factory=dict)
    persistence_key: str = ""


@dataclass(frozen=True, slots=True)
class DetectionRejection:
    """Structured rejection detail for auditable detector misses."""

    reason_code: str
    reason: str
    summary_metrics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DetectionOutcome:
    """Single detector outcome with explicit rejection reason when absent."""

    finding: RankedFinding | None
    rejection_reason: str | None = None
    rejection: DetectionRejection | None = None


class DetectorBase(ABC):
    """Abstract detector interface."""

    @abstractmethod
    def detect(
        self,
        *,
        context: TemplateContext,
        books: dict[int, BookSnapshot],
        confidence_score: Decimal,
        detected_at: datetime,
    ) -> DetectionOutcome:
        """Run detection for a single context against the latest books."""
