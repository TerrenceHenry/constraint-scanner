"""Catalog normalization, classification, and grouping pipeline."""

from constraint_scanner.catalog.catalog_service import CatalogRunResult, CatalogService
from constraint_scanner.catalog.entity_extractor import ExtractedEntities, extract_entities
from constraint_scanner.catalog.grouping import GroupProposal, group_markets
from constraint_scanner.catalog.market_classifier import MarketClassification, classify_market
from constraint_scanner.catalog.normalizer import NormalizedMarketText, normalize_market_text

__all__ = [
    "CatalogRunResult",
    "CatalogService",
    "ExtractedEntities",
    "GroupProposal",
    "MarketClassification",
    "NormalizedMarketText",
    "classify_market",
    "extract_entities",
    "group_markets",
    "normalize_market_text",
]
