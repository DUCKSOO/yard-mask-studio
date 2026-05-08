"""타일 API."""

from __future__ import annotations

import json
from pathlib import Path

from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import FileResponse

from backend.app.api.route_params import DatasetId, TenantId, TileId
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


@router.get(
    "",
    summary="타일 목록",
    description="""
인덱스(DB)에 등록된 타일을 `tile_id`, `status`, `metadata`와 함께 반환합니다.

- 데이터셋이 없으면 **404** (프론트에서 자주 보는 케이스 → 먼저 데이터셋 생성).
- `metadata`에는 GSD, `dataset_config_snapshot_id`, `geo_transform` 등이 포함될 수 있습니다.
""",
)
def list_tiles(
    tenant_id: TenantId,
    dataset_id: DatasetId,
    request: Request,
    db: DbSession,
    status: Annotated[
        str | None,
        Query(description="타일 상태 필터(예: unlabeled, labeled). 미지정이면 전체."),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=10_000, description="최대 반환 개수(기본 20)."),
    ] = 20,
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


@router.get(
    "/{tile_id}/image",
    summary="타일 PNG 이미지",
    description="라벨링에 쓰는 RGB 타일 PNG 바이너리(`image/png`). `<img src>` 또는 다운로드에 사용.",
)
def get_tile_image(
    tenant_id: TenantId,
    dataset_id: DatasetId,
    tile_id: TileId,
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


@router.get(
    "/{tile_id}/metadata",
    summary="타일 메타데이터 JSON",
    description="타일 생성 시 저장한 JSON(좌표, overlap, 측정 GSD, CRS, 스냅샷 id 등).",
)
def get_tile_metadata(
    tenant_id: TenantId,
    dataset_id: DatasetId,
    tile_id: TileId,
    request: Request,
    db: DbSession,
) -> dict:
    _tenant(request, tenant_id)
    row = tile_index.get_tile(db, tenant_id, dataset_id, tile_id)
    if row is None or not row.metadata_json:
        raise HTTPException(status_code=404, detail="tile not found")
    return json.loads(row.metadata_json)


@router.patch(
    "/{tile_id}/status",
    summary="타일 상태 변경",
    description="`unlabeled` / `labeled` / `in_progress` 등 워크플로 상태 문자열을 갱신합니다.",
)
def patch_tile_status(
    tenant_id: TenantId,
    dataset_id: DatasetId,
    tile_id: TileId,
    request: Request,
    db: DbSession,
    body: TileStatusPatch = Body(
        ...,
        description="갱신할 타일 상태 문자열을 담은 한 필드(`status`).",
    ),
) -> dict:
    _tenant(request, tenant_id)
    row = tile_index.update_tile_status(db, tenant_id, dataset_id, tile_id, body.status)
    if row is None:
        raise HTTPException(status_code=404, detail="tile not found")
    return {"tile_id": row.tile_id, "status": row.status}
