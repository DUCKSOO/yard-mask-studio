"""Annotation API."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Request
from sqlalchemy import select

from backend.app.annotation import mask_service
from backend.app.api.route_params import DatasetId, TenantId, TileId
from backend.app.api.schemas import AnnotationSaveRequest
from backend.app.core.db import AnnotationRow
from backend.app.core.tenant import assert_tenant_allowed
from backend.app.deps import DbSession
from backend.app.services import dataset_service
from backend.app.services.review_queue_service import delete_review_row, upsert_review_row
from backend.app.tiling import tile_index

router = APIRouter(
    prefix="/tenants/{tenant_id}/datasets/{dataset_id}/tiles/{tile_id}/annotation",
    tags=["annotation"],
)
logger = logging.getLogger(__name__)


def _tenant(request: Request, tenant_id: str) -> None:
    try:
        assert_tenant_allowed(tenant_id, request.app.state.settings.default_tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


@router.post(
    "",
    summary="annotation 저장",
    description="""
클래스 마스크를 **value:length RLE**(행 우선 C-order)로 받아 PNG(`masks/{tile_id}.png`)로 저장하고 DB `annotations`에 JSON을 기록합니다.

- `class_mask`의 height/width는 타일 이미지와 일치해야 합니다.
- 저장 후 타일 `status`를 요청의 `status`로 맞춥니다.
""",
)
def save_annotation(
    tenant_id: TenantId,
    dataset_id: DatasetId,
    tile_id: TileId,
    request: Request,
    db: DbSession,
    body: AnnotationSaveRequest = Body(
        ...,
        description="타일 상태·RLE 마스크. `class_mask.counts`는 C-order value:length 형식.",
    ),
) -> dict:
    _tenant(request, tenant_id)
    if tile_index.get_tile(db, tenant_id, dataset_id, tile_id) is None:
        raise HTTPException(status_code=404, detail="tile not found")
    m = body.class_mask
    try:
        mask_arr = mask_service.decode_rle_vl(m.counts, m.height, m.width)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    repo_root: Path = request.app.state.repo_root
    mask_dir = dataset_service.dataset_dir(repo_root, tenant_id, dataset_id) / "masks"
    mask_path = mask_dir / f"{tile_id}.png"
    mask_service.save_mask_png(mask_path, mask_arr)

    payload = body.model_dump()
    now = datetime.now(UTC).isoformat()
    stmt = select(AnnotationRow).where(
        AnnotationRow.tenant_id == tenant_id,
        AnnotationRow.dataset_id == dataset_id,
        AnnotationRow.tile_id == tile_id,
    )
    row = db.scalars(stmt).first()
    if row is None:
        row = AnnotationRow(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            tile_id=tile_id,
            annotation_json=json.dumps(payload),
            updated_at=now,
        )
        db.add(row)
    else:
        row.annotation_json = json.dumps(payload)
        row.updated_at = now
    db.commit()
    tile_index.update_tile_status(db, tenant_id, dataset_id, tile_id, body.status)
    if body.status == "labeled":
        upsert_review_row(
            db,
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            tile_id=tile_id,
            status="pending",
            note=None,
        )
        db.commit()
    logger.info(
        "annotation saved tenant=%s dataset_id=%s tile_id=%s status=%s mask=%sx%s",
        tenant_id,
        dataset_id,
        tile_id,
        body.status,
        m.width,
        m.height,
    )
    return {"saved": True, "mask_path": str(mask_path.relative_to(repo_root))}


@router.get(
    "",
    summary="annotation 조회",
    description="저장 시 직렬화한 JSON(`status`, `mask_encoding`, `class_mask`)을 그대로 반환합니다. 없으면 **404**.",
)
def get_annotation(
    tenant_id: TenantId,
    dataset_id: DatasetId,
    tile_id: TileId,
    request: Request,
    db: DbSession,
) -> dict:
    _tenant(request, tenant_id)
    stmt = select(AnnotationRow).where(
        AnnotationRow.tenant_id == tenant_id,
        AnnotationRow.dataset_id == dataset_id,
        AnnotationRow.tile_id == tile_id,
    )
    row = db.scalars(stmt).first()
    if row is None:
        raise HTTPException(status_code=404, detail="annotation not found")
    return json.loads(row.annotation_json)


@router.delete(
    "",
    status_code=204,
    summary="annotation 삭제",
    description="""
DB 행을 지우고 `masks/{tile_id}.png`가 있으면 파일도 삭제합니다.
타일 상태를 `unlabeled`로 되돌리고, 해당 타일의 검수 큐 행이 있으면 제거합니다.
""",
)
def delete_annotation(
    tenant_id: TenantId,
    dataset_id: DatasetId,
    tile_id: TileId,
    request: Request,
    db: DbSession,
) -> None:
    _tenant(request, tenant_id)
    if tile_index.get_tile(db, tenant_id, dataset_id, tile_id) is None:
        raise HTTPException(status_code=404, detail="tile not found")

    stmt = select(AnnotationRow).where(
        AnnotationRow.tenant_id == tenant_id,
        AnnotationRow.dataset_id == dataset_id,
        AnnotationRow.tile_id == tile_id,
    )
    row = db.scalars(stmt).first()
    if row:
        db.delete(row)

    repo_root: Path = request.app.state.repo_root
    mask_path = dataset_service.dataset_dir(repo_root, tenant_id, dataset_id) / "masks" / f"{tile_id}.png"
    if mask_path.is_file():
        mask_path.unlink()

    tile_index.update_tile_status(db, tenant_id, dataset_id, tile_id, "unlabeled", commit=False)
    delete_review_row(db, tenant_id=tenant_id, dataset_id=dataset_id, tile_id=tile_id)
    db.commit()
    logger.info("annotation deleted tenant=%s dataset_id=%s tile_id=%s", tenant_id, dataset_id, tile_id)
