from __future__ import annotations

from decimal import Decimal

from constraint_scanner.constraints.base import BaseConstraintTemplate
from constraint_scanner.constraints.types import ConstraintState, TemplateContext, TemplateEvaluation, TemplateValidation
from constraint_scanner.core.enums import TemplateType


class MutualExclusionTemplate(BaseConstraintTemplate):
    """Placeholder scaffold for future mutual-exclusion logic."""

    template_type = TemplateType.MUTUAL_EXCLUSION

    def validate(self, context: TemplateContext) -> TemplateValidation:
        return self._invalid("mutual_exclusion is not implemented in v1")

    def build_states(self, context: TemplateContext) -> tuple[ConstraintState, ...]:
        raise NotImplementedError("mutual_exclusion is a placeholder in v1")

    def evaluate(self, context: TemplateContext, pricing: dict[int, Decimal]) -> TemplateEvaluation:
        raise NotImplementedError("mutual_exclusion is a placeholder in v1")
