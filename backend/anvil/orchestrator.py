from __future__ import annotations

import asyncio
import platform
from datetime import UTC, datetime
from typing import Any

import ulid
from sqlalchemy import select

from anvil.config import get_settings
from anvil.db import session_scope
from anvil.logging import get_logger
from anvil.models import AuditLog, Device, Run, RunMetric, RunPhase, RunStatus
from anvil.profiles import Profile, get_profile
from anvil.pubsub import get_broadcaster
from anvil.runner import RunnerClient, get_runner_client

log = get_logger("anvil.orchestrator")


class JobQueue:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._running_run_id: str | None = None
        self._running_task: asyncio.Task[None] | None = None
        self._abort_requests: set[str] = set()

    def start(self) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run_forever(), name="anvil-job-queue")

    def stop(self) -> None:
        if self._worker is not None:
            self._worker.cancel()

    async def submit(self, run_id: str) -> None:
        await self._queue.put(run_id)

    @property
    def running_run_id(self) -> str | None:
        return self._running_run_id

    async def abort(self, run_id: str) -> str:
        """Request abort for a queued or running run.

        Returns the resulting status: "aborted_queued" for a run that was
        drained from the queue without starting, "aborting" if the active run
        was cancelled (caller should poll for the final status), or
        "not_active" if the run is neither queued nor running.
        """
        if self._running_run_id == run_id and self._running_task is not None:
            self._abort_requests.add(run_id)
            self._running_task.cancel()
            return "aborting"
        return "not_active"

    async def _run_forever(self) -> None:
        while True:
            try:
                run_id = await self._queue.get()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("queue_get_failed", error=str(exc), exc_info=True)
                await asyncio.sleep(1.0)
                continue
            async with self._lock:
                self._running_run_id = run_id
                task = asyncio.create_task(_execute_run(run_id), name=f"anvil-run-{run_id}")
                self._running_task = task
                try:
                    await task
                except asyncio.CancelledError:
                    log.info("run_cancelled", run_id=run_id)
                    await _safe_mark_aborted(run_id)
                except Exception as exc:
                    log.error("run_failed", run_id=run_id, error=str(exc), exc_info=True)
                    await _safe_mark_failed(run_id, str(exc))
                finally:
                    self._running_run_id = None
                    self._running_task = None
                    self._abort_requests.discard(run_id)


_queue_instance: JobQueue | None = None


def get_queue() -> JobQueue:
    global _queue_instance
    if _queue_instance is None:
        _queue_instance = JobQueue()
    return _queue_instance


async def _mark_failed(run_id: str, error: str) -> None:
    async with session_scope() as session:
        run = await session.get(Run, run_id)
        if run is None:
            return
        run.status = RunStatus.FAILED.value
        run.error_message = error
        run.finished_at = datetime.now(UTC)


async def _mark_aborted(run_id: str) -> None:
    async with session_scope() as session:
        run = await session.get(Run, run_id)
        if run is None:
            return
        run.status = RunStatus.ABORTED.value
        run.error_message = "aborted by user"
        run.finished_at = datetime.now(UTC)
    broadcaster = get_broadcaster()
    await broadcaster.publish(
        f"runs:{run_id}",
        {"event": "run_aborted", "payload": {"run_id": run_id, "reason": "aborted by user"}},
    )


async def _safe_mark_failed(run_id: str, error: str) -> None:
    """Persist a failed-status transition but never raise.

    Called from the worker's except-handler, so any exception here
    would crash the worker task and stop all future scheduling. A DB
    outage is bad, but a worker that gives up permanently is worse —
    log and keep running so the worker can recover when the DB comes
    back.
    """
    try:
        await _mark_failed(run_id, error)
    except Exception as exc:
        log.error(
            "mark_failed_failed",
            run_id=run_id,
            original_error=error,
            persistence_error=str(exc),
            exc_info=True,
        )


async def _safe_mark_aborted(run_id: str) -> None:
    try:
        await _mark_aborted(run_id)
    except Exception as exc:
        log.error(
            "mark_aborted_failed",
            run_id=run_id,
            persistence_error=str(exc),
            exc_info=True,
        )


