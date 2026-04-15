from __future__ import annotations

from decimal import Decimal

from constraint_scanner.constraints.base import BaseConstraintTemplate
from constraint_scanner.constraints.types import ConstraintState, TemplateContext, TemplateEvaluation, TemplateValidation
from constraint_scanner.core.enums import TemplateType


class AtLeastOneTemplate(BaseConstraintTemplate):
    """Placeholder scaffold for future at-least-one logic."""

    template_type = TemplateType.AT_LEAST_ONE

    def validate(self, context: TemplateContext) -> TemplateValidation:
        return self._invalid("at_least_one is not implemented in v1")

    def build_states(self, context: TemplateContext) -> tuple[ConstraintState, ...]:
        raise NotImplementedError("at_least_one is a placeholder in v1")

    def evaluate(self, context: TemplateContext, pricing: dict[int, Decimal]) -> TemplateEvaluation:
        raise NotImplementedError("at_least_one is a placeholder in v1")
