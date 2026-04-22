from __future__ import annotations

import ulid
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from anvil.api import require_bearer
from anvil.auth import Principal, require_operator, resolve_principal
from anvil.db import get_session
from anvil.models import SavedComparison
from anvil.shares import generate_slug

router = APIRouter(
    prefix="/comparisons",
    tags=["comparisons"],
    dependencies=[Depends(require_bearer)],
)


class ComparisonIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    run_ids: list[str] = Field(min_length=1)


class ComparisonOut(BaseModel):
    id: str
    name: str
    description: str | None
    run_ids: list[str]
    share_slug: str | None
    created_by: str | None
    created_at: str
    updated_at: str


def _to_out(row: SavedComparison) -> ComparisonOut:
    return ComparisonOut(
        id=row.id,
        name=row.name,
        description=row.description,
        run_ids=list(row.run_ids or []),
        share_slug=row.share_slug,
        created_by=row.created_by,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


@router.get("", response_model=list[ComparisonOut])
async def list_comparisons(
    session: AsyncSession = Depends(get_session),
) -> list[ComparisonOut]:
    rows = (
        await session.execute(
            select(SavedComparison).order_by(SavedComparison.updated_at.desc())
        )
    ).scalars().all()
    return [_to_out(r) for r in rows]


@router.post(
    "", response_model=ComparisonOut, dependencies=[Depends(require_operator)]
)
async def create_comparison(
    payload: ComparisonIn,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(resolve_principal),
) -> ComparisonOut:
    row = SavedComparison(
        id=str(ulid.ULID()),
        name=payload.name,
        description=payload.description,
        run_ids=list(payload.run_ids),
        created_by=principal.user_id,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _to_out(row)


@router.get("/{comp_id}", response_model=ComparisonOut)
async def get_comparison(
    comp_id: str, session: AsyncSession = Depends(get_session)
) -> ComparisonOut:
    row = await session.get(SavedComparison, comp_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return _to_out(row)


@router.put(
    "/{comp_id}", response_model=ComparisonOut, dependencies=[Depends(require_operator)]
)
async def update_comparison(
    comp_id: str,
    payload: ComparisonIn,
    session: AsyncSession = Depends(get_session),
) -> ComparisonOut:
    row = await session.get(SavedComparison, comp_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    row.name = payload.name
    row.description = payload.description
    row.run_ids = list(payload.run_ids)
    await session.commit()
    await session.refresh(row)
    return _to_out(row)


@router.delete("/{comp_id}", dependencies=[Depends(require_operator)])
async def delete_comparison(
    comp_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    row = await session.get(SavedComparison, comp_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    await session.delete(row)
    await session.commit()
    return {"deleted": comp_id}


@router.post("/{comp_id}/share", dependencies=[Depends(require_operator)])
async def create_comparison_share(
    comp_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    row = await session.get(SavedComparison, comp_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    row.share_slug = generate_slug()
    await session.commit()
    return {"id": row.id, "share_slug": row.share_slug}


@router.delete("/{comp_id}/share", dependencies=[Depends(require_operator)])
async def revoke_comparison_share(
    comp_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    row = await session.get(SavedComparison, comp_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    row.share_slug = None
    await session.commit()
    return {"id": row.id, "share_slug": None}
