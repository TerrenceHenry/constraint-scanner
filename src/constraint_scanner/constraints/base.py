from __future__ import annotations

from decimal import Decimal

from constraint_scanner.constraints.protocol import ConstraintTemplate
from constraint_scanner.constraints.types import ConstraintState, StatePayoff, TemplateContext, TemplateEvaluation, TemplateValidation


class BaseConstraintTemplate(ConstraintTemplate):
    """Shared helpers for deterministic template evaluation."""

    def _evaluate_from_states(
        self,
        context: TemplateContext,
        pricing: dict[int, Decimal],
        *,
        states: tuple[ConstraintState, ...],
    ) -> TemplateEvaluation:
        validation = self.validate(context)
        if not validation.valid:
            raise ValueError("; ".join(validation.issues))

        total_cost = sum((pricing.get(member.token_id, Decimal("0")) for member in context.members), start=Decimal("0"))
        state_payoffs: list[StatePayoff] = []
        for state in states:
            gross_payoff = sum(state.payouts_by_token.get(member.token_id, Decimal("0")) for member in context.members)
            state_payoffs.append(
                StatePayoff(
                    state_id=state.state_id,
                    label=state.label,
                    gross_payoff=gross_payoff,
                    net_payoff=gross_payoff - total_cost,
                )
            )

        min_net = min((payoff.net_payoff for payoff in state_payoffs), default=Decimal("0"))
        max_net = max((payoff.net_payoff for payoff in state_payoffs), default=Decimal("0"))
        return TemplateEvaluation(
            template_type=context.template_type,
            total_cost=total_cost,
            state_payoffs=tuple(state_payoffs),
            min_net_payoff=min_net,
            max_net_payoff=max_net,
            assumptions=context.assumptions,
        )

    def _invalid(self, *issues: str) -> TemplateValidation:
        return TemplateValidation(valid=False, issues=tuple(issues))
