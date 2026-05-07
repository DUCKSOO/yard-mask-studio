"""Annotation API."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from backend.app.annotation import mask_service
from backend.app.api.schemas import AnnotationSaveRequest
from backend.app.core.db import AnnotationRow
from backend.app.core.tenant import assert_tenant_allowed
from backend.app.deps import DbSession
from backend.app.services import dataset_service
from backend.app.tiling import tile_index

router = APIRouter(
    prefix="/tenants/{tenant_id}/datasets/{dataset_id}/tiles/{tile_id}/annotation",
    tags=["annotation"],
)


def _tenant(request: Request, tenant_id: str) -> None:
    try:
        assert_tenant_allowed(tenant_id, request.app.state.settings.default_tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


@router.post("")
def save_annotation(
    tenant_id: str,
    dataset_id: str,
    tile_id: str,
    body: AnnotationSaveRequest,
    request: Request,
    db: DbSession,
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
    return {"saved": True, "mask_path": str(mask_path.relative_to(repo_root))}


@router.get("")
def get_annotation(
    tenant_id: str,
    dataset_id: str,
    tile_id: str,
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


@router.delete("", status_code=204)
def delete_annotation(
    tenant_id: str,
    dataset_id: str,
    tile_id: str,
    request: Request,
    db: DbSession,
) -> None:
    _tenant(request, tenant_id)
    stmt = select(AnnotationRow).where(
        AnnotationRow.tenant_id == tenant_id,
        AnnotationRow.dataset_id == dataset_id,
        AnnotationRow.tile_id == tile_id,
    )
    row = db.scalars(stmt).first()
    if row:
        db.delete(row)
        db.commit()
    repo_root: Path = request.app.state.repo_root
    mask_path = dataset_service.dataset_dir(repo_root, tenant_id, dataset_id) / "masks" / f"{tile_id}.png"
    if mask_path.is_file():
        mask_path.unlink()
