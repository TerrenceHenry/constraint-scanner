from __future__ import annotations

from dataclasses import dataclass

from constraint_scanner.constraints.protocol import ConstraintTemplate
from constraint_scanner.constraints.templates.at_least_one import AtLeastOneTemplate
from constraint_scanner.constraints.templates.binary_complement import BinaryComplementTemplate
from constraint_scanner.constraints.templates.exact_one_of_n import ExactOneOfNTemplate
from constraint_scanner.constraints.templates.mutual_exclusion import MutualExclusionTemplate
from constraint_scanner.constraints.templates.one_vs_field import OneVsFieldTemplate
from constraint_scanner.constraints.templates.subset_superset import SubsetSupersetTemplate
from constraint_scanner.core.enums import TemplateType


@dataclass(slots=True)
class TemplateRegistry:
    """Explicit registry of available templates."""

    _templates: dict[TemplateType, ConstraintTemplate]

    def get(self, template_type: TemplateType) -> ConstraintTemplate:
        """Return the registered template instance."""

        return self._templates[template_type]

    def list_types(self) -> tuple[TemplateType, ...]:
        """Return registered template types in stable order."""

        return tuple(self._templates.keys())


def get_template_registry() -> TemplateRegistry:
    """Build the default template registry."""

    templates = {
        TemplateType.BINARY_COMPLEMENT: BinaryComplementTemplate(),
        TemplateType.EXACT_ONE_OF_N: ExactOneOfNTemplate(),
        TemplateType.ONE_VS_FIELD: OneVsFieldTemplate(),
        TemplateType.SUBSET_SUPERSET: SubsetSupersetTemplate(),
        TemplateType.MUTUAL_EXCLUSION: MutualExclusionTemplate(),
        TemplateType.AT_LEAST_ONE: AtLeastOneTemplate(),
    }
    return TemplateRegistry(templates)
