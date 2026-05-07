"""설정 API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

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


@router.get("", response_model=LabelingConfig)
def get_config(db: DbSession) -> LabelingConfig:
    cfg = load_active_config(db)
    if cfg is None:
        raise HTTPException(status_code=500, detail="active_config not initialized")
    return cfg


@router.post("", response_model=LabelingConfig)
def post_config(body: LabelingConfig, db: DbSession) -> LabelingConfig:
    return save_active_config(db, body, reason="user_edit")


@router.post("/validate")
def validate_config(body: LabelingConfig) -> dict:
    return {"ok": True, "warnings": [], "proposed": body.model_dump()}


@router.post("/rollback/{snapshot_id}", response_model=LabelingConfig)
def rollback_config(snapshot_id: int, db: DbSession) -> LabelingConfig:
    try:
        return rollback_to_snapshot(db, snapshot_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/snapshots")
def snapshots(db: DbSession) -> list[dict]:
    rows = list_config_snapshots(db)
    return [{"id": r.id, "reason": r.reason, "created_at": r.created_at} for r in rows]


@router.get("/snapshots/{snapshot_id}")
def snapshot_detail(snapshot_id: int, db: DbSession) -> dict:
    row = get_config_snapshot(db, snapshot_id)
    if row is None:
        raise HTTPException(status_code=404, detail="snapshot not found")
    return {"id": row.id, "reason": row.reason, "created_at": row.created_at, "config_json": row.config_json}
