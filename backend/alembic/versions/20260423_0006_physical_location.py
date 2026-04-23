"""physical_location column on devices

Revision ID: 20260423_0006
Revises: 20260423_0005
Create Date: 2026-04-23
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260423_0006"
down_revision = "20260423_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "devices",
        sa.Column(
            "physical_location",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(
                sa.JSON(), "sqlite"
            ),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("devices", "physical_location")
