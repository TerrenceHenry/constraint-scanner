from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from constraint_scanner.db.base import Base
from constraint_scanner.db.types import JSON_PAYLOAD

PRICE_PRECISION = Numeric(18, 8)
SIZE_PRECISION = Numeric(24, 8)
USD_PRECISION = Numeric(18, 4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class AuditMixin(TimestampMixin):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Market(AuditMixin, Base):
    __tablename__ = "markets"
    __table_args__ = (
        UniqueConstraint("external_id"),
        UniqueConstraint("slug"),
        Index("ix_markets_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    venue: Mapped[str] = mapped_column(String(50), nullable=False, default="polymarket")
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str | None] = mapped_column(String(255))
    question: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    outcome_type: Mapped[str | None] = mapped_column(String(32))
    event_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    event_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_payload: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON_PAYLOAD)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON_PAYLOAD)

    tokens: Mapped[list["Token"]] = relationship(back_populates="market", cascade="all, delete-orphan")
    group_memberships: Mapped[list["MarketGroupMember"]] = relationship(
        back_populates="market", cascade="all, delete-orphan"
    )
    feed_messages: Mapped[list["RawFeedMessage"]] = relationship(back_populates="market")
    opportunities: Mapped[list["Opportunity"]] = relationship(back_populates="market")
    simulated_executions: Mapped[list["SimulatedExecution"]] = relationship(back_populates="market")
    live_orders: Mapped[list["LiveOrder"]] = relationship(back_populates="market")
    live_fills: Mapped[list["LiveFill"]] = relationship(back_populates="market")
    pnl_daily_entries: Mapped[list["PnlDaily"]] = relationship(back_populates="market")


class Token(AuditMixin, Base):
    __tablename__ = "tokens"
    __table_args__ = (
        UniqueConstraint("external_id"),
        UniqueConstraint("market_id", "outcome_index"),
        Index("ix_tokens_market_id", "market_id"),
        Index("ix_tokens_symbol", "symbol"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id", ondelete="CASCADE"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(64))
    outcome_name: Mapped[str] = mapped_column(String(255), nullable=False)
    outcome_index: Mapped[int] = mapped_column(Integer, nullable=False)
    condition_id: Mapped[str | None] = mapped_column(String(128))
    asset_id: Mapped[str | None] = mapped_column(String(128))
    metadata_payload: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON_PAYLOAD)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON_PAYLOAD)

    market: Mapped[Market] = relationship(back_populates="tokens")
    orderbook_tops: Mapped[list["OrderbookTop"]] = relationship(
        back_populates="token", cascade="all, delete-orphan"
    )
    orderbook_depth_levels: Mapped[list["OrderbookDepth"]] = relationship(
        back_populates="token", cascade="all, delete-orphan"
    )
    feed_messages: Mapped[list["RawFeedMessage"]] = relationship(back_populates="token")
    opportunities: Mapped[list["Opportunity"]] = relationship(back_populates="token")
    simulated_executions: Mapped[list["SimulatedExecution"]] = relationship(back_populates="token")
    live_orders: Mapped[list["LiveOrder"]] = relationship(back_populates="token")
    live_fills: Mapped[list["LiveFill"]] = relationship(back_populates="token")
    pnl_daily_entries: Mapped[list["PnlDaily"]] = relationship(back_populates="token")


