"""설정 API."""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

from backend.app.api.route_params import ConfigSnapshotId
from backend.app.core.config_schema import LabelingConfig
from backend.app.core.config_store import (
    get_config_snapshot,
    list_config_snapshots,
    load_active_config,
    rollback_to_snapshot,
    save_active_config,
)
from backend.app.deps import DbSession

router = APIRouter(prefix="/config", tags=["config"])


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
