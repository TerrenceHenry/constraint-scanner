"""Initial schema for Constraint Scanner v1."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260414_0001"
down_revision = None
branch_labels = None
depends_on = None


def json_payload_type() -> Any:
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "markets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("venue", sa.String(length=50), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("outcome_type", sa.String(length=32), nullable=True),
        sa.Column("event_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("event_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", json_payload_type(), nullable=True),
        sa.Column("raw_payload", json_payload_type(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("external_id", name="uq_markets_external_id"),
        sa.UniqueConstraint("slug", name="uq_markets_slug"),
    )
    op.create_index("ix_markets_status", "markets", ["status"])

    op.create_table(
        "market_groups",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("group_key", sa.String(length=128), nullable=False),
        sa.Column("group_type", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("criteria", json_payload_type(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("group_key", name="uq_market_groups_group_key"),
    )
    op.create_index("ix_market_groups_group_type", "market_groups", ["group_type"])

    op.create_table(
        "tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=True),
        sa.Column("outcome_name", sa.String(length=255), nullable=False),
        sa.Column("outcome_index", sa.Integer(), nullable=False),
        sa.Column("condition_id", sa.String(length=128), nullable=True),
        sa.Column("asset_id", sa.String(length=128), nullable=True),
        sa.Column("metadata", json_payload_type(), nullable=True),
        sa.Column("raw_payload", json_payload_type(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("external_id", name="uq_tokens_external_id"),
        sa.UniqueConstraint("market_id", "outcome_index", name="uq_tokens_market_id_outcome_index"),
    )
    op.create_index("ix_tokens_market_id", "tokens", ["market_id"])
    op.create_index("ix_tokens_symbol", "tokens", ["symbol"])

    op.create_table(
        "raw_feed_messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("channel", sa.String(length=128), nullable=False),
        sa.Column("message_type", sa.String(length=64), nullable=True),
        sa.Column("sequence_number", sa.Integer(), nullable=True),
        sa.Column("market_id", sa.Integer(), nullable=True),
        sa.Column("token_id", sa.Integer(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", json_payload_type(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["token_id"], ["tokens.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_raw_feed_messages_received_at", "raw_feed_messages", ["received_at"])
    op.create_index("ix_raw_feed_messages_source_channel", "raw_feed_messages", ["source", "channel"])

    op.create_table(
        "market_group_members",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("member_role", sa.String(length=64), nullable=True),
        sa.Column("weight", sa.Numeric(18, 4), nullable=True),
        sa.Column("metadata", json_payload_type(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["market_groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("group_id", "market_id", name="uq_market_group_members_group_id_market_id"),
    )
    op.create_index("ix_market_group_members_market_id", "market_group_members", ["market_id"])

    op.create_table(
        "logical_constraints",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("group_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("constraint_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("definition", json_payload_type(), nullable=False),
        sa.Column("parameters", json_payload_type(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["market_groups.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_logical_constraints_group_id", "logical_constraints", ["group_id"])
    op.create_index("ix_logical_constraints_status", "logical_constraints", ["status"])

    op.create_table(
        "opportunities",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("group_id", sa.Integer(), nullable=True),
        sa.Column("constraint_id", sa.Integer(), nullable=True),
        sa.Column("market_id", sa.Integer(), nullable=True),
        sa.Column("token_id", sa.Integer(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Numeric(18, 4), nullable=True),
        sa.Column("edge_bps", sa.Numeric(18, 4), nullable=True),
        sa.Column("expected_value_usd", sa.Numeric(18, 4), nullable=True),
        sa.Column("details", json_payload_type(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["constraint_id"], ["logical_constraints.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["group_id"], ["market_groups.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["token_id"], ["tokens.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_opportunities_detected_at", "opportunities", ["detected_at"])
    op.create_index("ix_opportunities_status", "opportunities", ["status"])

    op.create_table(
        "orderbook_top",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("token_id", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("best_bid_price", sa.Numeric(18, 8), nullable=True),
        sa.Column("best_bid_size", sa.Numeric(24, 8), nullable=True),
        sa.Column("best_ask_price", sa.Numeric(18, 8), nullable=True),
        sa.Column("best_ask_size", sa.Numeric(24, 8), nullable=True),
        sa.Column("spread_bps", sa.Numeric(18, 4), nullable=True),
        sa.Column("payload", json_payload_type(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["token_id"], ["tokens.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("token_id", "observed_at", name="uq_orderbook_top_token_id_observed_at"),
    )
    op.create_index("ix_orderbook_top_token_observed", "orderbook_top", ["token_id", "observed_at"])

    op.create_table(
        "orderbook_depth",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("token_id", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(18, 8), nullable=False),
        sa.Column("size", sa.Numeric(24, 8), nullable=False),
        sa.Column("payload", json_payload_type(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["token_id"], ["tokens.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "token_id",
            "observed_at",
            "side",
            "level",
            name="uq_orderbook_depth_token_id_observed_at_side_level",
        ),
    )
    op.create_index("ix_orderbook_depth_token_observed", "orderbook_depth", ["token_id", "observed_at"])

    op.create_table(
        "simulated_executions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("opportunity_id", sa.Integer(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=True),
        sa.Column("token_id", sa.Integer(), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("price", sa.Numeric(18, 8), nullable=False),
        sa.Column("quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("fees_usd", sa.Numeric(18, 4), nullable=True),
        sa.Column("pnl_impact_usd", sa.Numeric(18, 4), nullable=True),
        sa.Column("payload", json_payload_type(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["token_id"], ["tokens.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_simulated_executions_executed_at", "simulated_executions", ["executed_at"])
    op.create_index("ix_simulated_executions_opportunity_id", "simulated_executions", ["opportunity_id"])

    op.create_table(
        "live_orders",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("opportunity_id", sa.Integer(), nullable=True),
        sa.Column("market_id", sa.Integer(), nullable=True),
        sa.Column("token_id", sa.Integer(), nullable=True),
        sa.Column("client_order_id", sa.String(length=128), nullable=False),
        sa.Column("venue_order_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("order_type", sa.String(length=32), nullable=False),
        sa.Column("price", sa.Numeric(18, 8), nullable=True),
        sa.Column("quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_request", json_payload_type(), nullable=True),
        sa.Column("raw_response", json_payload_type(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["token_id"], ["tokens.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("client_order_id", name="uq_live_orders_client_order_id"),
        sa.UniqueConstraint("venue_order_id", name="uq_live_orders_venue_order_id"),
    )
    op.create_index("ix_live_orders_status", "live_orders", ["status"])
    op.create_index("ix_live_orders_submitted_at", "live_orders", ["submitted_at"])

    op.create_table(
        "live_fills",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("live_order_id", sa.Integer(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=True),
        sa.Column("token_id", sa.Integer(), nullable=True),
        sa.Column("venue_fill_id", sa.String(length=128), nullable=False),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price", sa.Numeric(18, 8), nullable=False),
        sa.Column("quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("fee_usd", sa.Numeric(18, 4), nullable=True),
        sa.Column("realized_pnl_usd", sa.Numeric(18, 4), nullable=True),
        sa.Column("payload", json_payload_type(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["live_order_id"], ["live_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["token_id"], ["tokens.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("venue_fill_id", name="uq_live_fills_venue_fill_id"),
    )
    op.create_index("ix_live_fills_filled_at", "live_fills", ["filled_at"])
    op.create_index("ix_live_fills_order_id", "live_fills", ["live_order_id"])

    op.create_table(
        "pnl_daily",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=True),
        sa.Column("token_id", sa.Integer(), nullable=True),
        sa.Column("realized_pnl_usd", sa.Numeric(18, 4), nullable=True),
        sa.Column("unrealized_pnl_usd", sa.Numeric(18, 4), nullable=True),
        sa.Column("fees_usd", sa.Numeric(18, 4), nullable=True),
        sa.Column("net_pnl_usd", sa.Numeric(18, 4), nullable=True),
        sa.Column("gross_exposure_usd", sa.Numeric(18, 4), nullable=True),
        sa.Column("position_size", sa.Numeric(24, 8), nullable=True),
        sa.Column("details", json_payload_type(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["token_id"], ["tokens.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("as_of_date", "market_id", "token_id", name="uq_pnl_daily_as_of_date_market_id_token_id"),
    )
    op.create_index("ix_pnl_daily_as_of_date", "pnl_daily", ["as_of_date"])


def downgrade() -> None:
    op.drop_index("ix_pnl_daily_as_of_date", table_name="pnl_daily")
    op.drop_table("pnl_daily")
    op.drop_index("ix_live_fills_order_id", table_name="live_fills")
    op.drop_index("ix_live_fills_filled_at", table_name="live_fills")
    op.drop_table("live_fills")
    op.drop_index("ix_live_orders_submitted_at", table_name="live_orders")
    op.drop_index("ix_live_orders_status", table_name="live_orders")
    op.drop_table("live_orders")
    op.drop_index("ix_simulated_executions_opportunity_id", table_name="simulated_executions")
    op.drop_index("ix_simulated_executions_executed_at", table_name="simulated_executions")
    op.drop_table("simulated_executions")
    op.drop_index("ix_orderbook_depth_token_observed", table_name="orderbook_depth")
    op.drop_table("orderbook_depth")
    op.drop_index("ix_orderbook_top_token_observed", table_name="orderbook_top")
    op.drop_table("orderbook_top")
    op.drop_index("ix_opportunities_status", table_name="opportunities")
    op.drop_index("ix_opportunities_detected_at", table_name="opportunities")
    op.drop_table("opportunities")
    op.drop_index("ix_logical_constraints_status", table_name="logical_constraints")
    op.drop_index("ix_logical_constraints_group_id", table_name="logical_constraints")
    op.drop_table("logical_constraints")
    op.drop_index("ix_market_group_members_market_id", table_name="market_group_members")
    op.drop_table("market_group_members")
    op.drop_index("ix_raw_feed_messages_source_channel", table_name="raw_feed_messages")
    op.drop_index("ix_raw_feed_messages_received_at", table_name="raw_feed_messages")
    op.drop_table("raw_feed_messages")
    op.drop_index("ix_tokens_symbol", table_name="tokens")
    op.drop_index("ix_tokens_market_id", table_name="tokens")
    op.drop_table("tokens")
    op.drop_index("ix_market_groups_group_type", table_name="market_groups")
    op.drop_table("market_groups")
    op.drop_index("ix_markets_status", table_name="markets")
    op.drop_table("markets")
