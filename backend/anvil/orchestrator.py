from __future__ import annotations

import asyncio
import platform
from datetime import UTC, datetime
from typing import Any

import ulid
from sqlalchemy import select

from anvil.db import session_scope
from anvil.logging import get_logger
from anvil.models import LOCAL_RUNNER_ID, AuditLog, Device, Run, RunMetric, RunPhase, RunStatus
from anvil.profiles import Profile, get_profile
from anvil.pubsub import get_broadcaster
from anvil.runner.registry import get_runner_client, record_ping

log = get_logger("anvil.orchestrator")


class _Lane:
    """Serial execution lane for one runner host.

    Benchmarks on the same host run strictly one at a time (PCIe, CPU and
    thermal contention would corrupt measurements); different hosts run in
    parallel because they share nothing.
    """

    def __init__(self, runner_id: str) -> None:
        self.runner_id = runner_id
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.worker: asyncio.Task[None] | None = None
        self.running_run_id: str | None = None
        self.running_task: asyncio.Task[None] | None = None


class JobQueue:
    def __init__(self) -> None:
        self._lanes: dict[str, _Lane] = {}
        self._scheduler: asyncio.Task[None] | None = None
        self._started = False
        self._abort_requests: set[str] = set()

    def start(self) -> None:
        self._started = True
        for lane in self._lanes.values():
            self._ensure_worker(lane)
        if self._scheduler is None or self._scheduler.done():
            self._scheduler = asyncio.create_task(self._scheduler_loop(), name="anvil-scheduler")

    def stop(self) -> None:
        self._started = False
        for lane in self._lanes.values():
            if lane.worker is not None:
                lane.worker.cancel()
        if self._scheduler is not None:
            self._scheduler.cancel()

    def _ensure_worker(self, lane: _Lane) -> None:
        if lane.worker is None or lane.worker.done():
            lane.worker = asyncio.create_task(
                self._run_forever(lane), name=f"anvil-job-queue-{lane.runner_id}"
            )

    def _lane(self, runner_id: str) -> _Lane:
        lane = self._lanes.get(runner_id)
        if lane is None:
            lane = _Lane(runner_id)
            self._lanes[runner_id] = lane
        if self._started:
            self._ensure_worker(lane)
        return lane

    async def submit(self, run_id: str, runner_id: str | None = None) -> None:
        """Enqueue a committed run on its runner's lane.

        `runner_id` may be passed when the caller already knows it;
        otherwise it is read from the run (falling back to the device's
        runner, which is then pinned onto the run).
        """
        if runner_id is None:
            runner_id = await _resolve_run_runner(run_id)
        await self._lane(runner_id).queue.put(run_id)

    @property
    def running_run_ids(self) -> dict[str, str]:
        return {
            lane.runner_id: lane.running_run_id
            for lane in self._lanes.values()
            if lane.running_run_id is not None
        }

    async def abort(self, run_id: str) -> str:
        """Request abort for a queued or running run.

        Returns the resulting status: "aborted_queued" for a run that was
        drained from the queue without starting, "aborting" if the active run
        was cancelled (caller should poll for the final status), or
        "not_active" if the run is neither queued nor running.
        """
        for lane in self._lanes.values():
            if lane.running_run_id == run_id and lane.running_task is not None:
                self._abort_requests.add(run_id)
                lane.running_task.cancel()
                return "aborting"
        return "not_active"

    async def _run_forever(self, lane: _Lane) -> None:
        while True:
            try:
                run_id = await lane.queue.get()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("queue_get_failed", runner_id=lane.runner_id, error=str(exc), exc_info=True)
                await asyncio.sleep(1.0)
                continue
            lane.running_run_id = run_id
            task = asyncio.create_task(_execute_run(run_id), name=f"anvil-run-{run_id}")
            lane.running_task = task
            try:
                await task
            except asyncio.CancelledError:
                if run_id not in self._abort_requests:
                    # The lane worker itself is being cancelled (shutdown);
                    # reconcile_on_startup marks the run failed next boot.
                    raise
                log.info("run_cancelled", run_id=run_id)
                await _safe_mark_aborted(run_id)
            except Exception as exc:
                log.error("run_failed", run_id=run_id, error=str(exc), exc_info=True)
                await _safe_mark_failed(run_id, str(exc))
            finally:
                lane.running_run_id = None
                lane.running_task = None
                self._abort_requests.discard(run_id)

    async def _scheduler_loop(self) -> None:
        from datetime import timedelta

        from anvil.models import Schedule
        while True:
            try:
                await asyncio.sleep(60)
                to_submit: list[tuple[str, str]] = []
                async with session_scope() as session:
                    now = datetime.now(UTC)
                    due = (await session.execute(
                        select(Schedule).where(
                            Schedule.enabled.is_(True),
                            Schedule.next_run_at.isnot(None),
                            Schedule.next_run_at <= now,
                        )
                    )).scalars().all()
                    for sched in due:
                        try:
                            device = await session.get(Device, sched.device_id)
                            runner_id = (device.runner_id if device else None) or LOCAL_RUNNER_ID
                            run_id = str(ulid.ULID())
                            session.add(Run(
                                id=run_id,
                                device_id=sched.device_id,
                                profile_name=sched.profile_name,
                                profile_snapshot={},
                                status=RunStatus.QUEUED.value,
                                device_path_at_run="/dev/auto-scheduled",
                                runner_id=runner_id,
                            ))
                            await session.flush()
                            to_submit.append((run_id, runner_id))
                            sched.last_run_at = now
                            sched.next_run_at = now + timedelta(hours=sched.interval_hours)
                            log.info("schedule_triggered", schedule_id=sched.id, run_id=run_id)
                        except Exception as exc:
                            log.error("schedule_run_failed", schedule_id=sched.id, error=str(exc))
                # Submit only after commit: lane workers read the run in their
                # own session and must see the committed row.
                for run_id, runner_id in to_submit:
                    await self.submit(run_id, runner_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("scheduler_loop_error", error=str(exc), exc_info=True)
                await asyncio.sleep(60)


async def _resolve_run_runner(run_id: str) -> str:
    async with session_scope() as session:
        run = await session.get(Run, run_id)
        if run is None:
            return LOCAL_RUNNER_ID
        if run.runner_id is None:
            device = await session.get(Device, run.device_id)
            run.runner_id = (device.runner_id if device else None) or LOCAL_RUNNER_ID
        return run.runner_id


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
    broadcaster = get_broadcaster()

    async with session_scope() as session:
        run = await session.get(Run, run_id)
        if run is None:
            log.warning("run_not_found", run_id=run_id)
            return
        if run.status != RunStatus.QUEUED.value:
            # Cancelled (or otherwise finalised) while waiting in the lane.
            log.info("run_skipped_not_queued", run_id=run_id, status=run.status)
            return
        device = await session.get(Device, run.device_id)
        if device is None:
            raise RuntimeError(f"device {run.device_id} missing for run {run_id}")
        profile: Profile | None = get_profile(run.profile_name)
        if profile is None:
            raise RuntimeError(f"profile {run.profile_name} is unknown")

        runner_id = run.runner_id or device.runner_id or LOCAL_RUNNER_ID
        if device.runner_id is not None and device.runner_id != runner_id:
            # The drive was moved to another host after this run was queued;
            # its device path on the original host now means something else.
            raise RuntimeError(
                "device has moved to a different runner host since this run was queued; "
                "re-queue the run"
            )
        run.runner_id = runner_id
        run.status = RunStatus.PREFLIGHT.value
        run.started_at = datetime.now(UTC)
        device_pcie = (device.metadata_json or {}).get("pcie")
        device_path = device.current_device_path or run.device_path_at_run
        await session.flush()

    await broadcaster.publish(
        f"runs:{run_id}",
        {"event": "run_started", "payload": {"run_id": run_id, "device_path": device_path}},
    )

    client = await get_runner_client(runner_id)
    ping = await client.ping_info()
    if ping is None:
        raise RuntimeError(
            f"Runner '{runner_id}' is unreachable. Check that the runner service on that "
            "host is healthy and reachable from the API."
        )
    await record_ping(runner_id, ping)

    # Older runners do not report host facts; fall back to the API's view.
    host_sys: dict[str, Any] = dict(ping.get("host") or _capture_host_system())
    host_sys["runner_id"] = runner_id
    if device_pcie:
        host_sys["pcie_at_run"] = device_pcie

    try:
        smart_before = await client.smart(device_path)
    except Exception as exc:
        log.warning("smart_before_failed", run_id=run_id, error=str(exc))
        smart_before = {"error": str(exc)}

    async with session_scope() as session:
        run = await session.get(Run, run_id)
        if run is None:
            return
        run.host_system = host_sys
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
