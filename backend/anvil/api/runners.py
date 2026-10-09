"""Runner host registry: list (with live status), register, edit, remove.

The token is write-only: it is accepted on create/update but never returned.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import ulid
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from anvil.api import require_bearer
from anvil.auth import Principal, require_admin, resolve_principal
from anvil.db import get_session
from anvil.models import LOCAL_RUNNER_ID, Device, Run, Runner, RunnerKind, RunStatus
from anvil.orchestrator import audit as audit_write
from anvil.orchestrator import get_queue
from anvil.runner import (
    RunnerClient,
    RunnerUnavailable,
    fetch_tls_fingerprint,
    normalize_fingerprint,
    parse_tcp_address,
)
from anvil.runner.registry import client_for, ensure_local_runner

router = APIRouter(prefix="/runners", tags=["runners"], dependencies=[Depends(require_bearer)])

PING_TIMEOUT_S = 4.0


class RunnerOut(BaseModel):
    id: str
    name: str
    kind: str
    address: str
    enabled: bool
    tls_fingerprint: str | None
    has_token: bool
    host_info: dict[str, Any] | None
    last_seen_at: datetime | None
    created_at: datetime
    online: bool
    busy: bool
    device_count: int
    running_run_id: str | None
    error: str | None = None


class RunnerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    address: str = Field(min_length=3, max_length=256, description="HOST:PORT of the runner")
    token: str = Field(min_length=16, max_length=512)
    tls_fingerprint: str | None = Field(
        default=None,
        description="SHA-256 of the runner certificate. Omit to trust the certificate "
        "presented on first contact (shown in the response; compare it with the "
        "fingerprint printed by the runner installer).",
    )


class RunnerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    address: str | None = Field(default=None, min_length=3, max_length=256)
    token: str | None = Field(default=None, min_length=16, max_length=512)
    tls_fingerprint: str | None = None
    refetch_fingerprint: bool = False
    enabled: bool | None = None


async def _probe(runner: Runner) -> tuple[dict[str, Any] | None, str | None]:
    if not runner.enabled:
        return None, "disabled"
    try:
        client = client_for(runner)
    except (RunnerUnavailable, ValueError) as exc:
        return None, str(exc)
    try:
        info = await asyncio.wait_for(client.ping_info(), timeout=PING_TIMEOUT_S)
    except TimeoutError:
        return None, "timed out"
    if info is None:
        if runner.kind == RunnerKind.UNIX.value:
            return None, "unreachable (runner socket not available)"
        return None, "unreachable (connection, TLS fingerprint or token rejected)"
    return info, None


async def _serialize(
    session: AsyncSession, runners: list[Runner]
) -> list[RunnerOut]:
    probes = await asyncio.gather(*(_probe(r) for r in runners))
    counts = dict(
        (await session.execute(
            select(Device.runner_id, func.count(Device.id))
            .where(Device.current_device_path.isnot(None))
            .group_by(Device.runner_id)
        )).all()
    )
    running = get_queue().running_run_ids
    out: list[RunnerOut] = []
    for runner, (info, error) in zip(runners, probes, strict=True):
        if info is not None:
            runner.last_seen_at = datetime.now(UTC)
            if info.get("host"):
                runner.host_info = info["host"]
        out.append(RunnerOut(
            id=runner.id,
            name=runner.name,
            kind=runner.kind,
            address=runner.address,
            enabled=runner.enabled,
            tls_fingerprint=runner.tls_fingerprint,
            has_token=bool(runner.token),
            host_info=(info or {}).get("host") or runner.host_info,
            last_seen_at=runner.last_seen_at,
            created_at=runner.created_at,
            online=info is not None,
            busy=bool((info or {}).get("busy")),
            device_count=int(counts.get(runner.id, 0)),
            running_run_id=running.get(runner.id),
            error=error,
        ))
    await session.commit()
    return out


async def _get_or_404(session: AsyncSession, runner_id: str) -> Runner:
    runner = await session.get(Runner, runner_id)
    if runner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Runner not found")
    return runner


async def _verify_remote(address: str, token: str, fingerprint: str | None) -> tuple[str, dict[str, Any]]:
    """Pin (or check) the certificate and prove the token works. Returns (fingerprint, ping)."""
    try:
        parse_tcp_address(address)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if fingerprint:
        fingerprint = normalize_fingerprint(fingerprint)
    else:
        try:
            fingerprint = await fetch_tls_fingerprint(address)
        except RunnerUnavailable as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    client = RunnerClient(tcp_address=address, token=token, tls_fingerprint=fingerprint)
    try:
        info = await asyncio.wait_for(client.ping_info(), timeout=PING_TIMEOUT_S * 2)
    except TimeoutError:
        info = None
    if info is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Runner at {address} did not answer a ping with this token and "
            f"certificate (sha256 {fingerprint}).",
        )
    return fingerprint, info


@router.get("", response_model=list[RunnerOut])
async def list_runners(session: AsyncSession = Depends(get_session)) -> list[RunnerOut]:
    await ensure_local_runner(session)
    await session.commit()
    runners = list((await session.execute(
        select(Runner).order_by(Runner.created_at.asc(), Runner.name.asc())
    )).scalars())
    return await _serialize(session, runners)


@router.get("/{runner_id}", response_model=RunnerOut)
async def get_runner(runner_id: str, session: AsyncSession = Depends(get_session)) -> RunnerOut:
    runner = await _get_or_404(session, runner_id)
    return (await _serialize(session, [runner]))[0]


@router.post("", response_model=RunnerOut, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_admin)])
async def create_runner(
    body: RunnerCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(resolve_principal),
) -> RunnerOut:
    name = body.name.strip()
    if (await session.execute(select(Runner).where(Runner.name == name))).scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Runner name already in use")
    address = body.address.strip()
    fingerprint, info = await _verify_remote(address, body.token, body.tls_fingerprint)
    runner = Runner(
        id=str(ulid.ULID()),
        name=name,
        kind=RunnerKind.TCP.value,
        address=address,
        token=body.token,
        tls_fingerprint=fingerprint,
        enabled=True,
        host_info=info.get("host"),
    )
    session.add(runner)
    await session.commit()
    await audit_write(
        actor=principal.username,
        action="runner_created",
        target=runner.id,
        details={"name": name, "address": address, "tls_fingerprint": fingerprint},
    )
    return (await _serialize(session, [runner]))[0]


@router.patch("/{runner_id}", response_model=RunnerOut, dependencies=[Depends(require_admin)])
async def update_runner(
    runner_id: str,
    body: RunnerUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(resolve_principal),
) -> RunnerOut:
    runner = await _get_or_404(session, runner_id)
    changes: dict[str, Any] = {}

    if body.name is not None and body.name.strip() != runner.name:
        name = body.name.strip()
        clash = (await session.execute(select(Runner).where(Runner.name == name))).scalar_one_or_none()
        if clash is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Runner name already in use")
        runner.name = name
        changes["name"] = name

    if body.enabled is not None and body.enabled != runner.enabled:
        runner.enabled = body.enabled
        changes["enabled"] = body.enabled

    connection_change = (
        body.address is not None or body.token is not None
        or body.tls_fingerprint is not None or body.refetch_fingerprint
    )
    if connection_change:
        if runner.kind != RunnerKind.TCP.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The local runner's connection is configured by ANVIL_RUNNER_SOCKET",
            )
        address = (body.address or runner.address).strip()
        token = body.token or runner.token or ""
        fingerprint = None if body.refetch_fingerprint else (body.tls_fingerprint or runner.tls_fingerprint)
        fingerprint, info = await _verify_remote(address, token, fingerprint)
        runner.address = address
        runner.token = token
        runner.tls_fingerprint = fingerprint
        runner.host_info = info.get("host") or runner.host_info
        changes.update({
            "address": address,
            "token_changed": body.token is not None,
            "tls_fingerprint": fingerprint,
        })

    await session.commit()
    if changes:
        await audit_write(
            actor=principal.username, action="runner_updated", target=runner.id, details=changes
        )
    return (await _serialize(session, [runner]))[0]


@router.delete("/{runner_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_admin)])
async def delete_runner(
    runner_id: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(resolve_principal),
) -> None:
    if runner_id == LOCAL_RUNNER_ID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The local runner cannot be removed; disable it instead",
        )
    runner = await _get_or_404(session, runner_id)
    active = (await session.execute(
        select(func.count(Run.id)).where(
            Run.runner_id == runner_id,
            Run.status.in_([
                RunStatus.QUEUED.value, RunStatus.PREFLIGHT.value, RunStatus.RUNNING.value
            ]),
        )
    )).scalar_one()
    if active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Runner has {active} queued or running run(s); wait or abort them first",
        )
    # Devices keep their history; they just become unattached until seen again.
    await session.execute(
        update(Device)
        .where(Device.runner_id == runner_id)
        .values(
            runner_id=None,
            current_device_path=None,
            is_testable=False,
            exclusion_reason="runner host removed",
        )
    )
    name = runner.name
    await session.delete(runner)
    await session.commit()
    await audit_write(
        actor=principal.username, action="runner_deleted", target=runner_id, details={"name": name}
    )
