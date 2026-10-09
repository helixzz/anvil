"""runners table; devices/runs/tune_receipts gain runner_id

Every existing device, run and tune receipt belonged to the single
co-located runner, so they are backfilled to the `local` runner row.

Revision ID: 20261009_0008
Revises: 20260427_0007
Create Date: 2026-10-09
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261009_0008"
down_revision = "20260427_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runners",
        sa.Column("id", sa.String(length=26), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False, unique=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("address", sa.String(length=256), nullable=False),
        sa.Column("token", sa.Text(), nullable=True),
        sa.Column("tls_fingerprint", sa.String(length=128), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "host_info",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.execute(
        "INSERT INTO runners (id, name, kind, address, enabled) "
        "VALUES ('local', 'local', 'unix', '/run/anvil/runner.sock', true)"
    )

    for table, indexed in (("devices", True), ("runs", True), ("tune_receipts", False)):
        op.add_column(
            table,
            sa.Column(
                "runner_id",
                sa.String(length=26),
                sa.ForeignKey("runners.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
        if indexed:
            op.create_index(f"ix_{table}_runner_id", table, ["runner_id"])
        op.execute(f"UPDATE {table} SET runner_id = 'local'")


def downgrade() -> None:
    for table, indexed in (("tune_receipts", False), ("runs", True), ("devices", True)):
        if indexed:
            op.drop_index(f"ix_{table}_runner_id", table_name=table)
        op.drop_column(table, "runner_id")
    op.drop_table("runners")
