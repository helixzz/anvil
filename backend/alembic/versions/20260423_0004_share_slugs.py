"""share slugs for runs and saved comparisons

Revision ID: 20260423_0004
Revises: 20260422_0003
Create Date: 2026-04-23
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260423_0004"
down_revision = "20260422_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Runs get an optional share slug. Nullable so existing rows remain
    # private; populated by POST /api/runs/{id}/share. Unique index so
    # slugs can be used as stable URL tokens.
    op.add_column(
        "runs",
        sa.Column("share_slug", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_runs_share_slug",
        "runs",
        ["share_slug"],
        unique=True,
    )

    # Saved comparisons: a named, reusable selection of run IDs that can
    # itself be shared publicly via its own slug. created_by references
    # users.id but is nullable (anonymous/legacy-friendly) and uses
    # ON DELETE SET NULL so deleting a user doesn't cascade.
    op.create_table(
        "saved_comparisons",
        sa.Column("id", sa.String(length=26), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "run_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("share_slug", sa.String(length=64), nullable=True),
        sa.Column(
            "created_by",
            sa.String(length=26),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_saved_comparisons_share_slug",
        "saved_comparisons",
        ["share_slug"],
        unique=True,
    )
    op.create_index(
        "ix_saved_comparisons_created_by",
        "saved_comparisons",
        ["created_by"],
    )


def downgrade() -> None:
    op.drop_index("ix_saved_comparisons_created_by", table_name="saved_comparisons")
    op.drop_index("ix_saved_comparisons_share_slug", table_name="saved_comparisons")
    op.drop_table("saved_comparisons")
    op.drop_index("ix_runs_share_slug", table_name="runs")
    op.drop_column("runs", "share_slug")
