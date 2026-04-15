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


class OneVsFieldTemplate(BaseConstraintTemplate):
    """One named candidate versus a field bucket."""

    template_type = TemplateType.ONE_VS_FIELD

    def validate(self, context: TemplateContext) -> TemplateValidation:
        if context.template_type is not self.template_type:
            return self._invalid("template_type mismatch")
        one_members = [member for member in context.members if member.role == "one"]
        field_members = [member for member in context.members if member.role == "field"]
        if len(one_members) != 1:
            return self._invalid("one_vs_field requires exactly one 'one' member")
        if len(field_members) < 1:
            return self._invalid("one_vs_field requires at least one 'field' member")
        if len({member.token_id for member in context.members}) != len(context.members):
            return self._invalid("one_vs_field requires distinct token ids")
        if not has_guaranteed_exhaustiveness(context):
            return self._invalid("one_vs_field requires explicit guaranteed exhaustiveness")
        return TemplateValidation(valid=True)

    def build_states(self, context: TemplateContext) -> tuple[ConstraintState, ...]:
        validation = self.validate(context)
        if not validation.valid:
            raise ValueError("; ".join(validation.issues))

        one_member = next(member for member in context.members if member.role == "one")
        field_members = tuple(member for member in context.members if member.role == "field")
        states = [
            ConstraintState(
                state_id="one_wins",
                label=f"{one_member.question} wins",
                payouts_by_token={
                    member.token_id: Decimal("1") if member.token_id == one_member.token_id else Decimal("0")
                    for member in context.members
                },
            )
        ]
        for index, winner in enumerate(field_members, start=1):
            states.append(
                ConstraintState(
                    state_id=f"field_{index}",
                    label=f"{winner.question} wins",
                    payouts_by_token={
                        member.token_id: Decimal("1") if member.token_id == winner.token_id else Decimal("0")
                        for member in context.members
                    },
                )
            )
        return tuple(states)

    def evaluate(self, context: TemplateContext, pricing: dict[int, Decimal]) -> TemplateEvaluation:
        return self._evaluate_from_states(context, pricing, states=self.build_states(context))
