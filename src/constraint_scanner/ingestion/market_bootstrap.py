from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import sessionmaker

from constraint_scanner.clients.gamma_client import GammaClient
from constraint_scanner.clients.models import PolymarketMarket
from constraint_scanner.db.repositories.markets import MarketsRepository


@dataclass(frozen=True, slots=True)
class MarketBootstrapResult:
    """Summary of a market bootstrap pass."""

    market_ids: tuple[int, ...]
    token_ids: tuple[int, ...]
    tradable_market_ids: tuple[int, ...]
    tradable_token_ids: tuple[int, ...]


class MarketBootstrap:
    """Fetch public markets and upsert canonical market/token records."""

    def __init__(self, gamma_client: GammaClient, session_factory: sessionmaker) -> None:
        self._gamma_client = gamma_client
        self._session_factory = session_factory

    async def bootstrap(
        self,
        *,
        active: bool = True,
        closed: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> MarketBootstrapResult:
        """Fetch markets from Gamma and persist markets/tokens."""

        markets = await self._gamma_client.list_markets(
            active=active,
            closed=closed,
            limit=limit,
            offset=offset,
        )

        market_ids: list[int] = []
        token_ids: list[int] = []
        tradable_market_ids: list[int] = []
        tradable_token_ids: list[int] = []

        with self._session_factory() as session:
            repository = MarketsRepository(session)
            for market in markets:
                db_market = repository.upsert_market(
                    external_id=market.market_id,
                    defaults=self._market_defaults(market),
                )
                market_ids.append(db_market.id)

                extracted_token_ids: list[int] = []
                for token_index, (token_external_id, outcome_name) in enumerate(
                    zip(market.token_ids, market.outcomes, strict=False)
                ):
                    db_token = repository.upsert_token(
                        external_id=token_external_id,
                        defaults={
                            "market_id": db_market.id,
                            "symbol": outcome_name.upper(),
                            "outcome_name": outcome_name,
                            "outcome_index": token_index,
                            "raw_payload": {
                                "market_id": market.market_id,
                                "outcome_price": (
                                    str(market.outcome_prices[token_index])
                                    if token_index < len(market.outcome_prices)
                                    else None
                                ),
                            },
                        },
                    )
                    token_ids.append(db_token.id)
                    extracted_token_ids.append(db_token.id)

                if self._is_tradable(market, extracted_token_ids):
                    tradable_market_ids.append(db_market.id)
                    tradable_token_ids.extend(extracted_token_ids)

            session.commit()

        return MarketBootstrapResult(
            market_ids=tuple(market_ids),
            token_ids=tuple(token_ids),
            tradable_market_ids=tuple(tradable_market_ids),
            tradable_token_ids=tuple(tradable_token_ids),
        )

    def _market_defaults(self, market: PolymarketMarket) -> dict[str, Any]:
        status = "closed" if market.closed else "active" if market.active else "inactive"
        event_end_at = None
        if market.end_date_iso:
            text = market.end_date_iso[:-1] + "+00:00" if market.end_date_iso.endswith("Z") else market.end_date_iso
            event_end_at = datetime.fromisoformat(text)

        return {
            "venue": "polymarket",
            "slug": market.slug,
            "question": market.question,
            "description": market.description,
            "status": status,
            "event_end_at": event_end_at,
            "metadata_payload": {
                "archived": market.archived,
                "accepting_orders": market.accepting_orders,
                "enable_order_book": market.enable_order_book,
                "tags": list(market.tags),
            },
            "raw_payload": market.raw_payload,
        }

    def _is_tradable(self, market: PolymarketMarket, token_ids: list[int]) -> bool:
        return bool(
            market.active
            and not market.closed
            and market.accepting_orders is not False
            and market.enable_order_book is not False
            and token_ids
        )
