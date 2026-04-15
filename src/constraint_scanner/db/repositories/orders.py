from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from constraint_scanner.db.models import LiveFill, LiveOrder


class OrdersRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_order(self, **values: object) -> LiveOrder:
        order = LiveOrder(**values)
        self.session.add(order)
        self.session.flush()
        return order

    def create_fill(self, **values: object) -> LiveFill:
        fill = LiveFill(**values)
        self.session.add(fill)
        self.session.flush()
        return fill

    def get_order_by_client_order_id(self, client_order_id: str) -> LiveOrder | None:
        stmt = select(LiveOrder).where(LiveOrder.client_order_id == client_order_id)
        return self.session.scalar(stmt)

    def list_fills_for_order(self, order_id: int) -> list[LiveFill]:
        stmt = select(LiveFill).where(LiveFill.live_order_id == order_id).order_by(LiveFill.filled_at)
        return list(self.session.scalars(stmt))
