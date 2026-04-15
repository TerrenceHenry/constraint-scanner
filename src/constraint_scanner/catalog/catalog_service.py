from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import sessionmaker

from constraint_scanner.catalog.entity_extractor import extract_entities
from constraint_scanner.catalog.grouping import CatalogMarketRecord, GroupProposal, group_markets
from constraint_scanner.catalog.market_classifier import classify_market
from constraint_scanner.catalog.normalizer import normalize_market_text
from constraint_scanner.db.repositories.groups import GroupsRepository
from constraint_scanner.db.repositories.markets import MarketsRepository


@dataclass(frozen=True, slots=True)
class CatalogRunResult:
    """Summary of a catalog normalization and grouping pass."""

    analyzed_markets: int
    created_groups: int
    review_groups: int


class CatalogService:
    """Run normalization and grouping, then persist catalog-owned groups."""

    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def run(self, *, limit: int = 1000) -> CatalogRunResult:
        """Normalize markets, build conservative groups, and persist them."""

        with self._session_factory() as session:
            markets_repository = MarketsRepository(session)
            groups_repository = GroupsRepository(session)
            markets = markets_repository.list_markets(limit=limit)
            catalog_records: list[CatalogMarketRecord] = []

            for market in markets:
                normalized = normalize_market_text(market.question, market.description)
                entities = extract_entities(market.question, normalized)
                outcome_names = tuple(token.outcome_name for token in sorted(market.tokens, key=lambda token: token.outcome_index))
                classification = classify_market(
                    normalized=normalized,
                    entities=entities,
                    outcome_names=outcome_names,
                )
                catalog_records.append(
                    CatalogMarketRecord(
                        market_id=market.id,
                        question=market.question,
                        description=market.description or "",
                        status=market.status,
                        normalized=normalized,
                        entities=entities,
                        classification=classification,
                        outcome_names=outcome_names,
                    )
                )

            proposals = group_markets(catalog_records)
            groups_repository.delete_groups_by_types(["catalog_exact", "catalog_lexical", "catalog_review"])
            for proposal in proposals:
                self._persist_group(groups_repository, proposal, catalog_records)
            session.commit()

        return CatalogRunResult(
            analyzed_markets=len(catalog_records),
            created_groups=len(proposals),
            review_groups=sum(1 for proposal in proposals if proposal.review_required),
        )

    def _persist_group(
        self,
        groups_repository: GroupsRepository,
        proposal: GroupProposal,
        catalog_records: list[CatalogMarketRecord],
    ) -> None:
        group = groups_repository.upsert_group(
            group_key=proposal.group_key,
            defaults={
                "group_type": proposal.group_type,
                "label": proposal.label,
                "description": f"{proposal.stage} grouping proposal",
                "criteria": proposal.criteria | {
                    "stage": proposal.stage,
                    "confidence": str(proposal.confidence),
                    "market_ids": list(proposal.market_ids),
                },
            },
        )
        member_payloads = []
        record_by_id = {record.market_id: record for record in catalog_records}
        for market_id in proposal.market_ids:
            record = record_by_id[market_id]
            member_payloads.append(
                {
                    "market_id": market_id,
                    "member_role": "review" if proposal.review_required else "auto",
                    "weight": proposal.confidence,
                    "metadata_payload": {
                        "normalized_title": record.normalized.title_normalized,
                        "countries": list(record.entities.countries),
                        "offices": list(record.entities.offices),
                        "dates": list(record.entities.dates),
                        "classification": record.classification.primary_tag,
                    },
                }
            )
        groups_repository.replace_group_members(group.id, member_payloads)
