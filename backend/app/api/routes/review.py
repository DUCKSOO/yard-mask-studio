"""검수 큐 API — labeling-tool-plan-v3.md §10.6."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Query, Request

from sqlalchemy import select

from backend.app.api.route_params import DatasetId, TenantId, TileId
from backend.app.api.schemas import ReviewRejectBody
from backend.app.core.db import ReviewQueueRow
from backend.app.core.tenant import assert_tenant_allowed
from backend.app.deps import DbSession
from backend.app.services.review_queue_service import upsert_review_row
from backend.app.tiling import tile_index

router = APIRouter(tags=["review"])
logger = logging.getLogger(__name__)


def _tenant(request: Request, tenant_id: str) -> None:
    try:
        assert_tenant_allowed(tenant_id, request.app.state.settings.default_tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


@router.get(
    "/tenants/{tenant_id}/review/queue",
    summary="검수 큐 목록",
    description="테넌트 단위 검수 행 조회. `status=pending`(기본) | `approved` | `rejected` | `all`.",
)
def get_review_queue(
    tenant_id: TenantId,
    request: Request,
    db: DbSession,
    status: Annotated[
        str,
        Query(
            description="필터: pending(기본), approved, rejected, all(전체).",
        ),
    ] = "pending",
) -> list[dict]:
    _tenant(request, tenant_id)
    stmt = select(ReviewQueueRow).where(ReviewQueueRow.tenant_id == tenant_id)
    if status != "all":
        stmt = stmt.where(ReviewQueueRow.status == status)
    stmt = stmt.order_by(ReviewQueueRow.created_at.desc())
    rows = list(db.scalars(stmt))
    return [
        {
            "tile_id": r.tile_id,
            "dataset_id": r.dataset_id,
            "status": r.status,
            "note": r.note,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.post(
    "/tenants/{tenant_id}/datasets/{dataset_id}/tiles/{tile_id}/review/approve",
    summary="검수 승인",
    description="타일이 존재해야 합니다. `review_queue` 행을 upsert하고 `tiles.status`를 `approved`로 맞춥니다.",
)
def review_approve(
    tenant_id: TenantId,
    dataset_id: DatasetId,
    tile_id: TileId,
    request: Request,
    db: DbSession,
) -> dict:
    _tenant(request, tenant_id)
    if tile_index.get_tile(db, tenant_id, dataset_id, tile_id) is None:
        raise HTTPException(status_code=404, detail="tile not found")
    upsert_review_row(db, tenant_id=tenant_id, dataset_id=dataset_id, tile_id=tile_id, status="approved", note=None)
    tile_index.update_tile_status(db, tenant_id, dataset_id, tile_id, "approved", commit=False)
    db.commit()
    logger.info("review/approve tenant=%s dataset_id=%s tile_id=%s", tenant_id, dataset_id, tile_id)
    return {"ok": True, "status": "approved"}


@router.post(
    "/tenants/{tenant_id}/datasets/{dataset_id}/tiles/{tile_id}/review/reject",
    summary="검수 거부",
    description="`note`에 거부 사유를 넣을 수 있습니다. `tiles.status`는 `rejected`로 갱신됩니다.",
)
def review_reject(
    tenant_id: TenantId,
    dataset_id: DatasetId,
    tile_id: TileId,
    request: Request,
    db: DbSession,
    body: ReviewRejectBody = Body(default_factory=ReviewRejectBody),
) -> dict:
    _tenant(request, tenant_id)
    if tile_index.get_tile(db, tenant_id, dataset_id, tile_id) is None:
        raise HTTPException(status_code=404, detail="tile not found")
    upsert_review_row(
        db,
        tenant_id=tenant_id,
        dataset_id=dataset_id,
        tile_id=tile_id,
        status="rejected",
        note=body.note,
    )
    tile_index.update_tile_status(db, tenant_id, dataset_id, tile_id, "rejected", commit=False)
    db.commit()
    logger.info(
        "review/reject tenant=%s dataset_id=%s tile_id=%s note=%s",
        tenant_id,
        dataset_id,
        tile_id,
        (body.note[:80] + "…") if body.note and len(body.note) > 80 else body.note,
    )
    return {"ok": True, "status": "rejected"}
