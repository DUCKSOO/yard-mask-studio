"""타일 API."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from backend.app.api.schemas import TileStatusPatch
from backend.app.core.tenant import assert_tenant_allowed
from backend.app.deps import DbSession
from backend.app.services import dataset_service
from backend.app.tiling import tile_index

router = APIRouter(
    prefix="/tenants/{tenant_id}/datasets/{dataset_id}/tiles",
    tags=["tiles"],
)


def _tenant(request: Request, tenant_id: str) -> None:
    try:
        assert_tenant_allowed(tenant_id, request.app.state.settings.default_tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


@router.get("")
def list_tiles(
    tenant_id: str,
    dataset_id: str,
    request: Request,
    db: DbSession,
    status: str | None = None,
    limit: int = 20,
) -> list[dict]:
    _tenant(request, tenant_id)
    if dataset_service.get_dataset(db, tenant_id, dataset_id) is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    rows = tile_index.list_tiles(db, tenant_id, dataset_id, status=status, limit=limit)
    out = []
    for r in rows:
        meta = json.loads(r.metadata_json) if r.metadata_json else {"tile_id": r.tile_id}
        out.append({"tile_id": r.tile_id, "status": r.status, "metadata": meta})
    return out


@router.get("/{tile_id}/image")
def get_tile_image(
    tenant_id: str,
    dataset_id: str,
    tile_id: str,
    request: Request,
    db: DbSession,
):
    _tenant(request, tenant_id)
    row = tile_index.get_tile(db, tenant_id, dataset_id, tile_id)
    if row is None:
        raise HTTPException(status_code=404, detail="tile not found")
    repo_root: Path = request.app.state.repo_root
    path = dataset_service.dataset_dir(repo_root, tenant_id, dataset_id) / "images" / f"{tile_id}.png"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="tile image not on disk")
    return FileResponse(path, media_type="image/png")


@router.get("/{tile_id}/metadata")
def get_tile_metadata(
    tenant_id: str,
    dataset_id: str,
    tile_id: str,
    request: Request,
    db: DbSession,
) -> dict:
    _tenant(request, tenant_id)
    row = tile_index.get_tile(db, tenant_id, dataset_id, tile_id)
    if row is None or not row.metadata_json:
        raise HTTPException(status_code=404, detail="tile not found")
    return json.loads(row.metadata_json)


@router.patch("/{tile_id}/status")
def patch_tile_status(
    tenant_id: str,
    dataset_id: str,
    tile_id: str,
    body: TileStatusPatch,
    request: Request,
    db: DbSession,
) -> dict:
    _tenant(request, tenant_id)
    row = tile_index.update_tile_status(db, tenant_id, dataset_id, tile_id, body.status)
    if row is None:
        raise HTTPException(status_code=404, detail="tile not found")
    return {"tile_id": row.tile_id, "status": row.status}
