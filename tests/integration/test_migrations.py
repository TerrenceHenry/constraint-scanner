from __future__ import annotations

from sqlalchemy import inspect


def test_initial_migration_creates_expected_tables(migrated_engine) -> None:
    table_names = set(inspect(migrated_engine).get_table_names())

    assert {
        "live_fills",
        "live_orders",
        "logical_constraints",
        "market_group_members",
        "market_groups",
        "markets",
        "opportunities",
        "orderbook_depth",
        "orderbook_top",
        "pnl_daily",
        "raw_feed_messages",
        "simulated_executions",
        "tokens",
    }.issubset(table_names)

    opportunity_columns = {column["name"] for column in inspect(migrated_engine).get_columns("opportunities")}
    assert {
        "scope_key",
        "persistence_key",
        "first_seen_at",
        "last_seen_at",
        "closed_at",
    }.issubset(opportunity_columns)
