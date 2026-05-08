"""데이터셋 API."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Request

from backend.app.api.route_params import DatasetId, TenantId
from backend.app.api.schemas import DatasetCreateRequest, TileGenerateRequest
from backend.app.dataset.dataset_exporter import export_unet_dataset
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


@router.post(
    "",
    status_code=201,
    summary="데이터셋 생성",
    description="""
새 데이터셋을 등록하고, **당시 활성 `LabelingConfig` 스냅샷**을 `dataset_config_snapshots`에 고정합니다.

- `source_geotiff`: `data/source/{tenant_id}/raw_geotiff/` 아래 파일명만 전달 (경로 없음).
- 동일 `dataset_id`가 이미 있으면 **409**.
""",
)
def create_dataset(
    tenant_id: TenantId,
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


@router.get(
    "",
    summary="데이터셋 목록",
    description="테넌트에 속한 데이터셋 요약(`dataset_id`, 스냅샷 id, 원본 파일명, 생성 시각)을 반환합니다.",
)
def list_datasets(tenant_id: TenantId, request: Request, db: DbSession) -> list[dict]:
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


@router.get(
    "/{dataset_id}",
    response_model=None,
    summary="데이터셋 상세",
    description="단일 데이터셋 메타입니다. 없으면 **404**.",
)
def get_dataset_detail(tenant_id: TenantId, dataset_id: DatasetId, request: Request, db: DbSession) -> dict:
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


@router.get(
    "/{dataset_id}/config",
    response_model=LabelingConfig,
    summary="데이터셋에 고정된 라벨링 설정",
    description="데이터셋 생성 시점에 스냅샷으로 묶인 `LabelingConfig`입니다. 이후 전역 `active_config`를 바꿔도 이 데이터셋의 타일 메타는 이 스냅샷을 참조합니다.",
)
def get_dataset_config(tenant_id: TenantId, dataset_id: DatasetId, request: Request, db: DbSession) -> LabelingConfig:
    _tenant(request, tenant_id)
    try:
        return dataset_service.get_dataset_labeling_config(db, tenant_id, dataset_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="dataset not found") from None


@router.post(
    "/{dataset_id}/tiles/generate",
    status_code=202,
    summary="타일 일괄 생성",
    description="""
활성 설정의 `tiling`을 사용해 GeoTIFF를 읽고, `data/datasets/{tenant}/{dataset}/images/*.png` 및 `metadata/*.json`을 만들고 타일 인덱스를 갱신합니다.

- 본문 `source_geotiff`로 이번 실행만 다른 원본을 지정할 수 있습니다(미지정 시 데이터셋에 저장된 파일명).
- 원본 파일이 없으면 **400**, 데이터셋이 없으면 **404**.
""",
)
def generate_tiles(
    tenant_id: TenantId,
    dataset_id: DatasetId,
    request: Request,
    db: DbSession,
    body: TileGenerateRequest | None = Body(
        default=None,
        description="선택. 이번 생성만 다른 `source_geotiff`를 쓸 때 본문에 파일명을 넣습니다. 빈 본문 허용.",
    ),
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


@router.post(
    "/{dataset_id}/export/unet",
    summary="U-Net export",
    description="""
`status=labeled`인 annotation이 있고, 해당 타일의 `images/{tile_id}.png`·`masks/{tile_id}.png`가 모두 있을 때만 포함합니다.

- 라벨된 샘플이 없으면 **400**.
- 데이터셋이 없으면 **404**.
- 산출물: `data/exports/{tenant}/{dataset}/{export_id}/` (images, masks, splits, manifest, config_snapshot.yaml, classes.json).
""",
)
def export_unet(
    tenant_id: TenantId,
    dataset_id: DatasetId,
    request: Request,
    db: DbSession,
) -> dict:
    _tenant(request, tenant_id)
    repo_root: Path = request.app.state.repo_root
    try:
        export_id = export_unet_dataset(db, repo_root, tenant_id, dataset_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="dataset not found") from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {"export_id": export_id}
