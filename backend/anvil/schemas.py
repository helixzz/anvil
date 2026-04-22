from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DeviceOut(BaseModel):
    id: str
    fingerprint: str
    model: str
    serial: str
    firmware: str | None
    vendor: str | None
    brand: str | None
    protocol: str
    form_factor: str | None
    capacity_bytes: int | None
    sector_size_logical: int | None
    sector_size_physical: int | None
    wwid: str | None
    current_device_path: str | None
    is_testable: bool
    exclusion_reason: str | None
    first_seen: datetime
    last_seen: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True


class RunCreate(BaseModel):
    device_id: str
    profile_name: str = "quick"
    confirm_serial_last6: str | None = None
    simulation: bool = False


class RunPhaseOut(BaseModel):
    id: str
    phase_order: int
    phase_name: str
    pattern: str
    block_size: int
    iodepth: int
    numjobs: int
    rwmix_write_pct: int
    runtime_s: int
    started_at: datetime | None
    finished_at: datetime | None
    read_iops: float | None
    read_bw_bytes: int | None
    read_clat_mean_ns: float | None
    read_clat_p50_ns: float | None
    read_clat_p99_ns: float | None
    read_clat_p999_ns: float | None
    read_clat_p9999_ns: float | None
    write_iops: float | None
    write_bw_bytes: int | None
    write_clat_mean_ns: float | None
    write_clat_p50_ns: float | None
    write_clat_p99_ns: float | None
    write_clat_p999_ns: float | None
    write_clat_p9999_ns: float | None

    class Config:
        from_attributes = True


class RunOut(BaseModel):
    id: str
    device_id: str
    profile_name: str
    status: str
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None
    device_path_at_run: str
    phases: list[RunPhaseOut] = Field(default_factory=list)
    host_system: dict[str, Any] | None = None
    smart_before: dict[str, Any] | None = None
    smart_after: dict[str, Any] | None = None

    class Config:
        from_attributes = True


class RunSummary(BaseModel):
    id: str
    device_id: str
    device_model: str
    device_serial: str
    profile_name: str
    status: str
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class MetricPoint(BaseModel):
    ts: datetime
    metric_name: str
    value: float


class ProfileOut(BaseModel):
    name: str
    title: str
    description: str
    estimated_duration_seconds: int
    destructive: bool
    phases: list[dict[str, Any]]


class SystemStatus(BaseModel):
    version: str
    runner_connected: bool
    simulation_mode: bool
    device_count: int
    running_count: int
    queued_count: int
    uptime_seconds: float
