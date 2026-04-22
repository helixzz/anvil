from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select

from anvil import __version__
from anvil.api import require_bearer
from anvil.api.auth import admin_router
from anvil.api.auth import router as auth_router
from anvil.api.comparisons import router as comparisons_router
from anvil.api.dashboard import router as dashboard_router
from anvil.api.devices import router as devices_router
from anvil.api.environment import router as environment_router
from anvil.api.models import router as models_router
from anvil.api.public import router as public_router
from anvil.api.runs import router as runs_router
from anvil.api.ws import router as ws_router
from anvil.auth import hash_password
from anvil.config import get_settings
from anvil.db import session_scope
from anvil.logging import configure_logging, get_logger
from anvil.models import Device, Run, RunStatus, User, UserRole
from anvil.orchestrator import get_queue
from anvil.runner import get_runner_client
from anvil.schemas import SystemStatus

_start_time = time.monotonic()


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    log = get_logger("anvil")
    log.info("anvil_starting", version=__version__, simulation=settings.simulation_mode)
    await _bootstrap_admin()
    get_queue().start()
    try:
        yield
    finally:
        get_queue().stop()
        log.info("anvil_stopped")


async def _bootstrap_admin() -> None:
    """Ensure at least one active admin exists.

    Creates a user `admin` with password = first 16 chars of the
    ANVIL_BEARER_TOKEN if no admin user is present yet. This lets
    operators log in via the UI the moment the service comes up; they
    can rotate the password afterward. The static bearer token itself
    continues to work as an admin credential independently of this row.
    """
    import ulid
    from sqlalchemy import func, select

    log = get_logger("anvil.bootstrap")
    settings = get_settings()
    async with session_scope() as session:
        admin_count = (
            await session.execute(
                select(func.count(User.id))
                .where(User.role == UserRole.ADMIN.value)
                .where(User.is_active.is_(True))
            )
        ).scalar_one()
        if admin_count > 0:
            return
        bootstrap_pw = settings.bearer_token[:16]
        user = User(
            id=str(ulid.ULID()),
            username="admin",
            display_name="Bootstrap administrator",
            password_hash=hash_password(bootstrap_pw),
            role=UserRole.ADMIN.value,
            is_active=True,
        )
        session.add(user)
        log.warning(
            "bootstrap_admin_created",
            username="admin",
            password_source="first 16 chars of ANVIL_BEARER_TOKEN",
        )


app = FastAPI(
    title="Anvil",
    description="NVMe Validator & IOps Lab — backend API",
    version=__version__,
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api")
app.include_router(devices_router, prefix="/api")
app.include_router(runs_router, prefix="/api")
app.include_router(models_router, prefix="/api")
app.include_router(environment_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(comparisons_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(public_router)
app.include_router(ws_router)


@app.get("/api/status", response_model=SystemStatus, dependencies=[Depends(require_bearer)])
async def status_endpoint() -> SystemStatus:
    settings = get_settings()
    async with session_scope() as session:
        device_count = (await session.execute(select(func.count(Device.id)))).scalar_one()
        queued_count = (
            await session.execute(
                select(func.count(Run.id)).where(Run.status == RunStatus.QUEUED.value)
            )
        ).scalar_one()
        running_count = (
            await session.execute(
                select(func.count(Run.id)).where(
                    Run.status.in_([RunStatus.RUNNING.value, RunStatus.PREFLIGHT.value])
                )
            )
        ).scalar_one()

    try:
        runner_ok = await asyncio.wait_for(
            get_runner_client(settings.runner_socket).ping(), timeout=2.0
        )
    except Exception:
        runner_ok = False

    return SystemStatus(
        version=__version__,
        runner_connected=runner_ok,
        simulation_mode=settings.simulation_mode,
        device_count=device_count,
        running_count=running_count,
        queued_count=queued_count,
        uptime_seconds=time.monotonic() - _start_time,
    )


@app.get("/api/health", include_in_schema=False)
async def health() -> dict[str, str]:
    return {"status": "ok"}
