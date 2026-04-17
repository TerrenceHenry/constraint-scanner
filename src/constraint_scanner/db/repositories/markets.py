from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from constraint_scanner.db.models import Market, Token


class MarketsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_market(self, **values: object) -> Market:
        market = Market(**values)
        self.session.add(market)
        self.session.flush()
        return market

    def upsert_market(self, *, external_id: str, defaults: dict[str, object]) -> Market:
        market = self.get_market_by_external_id(external_id)
        if market is None:
            market = Market(external_id=external_id, **defaults)
            self.session.add(market)
        else:
            for field_name, field_value in defaults.items():
                setattr(market, field_name, field_value)
        self.session.flush()
        return market

    def get_market(self, market_id: int) -> Market | None:
        return self.session.get(Market, market_id)

    def get_market_by_external_id(self, external_id: str) -> Market | None:
        stmt = select(Market).where(Market.external_id == external_id)
        return self.session.scalar(stmt)

    def list_markets(self, *, limit: int = 100) -> list[Market]:
        stmt = select(Market).order_by(Market.id).limit(limit)
        return list(self.session.scalars(stmt))

    def create_token(self, **values: object) -> Token:
        token = Token(**values)
        self.session.add(token)
        self.session.flush()
        return token

    def get_token(self, token_id: int) -> Token | None:
        return self.session.get(Token, token_id)

    def get_token_by_external_id(self, external_id: str) -> Token | None:
        stmt = select(Token).where(Token.external_id == external_id)
        return self.session.scalar(stmt)

    def get_token_by_asset_id(self, asset_id: str) -> Token | None:
        stmt = select(Token).where(Token.asset_id == asset_id)
        return self.session.scalar(stmt)

    def upsert_token(self, *, external_id: str, defaults: dict[str, object]) -> Token:
        token = self.get_token_by_external_id(external_id)
        if token is None:
            token = Token(external_id=external_id, **defaults)
            self.session.add(token)
        else:
            for field_name, field_value in defaults.items():
                setattr(token, field_name, field_value)
        self.session.flush()
        return token

    def list_tokens_for_market(self, market_id: int) -> list[Token]:
        stmt = select(Token).where(Token.market_id == market_id).order_by(Token.outcome_index)
        return list(self.session.scalars(stmt))
