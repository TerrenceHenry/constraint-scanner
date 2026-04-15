"""Add explicit opportunity scope keys for open-row uniqueness."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260415_0003"
down_revision = "20260415_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("opportunities", sa.Column("scope_key", sa.String(length=255), nullable=True))

    op.execute(
        sa.text(
            """
            UPDATE opportunities
            SET scope_key = CASE
                WHEN constraint_id IS NOT NULL THEN :constraint_prefix || CAST(constraint_id AS TEXT)
                ELSE :legacy_prefix || CAST(id AS TEXT)
            END
            WHERE scope_key IS NULL
            """
        ).bindparams(
            constraint_prefix="constraint:",
            legacy_prefix="legacy-opportunity:",
        )
    )

    with op.batch_alter_table("opportunities") as batch_op:
        batch_op.alter_column("scope_key", existing_type=sa.String(length=255), nullable=False)

    op.drop_index("uq_opportunities_open_constraint_persistence", table_name="opportunities")
    op.create_index(
        "ix_opportunities_scope_key",
        "opportunities",
        ["scope_key"],
    )
    op.create_index(
        "uq_opportunities_open_scope_persistence",
        "opportunities",
        ["scope_key", "persistence_key"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
        sqlite_where=sa.text("status = 'open'"),
    )


def downgrade() -> None:
    op.drop_index("uq_opportunities_open_scope_persistence", table_name="opportunities")
    op.drop_index("ix_opportunities_scope_key", table_name="opportunities")
    op.create_index(
        "uq_opportunities_open_constraint_persistence",
        "opportunities",
        ["constraint_id", "persistence_key"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
        sqlite_where=sa.text("status = 'open'"),
    )

    with op.batch_alter_table("opportunities") as batch_op:
        batch_op.drop_column("scope_key")