class OrderbookTop(TimestampMixin, Base):
    __tablename__ = "orderbook_top"
    __table_args__ = (
        UniqueConstraint("token_id", "observed_at"),
        Index("ix_orderbook_top_token_observed", "token_id", "observed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_id: Mapped[int] = mapped_column(ForeignKey("tokens.id", ondelete="CASCADE"), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    best_bid_price: Mapped[Decimal | None] = mapped_column(PRICE_PRECISION)
    best_bid_size: Mapped[Decimal | None] = mapped_column(SIZE_PRECISION)
    best_ask_price: Mapped[Decimal | None] = mapped_column(PRICE_PRECISION)
    best_ask_size: Mapped[Decimal | None] = mapped_column(SIZE_PRECISION)
    spread_bps: Mapped[Decimal | None] = mapped_column(USD_PRECISION)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON_PAYLOAD)

    token: Mapped[Token] = relationship(back_populates="orderbook_tops")


class OrderbookDepth(TimestampMixin, Base):
    __tablename__ = "orderbook_depth"
    __table_args__ = (
        UniqueConstraint("token_id", "observed_at", "side", "level"),
        Index("ix_orderbook_depth_token_observed", "token_id", "observed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_id: Mapped[int] = mapped_column(ForeignKey("tokens.id", ondelete="CASCADE"), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal] = mapped_column(PRICE_PRECISION, nullable=False)
    size: Mapped[Decimal] = mapped_column(SIZE_PRECISION, nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON_PAYLOAD)

    token: Mapped[Token] = relationship(back_populates="orderbook_depth_levels")


class RawFeedMessage(TimestampMixin, Base):
    __tablename__ = "raw_feed_messages"
    __table_args__ = (
        Index("ix_raw_feed_messages_received_at", "received_at"),
        Index("ix_raw_feed_messages_source_channel", "source", "channel"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    channel: Mapped[str] = mapped_column(String(128), nullable=False)
    message_type: Mapped[str | None] = mapped_column(String(64))
    sequence_number: Mapped[int | None] = mapped_column(Integer)
    market_id: Mapped[int | None] = mapped_column(ForeignKey("markets.id", ondelete="SET NULL"))
    token_id: Mapped[int | None] = mapped_column(ForeignKey("tokens.id", ondelete="SET NULL"))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, nullable=False)

    market: Mapped[Market | None] = relationship(back_populates="feed_messages")
    token: Mapped[Token | None] = relationship(back_populates="feed_messages")


class MarketGroup(AuditMixin, Base):
    __tablename__ = "market_groups"
    __table_args__ = (
        UniqueConstraint("group_key"),
        Index("ix_market_groups_group_type", "group_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_key: Mapped[str] = mapped_column(String(128), nullable=False)
    group_type: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    criteria: Mapped[dict[str, Any] | None] = mapped_column(JSON_PAYLOAD)

    members: Mapped[list["MarketGroupMember"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )
    constraints: Mapped[list["LogicalConstraint"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )
    opportunities: Mapped[list["Opportunity"]] = relationship(back_populates="group")


class MarketGroupMember(TimestampMixin, Base):
    __tablename__ = "market_group_members"
    __table_args__ = (
        UniqueConstraint("group_id", "market_id"),
        Index("ix_market_group_members_market_id", "market_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("market_groups.id", ondelete="CASCADE"), nullable=False)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id", ondelete="CASCADE"), nullable=False)
    member_role: Mapped[str | None] = mapped_column(String(64))
    weight: Mapped[Decimal | None] = mapped_column(USD_PRECISION)
    metadata_payload: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON_PAYLOAD)

    group: Mapped[MarketGroup] = relationship(back_populates="members")
    market: Mapped[Market] = relationship(back_populates="group_memberships")


class LogicalConstraint(AuditMixin, Base):
    __tablename__ = "logical_constraints"
    __table_args__ = (
        Index("ix_logical_constraints_group_id", "group_id"),
        Index("ix_logical_constraints_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("market_groups.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    constraint_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    definition: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, nullable=False)
    parameters: Mapped[dict[str, Any] | None] = mapped_column(JSON_PAYLOAD)

    group: Mapped[MarketGroup | None] = relationship(back_populates="constraints")
    opportunities: Mapped[list["Opportunity"]] = relationship(back_populates="constraint")


class Opportunity(AuditMixin, Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        Index("ix_opportunities_detected_at", "detected_at"),
        Index("ix_opportunities_status", "status"),
        Index("ix_opportunities_constraint_status", "constraint_id", "status"),
        Index("ix_opportunities_scope_key", "scope_key"),
        Index(
            "uq_opportunities_open_scope_persistence",
            "scope_key",
            "persistence_key",
            unique=True,
            postgresql_where=text("status = 'open'"),
            sqlite_where=text("status = 'open'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("market_groups.id", ondelete="SET NULL"))
    constraint_id: Mapped[int | None] = mapped_column(ForeignKey("logical_constraints.id", ondelete="SET NULL"))
    market_id: Mapped[int | None] = mapped_column(ForeignKey("markets.id", ondelete="SET NULL"))
    token_id: Mapped[int | None] = mapped_column(ForeignKey("tokens.id", ondelete="SET NULL"))
    scope_key: Mapped[str] = mapped_column(String(255), nullable=False)
    persistence_key: Mapped[str] = mapped_column(String(255), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    score: Mapped[Decimal | None] = mapped_column(USD_PRECISION)
    edge_bps: Mapped[Decimal | None] = mapped_column(USD_PRECISION)
    expected_value_usd: Mapped[Decimal | None] = mapped_column(USD_PRECISION)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON_PAYLOAD)

    group: Mapped[MarketGroup | None] = relationship(back_populates="opportunities")
    constraint: Mapped[LogicalConstraint | None] = relationship(back_populates="opportunities")
    market: Mapped[Market | None] = relationship(back_populates="opportunities")
    token: Mapped[Token | None] = relationship(back_populates="opportunities")
    simulated_executions: Mapped[list["SimulatedExecution"]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan"
    )
    live_orders: Mapped[list["LiveOrder"]] = relationship(back_populates="opportunity")


class SimulatedExecution(TimestampMixin, Base):
    __tablename__ = "simulated_executions"
    __table_args__ = (
        Index("ix_simulated_executions_executed_at", "executed_at"),
        Index("ix_simulated_executions_opportunity_id", "opportunity_id"),
        Index("ix_simulated_executions_run_id", "simulation_run_id"),
        Index(
            "ix_simulated_executions_latest_summary",
            "opportunity_id",
            "summary_record",
            "executed_at",
        ),
        UniqueConstraint("opportunity_id", "simulation_run_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[int] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    simulation_run_id: Mapped[str] = mapped_column(String(255), nullable=False)
    summary_record: Mapped[bool] = mapped_column(nullable=False, default=True)
    market_id: Mapped[int | None] = mapped_column(ForeignKey("markets.id", ondelete="SET NULL"))
    token_id: Mapped[int | None] = mapped_column(ForeignKey("tokens.id", ondelete="SET NULL"))
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    side: Mapped[str | None] = mapped_column(String(8))
    price: Mapped[Decimal | None] = mapped_column(PRICE_PRECISION)
    quantity: Mapped[Decimal | None] = mapped_column(SIZE_PRECISION)
    fees_usd: Mapped[Decimal | None] = mapped_column(USD_PRECISION)
    pnl_impact_usd: Mapped[Decimal | None] = mapped_column(USD_PRECISION)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON_PAYLOAD)

    opportunity: Mapped[Opportunity] = relationship(back_populates="simulated_executions")
    market: Mapped[Market | None] = relationship(back_populates="simulated_executions")
    token: Mapped[Token | None] = relationship(back_populates="simulated_executions")


class LiveOrder(AuditMixin, Base):
    __tablename__ = "live_orders"
    __table_args__ = (
        UniqueConstraint("client_order_id"),
        UniqueConstraint("venue_order_id"),
        Index("ix_live_orders_status", "status"),
        Index("ix_live_orders_submitted_at", "submitted_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[int | None] = mapped_column(ForeignKey("opportunities.id", ondelete="SET NULL"))
    market_id: Mapped[int | None] = mapped_column(ForeignKey("markets.id", ondelete="SET NULL"))
    token_id: Mapped[int | None] = mapped_column(ForeignKey("tokens.id", ondelete="SET NULL"))
    client_order_id: Mapped[str] = mapped_column(String(128), nullable=False)
    venue_order_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    order_type: Mapped[str] = mapped_column(String(32), nullable=False, default="limit")
    price: Mapped[Decimal | None] = mapped_column(PRICE_PRECISION)
    quantity: Mapped[Decimal] = mapped_column(SIZE_PRECISION, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_request: Mapped[dict[str, Any] | None] = mapped_column(JSON_PAYLOAD)
    raw_response: Mapped[dict[str, Any] | None] = mapped_column(JSON_PAYLOAD)

    opportunity: Mapped[Opportunity | None] = relationship(back_populates="live_orders")
    market: Mapped[Market | None] = relationship(back_populates="live_orders")
    token: Mapped[Token | None] = relationship(back_populates="live_orders")
    fills: Mapped[list["LiveFill"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class LiveFill(TimestampMixin, Base):
    __tablename__ = "live_fills"
    __table_args__ = (
        UniqueConstraint("venue_fill_id"),
        Index("ix_live_fills_filled_at", "filled_at"),
        Index("ix_live_fills_order_id", "live_order_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    live_order_id: Mapped[int] = mapped_column(ForeignKey("live_orders.id", ondelete="CASCADE"), nullable=False)
    market_id: Mapped[int | None] = mapped_column(ForeignKey("markets.id", ondelete="SET NULL"))
    token_id: Mapped[int | None] = mapped_column(ForeignKey("tokens.id", ondelete="SET NULL"))
    venue_fill_id: Mapped[str] = mapped_column(String(128), nullable=False)
    filled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    price: Mapped[Decimal] = mapped_column(PRICE_PRECISION, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(SIZE_PRECISION, nullable=False)
    fee_usd: Mapped[Decimal | None] = mapped_column(USD_PRECISION)
    realized_pnl_usd: Mapped[Decimal | None] = mapped_column(USD_PRECISION)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON_PAYLOAD)

    order: Mapped[LiveOrder] = relationship(back_populates="fills")
    market: Mapped[Market | None] = relationship(back_populates="live_fills")
    token: Mapped[Token | None] = relationship(back_populates="live_fills")


class PnlDaily(AuditMixin, Base):
    __tablename__ = "pnl_daily"
    __table_args__ = (
        UniqueConstraint("as_of_date", "market_id", "token_id"),
        Index("ix_pnl_daily_as_of_date", "as_of_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    market_id: Mapped[int | None] = mapped_column(ForeignKey("markets.id", ondelete="SET NULL"))
    token_id: Mapped[int | None] = mapped_column(ForeignKey("tokens.id", ondelete="SET NULL"))
    realized_pnl_usd: Mapped[Decimal | None] = mapped_column(USD_PRECISION)
    unrealized_pnl_usd: Mapped[Decimal | None] = mapped_column(USD_PRECISION)
    fees_usd: Mapped[Decimal | None] = mapped_column(USD_PRECISION)
    net_pnl_usd: Mapped[Decimal | None] = mapped_column(USD_PRECISION)
    gross_exposure_usd: Mapped[Decimal | None] = mapped_column(USD_PRECISION)
    position_size: Mapped[Decimal | None] = mapped_column(SIZE_PRECISION)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON_PAYLOAD)

    market: Mapped[Market | None] = relationship(back_populates="pnl_daily_entries")
    token: Mapped[Token | None] = relationship(back_populates="pnl_daily_entries")
