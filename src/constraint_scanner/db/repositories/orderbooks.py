from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from constraint_scanner.db.models import OrderbookDepth, OrderbookTop


class OrderbooksRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_top_snapshot(self, **values: object) -> OrderbookTop:
        snapshot = OrderbookTop(**values)
        self.session.add(snapshot)
        self.session.flush()
        return snapshot

    def replace_depth_snapshot(
        self,
        *,
        token_id: int,
        observed_at: datetime,
        levels: Sequence[dict[str, object]],
    ) -> list[OrderbookDepth]:
        delete_stmt = delete(OrderbookDepth).where(
            OrderbookDepth.token_id == token_id,
            OrderbookDepth.observed_at == observed_at,
        )
        self.session.execute(delete_stmt)

        created_levels: list[OrderbookDepth] = []
        for level in levels:
            record = OrderbookDepth(token_id=token_id, observed_at=observed_at, **level)
            self.session.add(record)
            created_levels.append(record)

        self.session.flush()
        return created_levels

    def get_latest_top(self, token_id: int) -> OrderbookTop | None:
        stmt = (
            select(OrderbookTop)
            .where(OrderbookTop.token_id == token_id)
            .order_by(OrderbookTop.observed_at.desc())
            .limit(1)
        )
        return self.session.scalar(stmt)

    def list_depth(self, token_id: int, observed_at: datetime) -> list[OrderbookDepth]:
        stmt = (
            select(OrderbookDepth)
            .where(OrderbookDepth.token_id == token_id, OrderbookDepth.observed_at == observed_at)
            .order_by(OrderbookDepth.side, OrderbookDepth.level)
        )
        return list(self.session.scalars(stmt))
