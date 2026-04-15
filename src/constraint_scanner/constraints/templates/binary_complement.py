from __future__ import annotations

from decimal import Decimal

from constraint_scanner.constraints.base import BaseConstraintTemplate
from constraint_scanner.constraints.types import ConstraintState, TemplateContext, TemplateEvaluation, TemplateValidation
from constraint_scanner.core.enums import TemplateType


class BinaryComplementTemplate(BaseConstraintTemplate):
    """Two complementary binary contracts that each pay in opposite states."""

    template_type = TemplateType.BINARY_COMPLEMENT

    def validate(self, context: TemplateContext) -> TemplateValidation:
        if context.template_type is not self.template_type:
            return self._invalid("template_type mismatch")
        if len(context.members) != 2:
            return self._invalid("binary_complement requires exactly two members")
        if len({member.token_id for member in context.members}) != 2:
            return self._invalid("binary_complement requires distinct token ids")
        return TemplateValidation(valid=True)

    def build_states(self, context: TemplateContext) -> tuple[ConstraintState, ...]:
        validation = self.validate(context)
        if not validation.valid:
            raise ValueError("; ".join(validation.issues))

        left, right = context.members
        return (
            ConstraintState(
                state_id="left_true",
                label=f"{left.question} true",
                payouts_by_token={left.token_id: Decimal("1"), right.token_id: Decimal("0")},
            ),
            ConstraintState(
                state_id="right_true",
                label=f"{right.question} true",
                payouts_by_token={left.token_id: Decimal("0"), right.token_id: Decimal("1")},
            ),
        )

    def evaluate(self, context: TemplateContext, pricing: dict[int, Decimal]) -> TemplateEvaluation:
        return self._evaluate_from_states(context, pricing, states=self.build_states(context))
