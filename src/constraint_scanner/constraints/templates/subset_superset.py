from __future__ import annotations

from decimal import Decimal

from constraint_scanner.constraints.base import BaseConstraintTemplate
from constraint_scanner.constraints.types import ConstraintState, TemplateContext, TemplateEvaluation, TemplateValidation
from constraint_scanner.core.enums import TemplateType


class SubsetSupersetTemplate(BaseConstraintTemplate):
    """Placeholder scaffold for future subset/superset logic."""

    template_type = TemplateType.SUBSET_SUPERSET

    def validate(self, context: TemplateContext) -> TemplateValidation:
        return self._invalid("subset_superset is not implemented in v1")

    def build_states(self, context: TemplateContext) -> tuple[ConstraintState, ...]:
        raise NotImplementedError("subset_superset is a placeholder in v1")

    def evaluate(self, context: TemplateContext, pricing: dict[int, Decimal]) -> TemplateEvaluation:
        raise NotImplementedError("subset_superset is a placeholder in v1")
