"""initial schema

Revision ID: 20260422_0001
Revises:
Create Date: 2026-04-22

"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260422_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "devices",
        sa.Column("id", sa.String(length=26), primary_key=True),
        sa.Column("fingerprint", sa.String(length=128), unique=True, nullable=False),
        sa.Column("wwid", sa.String(length=256), nullable=True),
        sa.Column("model", sa.String(length=256), nullable=False),
        sa.Column("serial", sa.String(length=128), nullable=False),
        sa.Column("firmware", sa.String(length=64), nullable=True),
        sa.Column("vendor", sa.String(length=128), nullable=True),
        sa.Column("brand", sa.String(length=128), nullable=True),
        sa.Column("protocol", sa.String(length=16), nullable=False),
        sa.Column("form_factor", sa.String(length=32), nullable=True),
        sa.Column("capacity_bytes", sa.BigInteger(), nullable=True),
        sa.Column("sector_size_logical", sa.Integer(), nullable=True),
        sa.Column("sector_size_physical", sa.Integer(), nullable=True),
        sa.Column("is_testable", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("exclusion_reason", sa.String(length=256), nullable=True),
        sa.Column("current_device_path", sa.String(length=256), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "device_snapshots",
        sa.Column("id", sa.String(length=26), primary_key=True),
        sa.Column("device_id", sa.String(length=26),
                  sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_nvme_list", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_smart", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_lsblk", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_sysfs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("pcie", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "parsed",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    op.create_table(
        "runs",
        sa.Column("id", sa.String(length=26), primary_key=True),
        sa.Column("device_id", sa.String(length=26),
                  sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("profile_name", sa.String(length=128), nullable=False),
        sa.Column("profile_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("host_system", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("smart_before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("smart_after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("env_before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("env_after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("device_path_at_run", sa.String(length=256), nullable=False),
    )

    op.create_table(
        "run_phases",
        sa.Column("id", sa.String(length=26), primary_key=True),
        sa.Column("run_id", sa.String(length=26),
                  sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("phase_order", sa.Integer(), nullable=False),
        sa.Column("phase_name", sa.String(length=128), nullable=False),
        sa.Column("pattern", sa.String(length=32), nullable=False),
        sa.Column("block_size", sa.Integer(), nullable=False),
        sa.Column("iodepth", sa.Integer(), nullable=False),
        sa.Column("numjobs", sa.Integer(), nullable=False),
        sa.Column("rwmix_write_pct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("runtime_s", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fio_jobfile", sa.Text(), nullable=True),
        sa.Column("fio_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("read_iops", sa.Float(), nullable=True),
        sa.Column("read_bw_bytes", sa.BigInteger(), nullable=True),
        sa.Column("read_clat_mean_ns", sa.Float(), nullable=True),
        sa.Column("read_clat_p50_ns", sa.Float(), nullable=True),
        sa.Column("read_clat_p99_ns", sa.Float(), nullable=True),
        sa.Column("read_clat_p999_ns", sa.Float(), nullable=True),
        sa.Column("read_clat_p9999_ns", sa.Float(), nullable=True),
        sa.Column("write_iops", sa.Float(), nullable=True),
        sa.Column("write_bw_bytes", sa.BigInteger(), nullable=True),
        sa.Column("write_clat_mean_ns", sa.Float(), nullable=True),
        sa.Column("write_clat_p50_ns", sa.Float(), nullable=True),
        sa.Column("write_clat_p99_ns", sa.Float(), nullable=True),
        sa.Column("write_clat_p999_ns", sa.Float(), nullable=True),
        sa.Column("write_clat_p9999_ns", sa.Float(), nullable=True),
    )

    op.create_table(
        "run_metrics",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(length=26),
                  sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("phase_id", sa.String(length=26),
                  sa.ForeignKey("run_phases.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metric_name", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
    )
    op.create_index("ix_run_metrics_run_ts", "run_metrics", ["run_id", "ts"])
    op.create_index(
        "ix_run_metrics_phase_name_ts", "run_metrics", ["phase_id", "metric_name", "ts"]
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("actor", sa.String(length=128), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target", sa.String(length=256), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_index("ix_run_metrics_phase_name_ts", table_name="run_metrics")
    op.drop_index("ix_run_metrics_run_ts", table_name="run_metrics")
    op.drop_table("run_metrics")
    op.drop_table("run_phases")
    op.drop_table("runs")
    op.drop_table("device_snapshots")
    op.drop_table("devices")
