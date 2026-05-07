"""데이터셋 API."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from backend.app.api.schemas import DatasetCreateRequest, TileGenerateRequest
from backend.app.core.config_schema import LabelingConfig
from backend.app.core.tenant import assert_tenant_allowed
from backend.app.deps import DbSession
from backend.app.services import dataset_service

router = APIRouter(prefix="/tenants/{tenant_id}/datasets", tags=["datasets"])


def _tenant(request: Request, tenant_id: str) -> None:
    try:
        assert_tenant_allowed(tenant_id, request.app.state.settings.default_tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


@router.post("", status_code=201)
def create_dataset(
    tenant_id: str,
    body: DatasetCreateRequest,
    request: Request,
    db: DbSession,
) -> dict:
    _tenant(request, tenant_id)
    try:
        row = dataset_service.create_dataset(
            db,
            tenant_id=tenant_id,
            dataset_id=body.dataset_id,
            source_geotiff=body.source_geotiff,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {"dataset_id": row.dataset_id, "id": row.id, "config_snapshot_id": row.config_snapshot_id}


@router.get("")
def list_datasets(tenant_id: str, request: Request, db: DbSession) -> list[dict]:
    _tenant(request, tenant_id)
    rows = dataset_service.list_datasets(db, tenant_id)
    return [
        {
            "dataset_id": r.dataset_id,
            "config_snapshot_id": r.config_snapshot_id,
            "source_geotiff": r.source_geotiff,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.get("/{dataset_id}", response_model=None)
def get_dataset_detail(tenant_id: str, dataset_id: str, request: Request, db: DbSession) -> dict:
    _tenant(request, tenant_id)
    row = dataset_service.get_dataset(db, tenant_id, dataset_id)
    if row is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    return {
        "dataset_id": row.dataset_id,
        "config_snapshot_id": row.config_snapshot_id,
        "source_geotiff": row.source_geotiff,
        "created_at": row.created_at,
    }


@router.get("/{dataset_id}/config", response_model=LabelingConfig)
def get_dataset_config(tenant_id: str, dataset_id: str, request: Request, db: DbSession) -> LabelingConfig:
    _tenant(request, tenant_id)
    try:
        return dataset_service.get_dataset_labeling_config(db, tenant_id, dataset_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="dataset not found") from None


@router.post("/{dataset_id}/tiles/generate", status_code=202)
def generate_tiles(
    tenant_id: str,
    dataset_id: str,
    request: Request,
    db: DbSession,
    body: TileGenerateRequest | None = None,
) -> dict:
    _tenant(request, tenant_id)
    body = body or TileGenerateRequest()
    repo_root: Path = request.app.state.repo_root
    try:
        n = dataset_service.generate_tiles(
            db,
            repo_root,
            tenant_id,
            dataset_id,
            source_geotiff=body.source_geotiff,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="dataset not found") from None
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"tiles_created": n}


@router.post("/{dataset_id}/export/unet")
def export_unet_stub() -> None:
    raise HTTPException(status_code=501, detail="Step 5: U-Net export not implemented")