async def reconcile_on_startup() -> list[str]:
    """Recover runs that were in-flight when the API was killed.

    There are three possible states to recover:

    - `queued`: the row was committed but never pushed into the
      in-memory asyncio.Queue (or was pushed and then lost to a
      restart). Re-enqueue it so the worker picks it up.
    - `preflight` / `running`: a worker had claimed the run but died
      mid-execution. We cannot resume safely because the fio process
      in the runner container is gone and any partial phase state is
      now stale; mark the row failed with a clear reason so operators
      know to re-queue it manually.

    Called from the FastAPI lifespan after `session_scope` is ready and
    before `JobQueue.start()`. Idempotent: safe to call more than once.
    Returns the list of run IDs that were re-enqueued, for logging.
    """
    requeued: list[str] = []
    async with session_scope() as session:
        stale_rows = (
            await session.execute(
                select(Run).where(
                    Run.status.in_(
                        [RunStatus.PREFLIGHT.value, RunStatus.RUNNING.value]
                    )
                )
            )
        ).scalars().all()
        for row in stale_rows:
            row.status = RunStatus.FAILED.value
            row.finished_at = datetime.now(UTC)
            row.error_message = (
                "API restarted while this run was in progress; partial state "
                "is unrecoverable. Re-queue the run to try again."
            )
            log.warning(
                "run_failed_on_reconcile",
                run_id=row.id,
                previous_status=row.status,
            )
        queued_rows = (
            await session.execute(
                select(Run)
                .where(Run.status == RunStatus.QUEUED.value)
                .order_by(Run.queued_at.asc())
            )
        ).scalars().all()
        requeued = [r.id for r in queued_rows]
    queue = get_queue()
    for run_id in requeued:
        await queue.submit(run_id)
        log.info("run_requeued_on_reconcile", run_id=run_id)
    return requeued


async def _execute_run(run_id: str) -> None:
    settings = get_settings()
    client: RunnerClient = get_runner_client(settings.runner_socket)
    broadcaster = get_broadcaster()

    async with session_scope() as session:
        run = await session.get(Run, run_id)
        if run is None:
            log.warning("run_not_found", run_id=run_id)
            return
        device = await session.get(Device, run.device_id)
        if device is None:
            raise RuntimeError(f"device {run.device_id} missing for run {run_id}")
        profile: Profile | None = get_profile(run.profile_name)
        if profile is None:
            raise RuntimeError(f"profile {run.profile_name} is unknown")

        run.status = RunStatus.PREFLIGHT.value
        run.started_at = datetime.now(UTC)
        host_sys = _capture_host_system()
        device_meta = device.metadata_json or {}
        if device_meta.get("pcie"):
            host_sys["pcie_at_run"] = device_meta["pcie"]
        run.host_system = host_sys
        device_path = device.current_device_path or run.device_path_at_run
        await session.flush()

    await broadcaster.publish(
        f"runs:{run_id}",
        {"event": "run_started", "payload": {"run_id": run_id, "device_path": device_path}},
    )

    ok = await client.ping()
    if not ok:
        raise RuntimeError(
            "Runner socket is unreachable. Ensure the privileged runner container is healthy."
        )

    try:
        smart_before = await client.smart(device_path)
    except Exception as exc:
        log.warning("smart_before_failed", run_id=run_id, error=str(exc))
        smart_before = {"error": str(exc)}

    async with session_scope() as session:
        run = await session.get(Run, run_id)
        if run is None:
            return
        run.smart_before = smart_before
        run.status = RunStatus.RUNNING.value

    phase_id_by_name: dict[str, str] = {}
    async with session_scope() as session:
        for order, spec in enumerate(profile.phases):
            phase_id = str(ulid.ULID())
            phase = RunPhase(
                id=phase_id,
                run_id=run_id,
                phase_order=order,
                phase_name=spec.name,
                pattern=spec.pattern,
                block_size=spec.block_size,
                iodepth=spec.iodepth,
                numjobs=spec.numjobs,
                rwmix_write_pct=spec.rwmix_write_pct,
                runtime_s=spec.runtime_s,
            )
            session.add(phase)
            phase_id_by_name[spec.name] = phase_id

    saw_complete = False
    async for event in client.run_benchmark(
        run_id=run_id,
        device_path=device_path,
        profile=profile.as_dict(),
    ):
        await _handle_event(run_id, phase_id_by_name, event.kind, event.payload)
        await broadcaster.publish(
            f"runs:{run_id}",
            {"event": event.kind, "payload": event.payload},
        )
        if event.kind in {"run_failed", "run_aborted"}:
            async with session_scope() as session:
                run = await session.get(Run, run_id)
                if run is None:
                    return
                run.status = (
                    RunStatus.ABORTED.value if event.kind == "run_aborted" else RunStatus.FAILED.value
                )
                run.finished_at = datetime.now(UTC)
                reason = event.payload.get("reason")
                err = event.payload.get("error")
                if reason == "thermal_abort":
                    t = event.payload.get("threshold_c")
                    n = event.payload.get("consecutive_samples_required")
                    run.error_message = (
                        f"thermal_abort: temperature ≥ {t} °C "
                        f"for {n} consecutive SMART samples"
                    )
                else:
                    run.error_message = err or reason
            return
        if event.kind == "run_complete":
            saw_complete = True

    if not saw_complete:
        raise RuntimeError(
            f"runner stream for run {run_id} ended without a run_complete event"
        )

    try:
        smart_after = await client.smart(device_path)
    except Exception as exc:
        log.warning("smart_after_failed", run_id=run_id, error=str(exc))
        smart_after = {"error": str(exc)}

    async with session_scope() as session:
        run = await session.get(Run, run_id)
        if run is None:
            return
        run.smart_after = smart_after
        run.status = RunStatus.COMPLETE.value
        run.finished_at = datetime.now(UTC)

    await broadcaster.publish(
        f"runs:{run_id}",
        {"event": "run_complete", "payload": {"run_id": run_id}},
    )


