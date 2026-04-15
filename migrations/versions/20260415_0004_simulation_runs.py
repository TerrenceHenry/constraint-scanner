"""Add authoritative simulation run identity and summary semantics."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260415_0004"
down_revision = "20260415_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("simulated_executions", sa.Column("simulation_run_id", sa.String(length=255), nullable=True))
    op.add_column(
        "simulated_executions",
        sa.Column("summary_record", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.execute(
        sa.text(
            """
            UPDATE simulated_executions
            SET simulation_run_id = :prefix || CAST(id AS TEXT)
            WHERE simulation_run_id IS NULL
            """
        ).bindparams(prefix="legacy-simrun:")
    )

    with op.batch_alter_table("simulated_executions") as batch_op:
        batch_op.alter_column("simulation_run_id", existing_type=sa.String(length=255), nullable=False)
        batch_op.alter_column("side", existing_type=sa.String(length=8), nullable=True)
        batch_op.alter_column("price", existing_type=sa.Numeric(18, 8), nullable=True)
        batch_op.alter_column("quantity", existing_type=sa.Numeric(24, 8), nullable=True)

    with op.batch_alter_table("simulated_executions") as batch_op:
        batch_op.create_index(
            "ix_simulated_executions_run_id",
            ["simulation_run_id"],
        )
        batch_op.create_index(
            "ix_simulated_executions_latest_summary",
            ["opportunity_id", "summary_record", "executed_at"],
        )
        batch_op.create_unique_constraint(
            "uq_simulated_executions_opportunity_run",
            ["opportunity_id", "simulation_run_id"],
        )
        batch_op.alter_column("summary_record", existing_type=sa.Boolean(), server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("simulated_executions") as batch_op:
        batch_op.drop_constraint("uq_simulated_executions_opportunity_run", type_="unique")
        batch_op.drop_index("ix_simulated_executions_latest_summary")
        batch_op.drop_index("ix_simulated_executions_run_id")
        batch_op.alter_column("quantity", existing_type=sa.Numeric(24, 8), nullable=False)
        batch_op.alter_column("price", existing_type=sa.Numeric(18, 8), nullable=False)
        batch_op.alter_column("side", existing_type=sa.String(length=8), nullable=False)
        batch_op.drop_column("summary_record")
        batch_op.drop_column("simulation_run_id")
