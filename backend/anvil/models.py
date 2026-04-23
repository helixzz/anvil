from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from anvil.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


_tz_datetime = DateTime(timezone=True)


class RunStatus(StrEnum):
    QUEUED = "queued"
    PREFLIGHT = "preflight"
    RUNNING = "running"
    COMPLETE = "complete"
    ABORTED = "aborted"
    FAILED = "failed"


class DeviceProtocol(StrEnum):
    NVME = "nvme"
    SATA = "sata"
    SAS = "sas"
    UNKNOWN = "unknown"


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    wwid: Mapped[str | None] = mapped_column(String(256))
    model: Mapped[str] = mapped_column(String(256), nullable=False)
    serial: Mapped[str] = mapped_column(String(128), nullable=False)
    firmware: Mapped[str | None] = mapped_column(String(64))
    vendor: Mapped[str | None] = mapped_column(String(128))
    brand: Mapped[str | None] = mapped_column(String(128))
    protocol: Mapped[str] = mapped_column(String(16), nullable=False)
    form_factor: Mapped[str | None] = mapped_column(String(32))
    capacity_bytes: Mapped[int | None] = mapped_column(BigInteger)
    sector_size_logical: Mapped[int | None] = mapped_column(Integer)
    sector_size_physical: Mapped[int | None] = mapped_column(Integer)
    is_testable: Mapped[bool] = mapped_column(default=True, nullable=False)
    exclusion_reason: Mapped[str | None] = mapped_column(String(256))
    current_device_path: Mapped[str | None] = mapped_column(String(256))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    first_seen: Mapped[datetime] = mapped_column(_tz_datetime, default=utcnow, nullable=False)
    last_seen: Mapped[datetime] = mapped_column(_tz_datetime, default=utcnow, nullable=False)

    snapshots: Mapped[list[DeviceSnapshot]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )
    runs: Mapped[list[Run]] = relationship(back_populates="device")


class DeviceSnapshot(Base):
    __tablename__ = "device_snapshots"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    device_id: Mapped[str] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    captured_at: Mapped[datetime] = mapped_column(_tz_datetime, default=utcnow, nullable=False)
    raw_nvme_list: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    raw_smart: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    raw_lsblk: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    raw_sysfs: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    pcie: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    parsed: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    device: Mapped[Device] = relationship(back_populates="snapshots")


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    device_id: Mapped[str] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    profile_name: Mapped[str] = mapped_column(String(128), nullable=False)
    profile_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=RunStatus.QUEUED.value)
    queued_at: Mapped[datetime] = mapped_column(_tz_datetime, default=utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(_tz_datetime)
    finished_at: Mapped[datetime | None] = mapped_column(_tz_datetime)
    error_message: Mapped[str | None] = mapped_column(Text)
    host_system: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    smart_before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    smart_after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    env_before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    env_after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    device_path_at_run: Mapped[str] = mapped_column(String(256), nullable=False)
    share_slug: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)

    device: Mapped[Device] = relationship(back_populates="runs")
    phases: Mapped[list[RunPhase]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="RunPhase.phase_order"
    )
    metrics: Mapped[list[RunMetric]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class RunPhase(Base):
    __tablename__ = "run_phases"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    phase_order: Mapped[int] = mapped_column(Integer, nullable=False)
    phase_name: Mapped[str] = mapped_column(String(128), nullable=False)
    pattern: Mapped[str] = mapped_column(String(32), nullable=False)
    block_size: Mapped[int] = mapped_column(Integer, nullable=False)
    iodepth: Mapped[int] = mapped_column(Integer, nullable=False)
    numjobs: Mapped[int] = mapped_column(Integer, nullable=False)
    rwmix_write_pct: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    runtime_s: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(_tz_datetime)
    finished_at: Mapped[datetime | None] = mapped_column(_tz_datetime)

    fio_jobfile: Mapped[str | None] = mapped_column(Text)
    fio_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    read_iops: Mapped[float | None] = mapped_column(Float)
    read_bw_bytes: Mapped[int | None] = mapped_column(BigInteger)
    read_clat_mean_ns: Mapped[float | None] = mapped_column(Float)
    read_clat_p50_ns: Mapped[float | None] = mapped_column(Float)
    read_clat_p99_ns: Mapped[float | None] = mapped_column(Float)
    read_clat_p999_ns: Mapped[float | None] = mapped_column(Float)
    read_clat_p9999_ns: Mapped[float | None] = mapped_column(Float)

    write_iops: Mapped[float | None] = mapped_column(Float)
    write_bw_bytes: Mapped[int | None] = mapped_column(BigInteger)
    write_clat_mean_ns: Mapped[float | None] = mapped_column(Float)
    write_clat_p50_ns: Mapped[float | None] = mapped_column(Float)
    write_clat_p99_ns: Mapped[float | None] = mapped_column(Float)
    write_clat_p999_ns: Mapped[float | None] = mapped_column(Float)
    write_clat_p9999_ns: Mapped[float | None] = mapped_column(Float)

    run: Mapped[Run] = relationship(back_populates="phases")


class RunMetric(Base):
    __tablename__ = "run_metrics"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
    )
    phase_id: Mapped[str | None] = mapped_column(
        ForeignKey("run_phases.id", ondelete="SET NULL")
    )
    ts: Mapped[datetime] = mapped_column(_tz_datetime, default=utcnow, nullable=False)
    metric_name: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)

    run: Mapped[Run] = relationship(back_populates="metrics")

    __table_args__ = (
        Index("ix_run_metrics_run_ts", "run_id", "ts"),
        Index("ix_run_metrics_phase_name_ts", "phase_id", "metric_name", "ts"),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(_tz_datetime, default=utcnow, nullable=False, index=True)
    actor: Mapped[str | None] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target: Mapped[str | None] = mapped_column(String(256))
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class UserRole(StrEnum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    username: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(256))
    password_hash: Mapped[str | None] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(32), nullable=False, default=UserRole.VIEWER.value)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(_tz_datetime, default=utcnow, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(_tz_datetime)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(_tz_datetime, default=utcnow, nullable=False)


class SavedComparison(Base):
    __tablename__ = "saved_comparisons"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    run_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    share_slug: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(_tz_datetime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        _tz_datetime, default=utcnow, onupdate=utcnow, nullable=False
    )


class TuneReceipt(Base):
    __tablename__ = "tune_receipts"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    results: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    reverted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        _tz_datetime, default=utcnow, nullable=False, index=True
    )
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
