from __future__ import annotations

from decimal import Decimal

from constraint_scanner.constraints.base import BaseConstraintTemplate
from constraint_scanner.constraints.types import (
    ConstraintState,
    TemplateContext,
    TemplateEvaluation,
    TemplateValidation,
    has_guaranteed_exhaustiveness,
)
from constraint_scanner.core.enums import TemplateType


class ExactOneOfNTemplate(BaseConstraintTemplate):
    """Exactly one member wins across an exhaustive set."""

    template_type = TemplateType.EXACT_ONE_OF_N

    def validate(self, context: TemplateContext) -> TemplateValidation:
        if context.template_type is not self.template_type:
            return self._invalid("template_type mismatch")
        if len(context.members) < 2:
            return self._invalid("exact_one_of_n requires at least two members")
        if len({member.token_id for member in context.members}) != len(context.members):
            return self._invalid("exact_one_of_n requires distinct token ids")
        if not has_guaranteed_exhaustiveness(context):
            return self._invalid("exact_one_of_n requires explicit guaranteed exhaustiveness")
        return TemplateValidation(valid=True)

    def build_states(self, context: TemplateContext) -> tuple[ConstraintState, ...]:
        validation = self.validate(context)
        if not validation.valid:
            raise ValueError("; ".join(validation.issues))

        states: list[ConstraintState] = []
        for index, winner in enumerate(context.members, start=1):
            payouts = {member.token_id: Decimal("1") if member.token_id == winner.token_id else Decimal("0") for member in context.members}
            states.append(
                ConstraintState(
                    state_id=f"winner_{index}",
                    label=f"{winner.question} wins",
                    payouts_by_token=payouts,
                )
            )
        return tuple(states)

    def evaluate(self, context: TemplateContext, pricing: dict[int, Decimal]) -> TemplateEvaluation:
        return self._evaluate_from_states(context, pricing, states=self.build_states(context))
