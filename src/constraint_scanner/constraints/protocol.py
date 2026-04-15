from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal

from constraint_scanner.constraints.types import ConstraintState, TemplateContext, TemplateEvaluation, TemplateValidation
from constraint_scanner.core.enums import TemplateType


class ConstraintTemplate(ABC):
    """Small explicit interface implemented by all constraint templates."""

    template_type: TemplateType

    @abstractmethod
    def validate(self, context: TemplateContext) -> TemplateValidation:
        """Validate whether the context matches the template's assumptions."""

    @abstractmethod
    def build_states(self, context: TemplateContext) -> tuple[ConstraintState, ...]:
        """Build deterministic mutually exclusive states for evaluation."""

    @abstractmethod
    def evaluate(
        self,
        context: TemplateContext,
        pricing: dict[int, Decimal],
    ) -> TemplateEvaluation:
        """Evaluate the template against explicit token pricing."""
