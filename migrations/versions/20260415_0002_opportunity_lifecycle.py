"""Add opportunity lifecycle fields and open-row uniqueness."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260415_0002"
down_revision = "20260414_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("opportunities", sa.Column("persistence_key", sa.String(length=255), nullable=True))
    op.add_column("opportunities", sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("opportunities", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("opportunities", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))

    op.execute(
        sa.text(
            """
            UPDATE opportunities
            SET persistence_key = :prefix || CAST(id AS TEXT),
                first_seen_at = detected_at,
                last_seen_at = detected_at
            WHERE persistence_key IS NULL
            """
        ).bindparams(prefix="legacy_")
    )

    with op.batch_alter_table("opportunities") as batch_op:
        batch_op.alter_column("persistence_key", existing_type=sa.String(length=255), nullable=False)
        batch_op.alter_column("first_seen_at", existing_type=sa.DateTime(timezone=True), nullable=False)
        batch_op.alter_column("last_seen_at", existing_type=sa.DateTime(timezone=True), nullable=False)

    op.create_index(
        "ix_opportunities_constraint_status",
        "opportunities",
        ["constraint_id", "status"],
    )
    op.create_index(
        "uq_opportunities_open_constraint_persistence",
        "opportunities",
        ["constraint_id", "persistence_key"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
        sqlite_where=sa.text("status = 'open'"),
    )


def downgrade() -> None:
    op.drop_index("uq_opportunities_open_constraint_persistence", table_name="opportunities")
    op.drop_index("ix_opportunities_constraint_status", table_name="opportunities")

    with op.batch_alter_table("opportunities") as batch_op:
        batch_op.drop_column("closed_at")
        batch_op.drop_column("last_seen_at")
        batch_op.drop_column("first_seen_at")
        batch_op.drop_column("persistence_key")
