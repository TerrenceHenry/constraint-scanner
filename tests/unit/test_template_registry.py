from __future__ import annotations

from constraint_scanner.constraints.template_registry import get_template_registry
from constraint_scanner.constraints.templates.binary_complement import BinaryComplementTemplate
from constraint_scanner.core.enums import TemplateType


def test_template_registry_returns_expected_instances() -> None:
    registry = get_template_registry()

    assert registry.list_types()[0] is TemplateType.BINARY_COMPLEMENT
    assert isinstance(registry.get(TemplateType.BINARY_COMPLEMENT), BinaryComplementTemplate)

