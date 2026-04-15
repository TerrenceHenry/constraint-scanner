from __future__ import annotations

from dataclasses import dataclass

from constraint_scanner.catalog.entity_extractor import ExtractedEntities
from constraint_scanner.catalog.normalizer import NormalizedMarketText


@dataclass(frozen=True, slots=True)
class MarketClassification:
    """Simple deterministic market classification and tags."""

    outcome_structure: str
    market_type_tags: tuple[str, ...]
    primary_tag: str


def classify_market(
    *,
    normalized: NormalizedMarketText,
    entities: ExtractedEntities,
    outcome_names: tuple[str, ...],
) -> MarketClassification:
    """Classify market outcome structure and basic market type tags."""

    outcome_structure = "binary" if len(outcome_names) == 2 else "multi_outcome" if len(outcome_names) > 2 else "unknown"
    tags: list[str] = []
    text = normalized.title_normalized

    if "election" in text or entities.offices:
        tags.append("election")
    if "control" in text and ("senate" in text or "house" in text):
        tags.append("legislative_control")
    if "who will win" in text or text.startswith("who wins"):
        tags.append("winner")
    if "by " in text and normalized.date_tokens:
        tags.append("deadline")
    if not tags:
        tags.append("generic")

    return MarketClassification(
        outcome_structure=outcome_structure,
        market_type_tags=tuple(dict.fromkeys(tags)),
        primary_tag=tags[0],
    )
