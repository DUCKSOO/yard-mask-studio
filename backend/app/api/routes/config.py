"""설정 API."""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Request
from sqlalchemy import func, select

from backend.app.api.route_params import ConfigSnapshotId, TenantId
from backend.app.api.schemas import ConfigImpactRequest, ConfigImpactResponse, DatasetImpactItem
from backend.app.core.config_schema import LabelingConfig
from backend.app.core.config_store import (
    get_config_snapshot,
    list_config_snapshots,
    load_active_config,
    rollback_to_snapshot,
    save_active_config,
)
from backend.app.core.db import TileRow
from backend.app.core.tenant import assert_tenant_allowed
from backend.app.deps import DbSession

router = APIRouter(prefix="/config", tags=["config"])


def _tenant(request: Request, tenant_id: str) -> None:
    try:
        assert_tenant_allowed(tenant_id, request.app.state.settings.default_tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


def _tiling_stride_px(tile_size: int, tile_overlap: int) -> float:
    return float(max(1, tile_size - tile_overlap))


@router.get(
    "",
    response_model=LabelingConfig,
    summary="활성 라벨링 설정 조회",
    description="DB `active_config`의 현재 `LabelingConfig`를 반환합니다. 미초기화 시 500입니다.",
)
def get_config(db: DbSession) -> LabelingConfig:
    cfg = load_active_config(db)
    if cfg is None:
        raise HTTPException(status_code=500, detail="active_config not initialized")
    return cfg


@router.post(
    "",
    response_model=LabelingConfig,
    summary="활성 라벨링 설정 저장",
    description="요청 본문 전체를 새 활성 설정으로 저장합니다. 이전 설정은 변경 스냅샷에 남습니다.",
)
def post_config(
    db: DbSession,
    body: LabelingConfig = Body(
        ...,
        description="저장할 전역 활성 설정. 타일링·지리·그리드·SAM·클래스 정의·dataset 출력 설정을 포함합니다.",
    ),
) -> LabelingConfig:
    return save_active_config(db, body, reason="user_edit")


@router.post(
    "/validate",
    summary="설정 검증(자리)",
    description="현재는 본문을 그대로 `proposed`로 돌려주는 플레이스홀더입니다. 향후 GSD·overlap 등 경고를 채울 수 있습니다.",
)
def validate_config(
    body: LabelingConfig = Body(
        ...,
        description="검증 대상 설정(현재는 응답의 `proposed`에 그대로 반영).",
    ),
) -> dict:
    return {"ok": True, "warnings": [], "proposed": body.model_dump()}


@router.post(
    "/rollback/{snapshot_id}",
    response_model=LabelingConfig,
    summary="설정 롤백",
    description="`config_change_snapshots`에 저장된 과거 설정으로 되돌립니다. 잘못된 `snapshot_id`면 404.",
)
def rollback_config(snapshot_id: ConfigSnapshotId, db: DbSession) -> LabelingConfig:
    try:
        return rollback_to_snapshot(db, snapshot_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get(
    "/snapshots",
    summary="설정 변경 스냅샷 목록",
    description="최근 사용자 설정 변경 이력(id, reason, created_at)입니다.",
)
def snapshots(db: DbSession) -> list[dict]:
    rows = list_config_snapshots(db)
    return [{"id": r.id, "reason": r.reason, "created_at": r.created_at} for r in rows]


@router.get(
    "/snapshots/{snapshot_id}",
    summary="설정 스냅샷 단건",
    description="해당 스냅샷의 `config_json` 원문을 포함해 반환합니다.",
)
def snapshot_detail(snapshot_id: ConfigSnapshotId, db: DbSession) -> dict:
    row = get_config_snapshot(db, snapshot_id)
    if row is None:
        raise HTTPException(status_code=404, detail="snapshot not found")
    return {"id": row.id, "reason": row.reason, "created_at": row.created_at, "config_json": row.config_json}


@router.post(
    "/tenants/{tenant_id}/impact",
    response_model=ConfigImpactResponse,
    summary="설정 변경 영향도 분석",
    description="""
가상의 `tile_size` / `tile_overlap`에 대해, 현재 테넌트 타일 수 대비 **대략적인** 타일 수 변화를 추정합니다.
DB·디스크는 변경하지 않습니다.

- 생략한 필드는 **활성 설정** 값을 사용합니다.
- 추정식: 타일 수 ∝ 1 / stride², stride = max(1, tile_size - tile_overlap).
""",
)
def config_impact(
    tenant_id: TenantId,
    request: Request,
    db: DbSession,
    body: ConfigImpactRequest = Body(
        ...,
        description="분석할 tiling 파라미터. 둘 다 생략이면 활성 설정과 동일하여 delta는 0에 가깝습니다.",
    ),
) -> ConfigImpactResponse:
    _tenant(request, tenant_id)
    cfg = load_active_config(db)
    if cfg is None:
        raise HTTPException(status_code=500, detail="active_config not initialized")

    old_ts = int(cfg.tiling.tile_size)
    old_ov = int(cfg.tiling.tile_overlap)
    new_ts = int(body.tile_size) if body.tile_size is not None else old_ts
    new_ov = int(body.tile_overlap) if body.tile_overlap is not None else old_ov
    if new_ov >= new_ts:
        raise HTTPException(
            status_code=400,
            detail="effective tile_overlap must be less than tile_size",
        )

    old_stride = _tiling_stride_px(old_ts, old_ov)
    new_stride = _tiling_stride_px(new_ts, new_ov)
    ratio = (old_stride / new_stride) ** 2

    stmt = (
        select(TileRow.dataset_id, func.count(TileRow.id))
        .where(TileRow.tenant_id == tenant_id)
        .group_by(TileRow.dataset_id)
        .order_by(TileRow.dataset_id)
    )
    rows = list(db.execute(stmt).all())

    items: list[DatasetImpactItem] = []
    current_total = 0
    simulated_total = 0
    for ds_id, cnt in rows:
        c = int(cnt)
        current_total += c
        sim = max(0, round(c * ratio))
        simulated_total += sim
        items.append(
            DatasetImpactItem(
                dataset_id=str(ds_id),
                tile_count=c,
                simulated_tile_count=sim,
            ),
        )

    return ConfigImpactResponse(
        current_tile_count=current_total,
        simulated_tile_count=simulated_total,
        delta=simulated_total - current_total,
        affected_datasets=items,
    )
