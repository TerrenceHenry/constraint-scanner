from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from constraint_scanner.db.models import MarketGroup, MarketGroupMember


class GroupsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_group(self, **values: object) -> MarketGroup:
        group = MarketGroup(**values)
        self.session.add(group)
        self.session.flush()
        return group

    def upsert_group(self, *, group_key: str, defaults: dict[str, object]) -> MarketGroup:
        group = self.get_group_by_key(group_key)
        if group is None:
            group = MarketGroup(group_key=group_key, **defaults)
            self.session.add(group)
        else:
            for field_name, field_value in defaults.items():
                setattr(group, field_name, field_value)
        self.session.flush()
        return group

    def get_group_by_key(self, group_key: str) -> MarketGroup | None:
        stmt = select(MarketGroup).where(MarketGroup.group_key == group_key)
        return self.session.scalar(stmt)

    def add_market_to_group(self, **values: object) -> MarketGroupMember:
        member = MarketGroupMember(**values)
        self.session.add(member)
        self.session.flush()
        return member

    def replace_group_members(self, group_id: int, members: list[dict[str, object]]) -> list[MarketGroupMember]:
        self.session.execute(delete(MarketGroupMember).where(MarketGroupMember.group_id == group_id))
        created_members: list[MarketGroupMember] = []
        for member_values in members:
            member = MarketGroupMember(group_id=group_id, **member_values)
            self.session.add(member)
            created_members.append(member)
        self.session.flush()
        return created_members

    def delete_groups_by_types(self, group_types: list[str]) -> None:
        self.session.execute(delete(MarketGroup).where(MarketGroup.group_type.in_(group_types)))

    def list_group_members(self, group_id: int) -> list[MarketGroupMember]:
        stmt = (
            select(MarketGroupMember)
            .where(MarketGroupMember.group_id == group_id)
            .order_by(MarketGroupMember.id)
        )
        return list(self.session.scalars(stmt))
