"""타일 annotation 저장·조회·삭제 — RLE → PNG."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Request, Response
from PIL import Image
from sqlalchemy import select

from backend.app.annotation import mask_service
from backend.app.api.route_params import DatasetId, TenantId, TileId
from backend.app.api.schemas import AnnotationSaveRequest
from backend.app.core.db import AnnotationRow
from backend.app.core.tenant import assert_tenant_allowed
from backend.app.deps import DbSession
from backend.app.services import dataset_service
from backend.app.services.review_queue_service import delete_review_row
from backend.app.tiling import tile_index

router = APIRouter(
    prefix="/tenants/{tenant_id}/datasets/{dataset_id}/tiles/{tile_id}",
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


def _annotation_row(
    db,
    tenant_id: str,
    dataset_id: str,
    tile_id: str,
) -> AnnotationRow | None:
    stmt = select(AnnotationRow).where(
        AnnotationRow.tenant_id == tenant_id,
        AnnotationRow.dataset_id == dataset_id,
        AnnotationRow.tile_id == tile_id,
    )
    return db.scalars(stmt).first()


@router.post(
    "/annotation",
    summary="최종 annotation 저장 (RLE → PNG)",
)
def save_annotation(
    tenant_id: TenantId,
    dataset_id: DatasetId,
    tile_id: TileId,
    request: Request,
    db: DbSession,
    body: AnnotationSaveRequest = Body(...),
) -> dict:
    _tenant(request, tenant_id)
    if tile_index.get_tile(db, tenant_id, dataset_id, tile_id) is None:
        raise HTTPException(status_code=404, detail="tile not found")

    repo_root: Path = request.app.state.repo_root
    img_path = dataset_service.dataset_dir(repo_root, tenant_id, dataset_id) / "images" / f"{tile_id}.png"
    if not img_path.is_file():
        raise HTTPException(status_code=404, detail="tile image missing")

    with Image.open(img_path) as im:
        im_w, im_h = im.size
    if body.class_mask.width != im_w or body.class_mask.height != im_h:
        raise HTTPException(
            status_code=422,
            detail=f"class_mask size {body.class_mask.width}x{body.class_mask.height} != tile {im_w}x{im_h}",
        )

    try:
        arr = mask_service.decode_rle_vl(body.class_mask.counts, body.class_mask.height, body.class_mask.width)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    mask_path = dataset_service.dataset_dir(repo_root, tenant_id, dataset_id) / "masks" / f"{tile_id}.png"
    mask_service.save_mask_png(mask_path, arr)

    now = datetime.now(UTC).isoformat()
    payload = body.model_dump(mode="json", exclude_none=True)
    ann_json = json.dumps(payload, ensure_ascii=False)

    row = _annotation_row(db, tenant_id, dataset_id, tile_id)
    if row is None:
        row = AnnotationRow(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            tile_id=tile_id,
            annotation_json=ann_json,
            updated_at=now,
        )
        db.add(row)
    else:
        row.annotation_json = ann_json
        row.updated_at = now

    tile_index.update_tile_status(db, tenant_id, dataset_id, tile_id, body.status, commit=False)
    db.commit()

    rel = mask_path.resolve().relative_to(repo_root.resolve())
    logger.info(
        "annotation saved tenant=%s dataset_id=%s tile_id=%s",
        tenant_id,
        dataset_id,
        tile_id,
    )
    return {"saved": True, "mask_path": rel.as_posix()}


@router.get(
    "/annotation",
    summary="annotation 조회",
)
def get_annotation(
    tenant_id: TenantId,
    dataset_id: DatasetId,
    tile_id: TileId,
    request: Request,
    db: DbSession,
) -> dict:
    _tenant(request, tenant_id)
    row = _annotation_row(db, tenant_id, dataset_id, tile_id)
    if row is None:
        raise HTTPException(status_code=404, detail="annotation not found")
    return json.loads(row.annotation_json)


@router.delete(
    "/annotation",
    summary="annotation 삭제",
    status_code=204,
    response_class=Response,
)
def delete_annotation(
    tenant_id: TenantId,
    dataset_id: DatasetId,
    tile_id: TileId,
    request: Request,
    db: DbSession,
) -> Response:
    _tenant(request, tenant_id)
    row = _annotation_row(db, tenant_id, dataset_id, tile_id)
    if row is None:
        raise HTTPException(status_code=404, detail="annotation not found")

    repo_root: Path = request.app.state.repo_root
    mask_path = dataset_service.dataset_dir(repo_root, tenant_id, dataset_id) / "masks" / f"{tile_id}.png"
    if mask_path.is_file():
        mask_path.unlink()

    db.delete(row)
    delete_review_row(db, tenant_id=tenant_id, dataset_id=dataset_id, tile_id=tile_id)
    tile_index.update_tile_status(db, tenant_id, dataset_id, tile_id, "unlabeled", commit=False)
    db.commit()

    logger.info("annotation deleted tenant=%s dataset_id=%s tile_id=%s", tenant_id, dataset_id, tile_id)
    return Response(status_code=204)