async def _handle_event(
    run_id: str,
    phase_id_by_name: dict[str, str],
    kind: str,
    payload: dict[str, Any],
) -> None:
    if kind == "phase_started":
        phase_id = phase_id_by_name.get(payload.get("phase_name", ""))
        if phase_id:
            async with session_scope() as session:
                phase = await session.get(RunPhase, phase_id)
                if phase is not None:
                    phase.started_at = datetime.now(UTC)
                    if payload.get("jobfile"):
                        phase.fio_jobfile = payload["jobfile"]
    elif kind == "phase_sample":
        phase_id = phase_id_by_name.get(payload.get("phase_name", ""))
        metrics: list[tuple[str, float]] = []
        for key in ("read_iops", "write_iops", "read_bw_bytes", "write_bw_bytes",
                    "read_clat_mean_ns", "write_clat_mean_ns"):
            value = payload.get(key)
            if value is None:
                continue
            try:
                metrics.append((key, float(value)))
            except (TypeError, ValueError):
                continue
        if not metrics:
            return
        async with session_scope() as session:
            for name, value in metrics:
                session.add(
                    RunMetric(
                        run_id=run_id,
                        phase_id=phase_id,
                        ts=datetime.now(UTC),
                        metric_name=name,
                        value=value,
                    )
                )
    elif kind == "smart_sample":
        temp_c = payload.get("temperature_c")
        if temp_c is None:
            return
        async with session_scope() as session:
            session.add(
                RunMetric(
                    run_id=run_id,
                    phase_id=None,
                    ts=datetime.now(UTC),
                    metric_name="temperature_c",
                    value=float(temp_c),
                )
            )
    elif kind == "phase_complete":
        phase_id = phase_id_by_name.get(payload.get("phase_name", ""))
        if not phase_id:
            return
        async with session_scope() as session:
            phase = await session.get(RunPhase, phase_id)
            if phase is None:
                return
            phase.finished_at = datetime.now(UTC)
            phase.fio_result = payload.get("fio_result")
            summary = payload.get("summary") or {}
            for attr in (
                "read_iops", "read_bw_bytes",
                "read_clat_mean_ns", "read_clat_p50_ns", "read_clat_p99_ns",
                "read_clat_p999_ns", "read_clat_p9999_ns",
                "write_iops", "write_bw_bytes",
                "write_clat_mean_ns", "write_clat_p50_ns", "write_clat_p99_ns",
                "write_clat_p999_ns", "write_clat_p9999_ns",
            ):
                value = summary.get(attr)
                if value is not None:
                    setattr(phase, attr, value)


def _capture_host_system() -> dict[str, Any]:
    return {
        "platform": platform.platform(),
        "kernel": platform.release(),
        "python": platform.python_version(),
        "architecture": platform.machine(),
    }


async def queue_depth() -> int:
    async with session_scope() as session:
        result = await session.execute(
            select(Run).where(Run.status == RunStatus.QUEUED.value)
        )
        return len(list(result.scalars()))


async def running_count() -> int:
    async with session_scope() as session:
        result = await session.execute(
            select(Run).where(
                Run.status.in_([RunStatus.RUNNING.value, RunStatus.PREFLIGHT.value])
            )
        )
        return len(list(result.scalars()))


async def audit(actor: str | None, action: str, target: str | None, details: dict[str, Any]) -> None:
    async with session_scope() as session:
        session.add(AuditLog(actor=actor, action=action, target=target, details=details))
