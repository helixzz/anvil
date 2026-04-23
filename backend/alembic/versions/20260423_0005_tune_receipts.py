"""tune_receipts: server-side storage of env-tune apply receipts

Revision ID: 20260423_0005
Revises: 20260423_0004
Create Date: 2026-04-23
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260423_0005"
down_revision = "20260423_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tune_receipts",
        sa.Column("id", sa.String(length=26), primary_key=True),
        sa.Column(
            "results",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("reverted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_by",
            sa.String(length=26),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_tune_receipts_created_at", "tune_receipts", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_tune_receipts_created_at", table_name="tune_receipts")
    op.drop_table("tune_receipts")
