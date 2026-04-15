from __future__ import annotations

from decimal import Decimal

from constraint_scanner.constraints.template_registry import get_template_registry
from constraint_scanner.constraints.types import TemplateContext, TemplateMarketRef
from constraint_scanner.core.enums import TemplateType


def test_binary_complement_template_validate_build_and_evaluate() -> None:
    template = get_template_registry().get(TemplateType.BINARY_COMPLEMENT)
    context = TemplateContext(
        template_type=TemplateType.BINARY_COMPLEMENT,
        group_id=1,
        group_key="group-1",
        members=(
            TemplateMarketRef(1, 101, "Will Alice win?", "Yes"),
            TemplateMarketRef(2, 202, "Will Alice lose?", "Yes"),
        ),
        assumptions={"reason": "explicit complement"},
    )

    validation = template.validate(context)
    states = template.build_states(context)
    evaluation = template.evaluate(context, {101: Decimal("0.48"), 202: Decimal("0.47")})

    assert validation.valid is True
    assert len(states) == 2
    assert evaluation.total_cost == Decimal("0.95")
    assert evaluation.min_net_payoff == Decimal("0.05")
    assert evaluation.max_net_payoff == Decimal("0.05")


def test_exact_one_of_n_payoff_is_constant_across_states() -> None:
    template = get_template_registry().get(TemplateType.EXACT_ONE_OF_N)
    context = TemplateContext(
        template_type=TemplateType.EXACT_ONE_OF_N,
        group_id=2,
        group_key="group-2",
        members=(
            TemplateMarketRef(1, 101, "Will Alice win?", "Yes"),
            TemplateMarketRef(2, 102, "Will Bob win?", "Yes"),
            TemplateMarketRef(3, 103, "Will Carol win?", "Yes"),
        ),
        assumptions={"exhaustiveness": {"guaranteed": True, "basis": "native_market_defined"}},
    )

    evaluation = template.evaluate(
        context,
        {
            101: Decimal("0.31"),
            102: Decimal("0.33"),
            103: Decimal("0.29"),
        },
    )

    assert len(evaluation.state_payoffs) == 3
    assert evaluation.total_cost == Decimal("0.93")
    assert {payoff.net_payoff for payoff in evaluation.state_payoffs} == {Decimal("0.07")}


def test_one_vs_field_template_requires_explicit_roles() -> None:
    template = get_template_registry().get(TemplateType.ONE_VS_FIELD)
    invalid_context = TemplateContext(
        template_type=TemplateType.ONE_VS_FIELD,
        group_id=3,
        group_key="group-3",
        members=(
            TemplateMarketRef(1, 101, "Will Alice win?", "Yes"),
            TemplateMarketRef(2, 102, "Will Bob win?", "Yes"),
        ),
    )
    valid_context = TemplateContext(
        template_type=TemplateType.ONE_VS_FIELD,
        group_id=3,
        group_key="group-3",
        members=(
            TemplateMarketRef(1, 101, "Will Alice win?", "Yes", role="one"),
            TemplateMarketRef(2, 102, "Will the field win?", "Yes", role="field"),
        ),
        assumptions={"exhaustiveness": {"guaranteed": True, "basis": "manual_constraint_override"}},
    )

    assert template.validate(invalid_context).valid is False
    evaluation = template.evaluate(valid_context, {101: Decimal("0.42"), 102: Decimal("0.49")})
    assert len(evaluation.state_payoffs) == 2
    assert evaluation.min_net_payoff == Decimal("0.09")


def test_exact_one_of_n_rejects_missing_exhaustiveness_guarantee() -> None:
    template = get_template_registry().get(TemplateType.EXACT_ONE_OF_N)
    context = TemplateContext(
        template_type=TemplateType.EXACT_ONE_OF_N,
        group_id=4,
        group_key="group-4",
        members=(
            TemplateMarketRef(1, 101, "Will Alice win?", "Yes"),
            TemplateMarketRef(2, 102, "Will Bob win?", "Yes"),
        ),
    )

    validation = template.validate(context)

    assert validation.valid is False
    assert "explicit guaranteed exhaustiveness" in validation.issues[0]
