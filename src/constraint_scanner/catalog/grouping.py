from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from itertools import combinations

from constraint_scanner.catalog.entity_extractor import ExtractedEntities
from constraint_scanner.catalog.market_classifier import MarketClassification
from constraint_scanner.catalog.normalizer import NormalizedMarketText
from constraint_scanner.core.ids import make_prefixed_id

_AUTO_THRESHOLD = Decimal("0.90")
_REVIEW_THRESHOLD = Decimal("0.72")


@dataclass(frozen=True, slots=True)
class CatalogMarketRecord:
    """Catalog-ready market record for grouping."""

    market_id: int
    question: str
    description: str
    status: str
    normalized: NormalizedMarketText
    entities: ExtractedEntities
    classification: MarketClassification
    outcome_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GroupProposal:
    """Auditable group proposal with decomposed confidence."""

    group_key: str
    stage: str
    market_ids: tuple[int, ...]
    label: str
    confidence: Decimal
    confidence_components: dict[str, Decimal]
    review_required: bool
    group_type: str
    criteria: dict[str, object]


def group_markets(markets: list[CatalogMarketRecord]) -> list[GroupProposal]:
    """Run exact and lexical grouping with conservative deterministic heuristics."""

    exact_groups = _stage_exact_grouping(markets)
    assigned_market_ids = {market_id for proposal in exact_groups for market_id in proposal.market_ids}
    lexical_groups = _stage_lexical_grouping([market for market in markets if market.market_id not in assigned_market_ids])
    return [*exact_groups, *lexical_groups, *_stage_embedding_placeholder(markets)]


def _stage_exact_grouping(markets: list[CatalogMarketRecord]) -> list[GroupProposal]:
    buckets: dict[str, list[CatalogMarketRecord]] = {}
    for market in markets:
        exact_key = _make_exact_key(market)
        if exact_key is None:
            continue
        buckets.setdefault(exact_key, []).append(market)

    proposals: list[GroupProposal] = []
    for exact_key, bucket in sorted(buckets.items()):
        if len(bucket) < 2:
            continue
        market_ids = tuple(sorted(market.market_id for market in bucket))
        components = {
            "exact_key_match": Decimal("0.60"),
            "country_alignment": Decimal("0.15"),
            "office_alignment": Decimal("0.15"),
            "date_alignment": Decimal("0.10"),
        }
        confidence = sum(components.values(), start=Decimal("0"))
        proposals.append(
            GroupProposal(
                group_key=make_prefixed_id("grp", "exact", exact_key),
                stage="exact",
                market_ids=market_ids,
                label=bucket[0].question,
                confidence=confidence,
                confidence_components=components,
                review_required=False,
                group_type="catalog_exact",
                criteria={
                    "exact_key": exact_key,
                    "review_required": False,
                    "components": {key: str(value) for key, value in components.items()},
                },
            )
        )
    return proposals


def _stage_lexical_grouping(markets: list[CatalogMarketRecord]) -> list[GroupProposal]:
    proposals: list[GroupProposal] = []
    seen_groups: set[tuple[int, ...]] = set()

    for left, right in combinations(sorted(markets, key=lambda market: market.market_id), 2):
        if not _passes_anchor_guards(left, right):
            continue

        score, components = _lexical_score(left, right)
        if score < _REVIEW_THRESHOLD:
            continue

        market_ids = tuple(sorted((left.market_id, right.market_id)))
        if market_ids in seen_groups:
            continue
        seen_groups.add(market_ids)

        review_required = score < _AUTO_THRESHOLD
        proposals.append(
            GroupProposal(
                group_key=make_prefixed_id("grp", "lex", *market_ids),
                stage="lexical",
                market_ids=market_ids,
                label=left.question,
                confidence=score,
                confidence_components=components,
                review_required=review_required,
                group_type="catalog_review" if review_required else "catalog_lexical",
                criteria={
                    "review_required": review_required,
                    "components": {key: str(value) for key, value in components.items()},
                    "shared_countries": sorted(set(left.entities.countries) & set(right.entities.countries)),
                    "shared_offices": sorted(set(left.entities.offices) & set(right.entities.offices)),
                    "shared_dates": sorted(set(left.entities.dates) & set(right.entities.dates)),
                },
            )
        )

    return proposals


def _stage_embedding_placeholder(markets: list[CatalogMarketRecord]) -> list[GroupProposal]:
    """Placeholder for later embedding-based grouping, intentionally disabled in v1."""

    return []


def _make_exact_key(market: CatalogMarketRecord) -> str | None:
    countries = ",".join(sorted(market.entities.countries))
    offices = ",".join(sorted(market.entities.offices))
    years = ",".join(sorted(market.normalized.years))
    if not countries or not offices or not years:
        return None
    return "|".join((market.classification.primary_tag, countries, offices, years))


def _passes_anchor_guards(left: CatalogMarketRecord, right: CatalogMarketRecord) -> bool:
    if left.classification.outcome_structure != right.classification.outcome_structure:
        return False
    if left.entities.countries and right.entities.countries and set(left.entities.countries).isdisjoint(right.entities.countries):
        return False
    if left.entities.offices and right.entities.offices and set(left.entities.offices).isdisjoint(right.entities.offices):
        return False
    if left.normalized.years and right.normalized.years and set(left.normalized.years).isdisjoint(right.normalized.years):
        return False

    shared_anchor = bool(
        set(left.entities.countries) & set(right.entities.countries)
        or set(left.entities.offices) & set(right.entities.offices)
        or set(left.normalized.years) & set(right.normalized.years)
    )
    return shared_anchor


def _lexical_score(left: CatalogMarketRecord, right: CatalogMarketRecord) -> tuple[Decimal, dict[str, Decimal]]:
    left_tokens = set(left.normalized.lexical_tokens)
    right_tokens = set(right.normalized.lexical_tokens)
    shared_tokens = left_tokens & right_tokens
    union_tokens = left_tokens | right_tokens
    lexical_overlap = Decimal("0")
    if union_tokens:
        lexical_overlap = Decimal(str(len(shared_tokens) / len(union_tokens)))

    components = {
        "lexical_overlap": min(Decimal("0.40"), lexical_overlap * Decimal("0.40")),
        "country_alignment": Decimal("0.20") if set(left.entities.countries) & set(right.entities.countries) else Decimal("0"),
        "office_alignment": Decimal("0.20") if set(left.entities.offices) & set(right.entities.offices) else Decimal("0"),
        "date_alignment": Decimal("0.15") if set(left.normalized.years) & set(right.normalized.years) else Decimal("0"),
        "tag_alignment": Decimal("0.10") if left.classification.primary_tag == right.classification.primary_tag else Decimal("0"),
        "party_alignment": Decimal("0.05") if set(left.entities.parties) & set(right.entities.parties) else Decimal("0"),
    }
    score = sum(components.values(), start=Decimal("0"))
    return score, components
