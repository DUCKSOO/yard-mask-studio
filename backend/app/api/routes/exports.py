"""Export 상태 조회 및 ZIP 다운로드."""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from backend.app.api.route_params import ExportId, TenantId
from backend.app.core.tenant import assert_tenant_allowed
from backend.app.dataset.dataset_exporter import get_export
from backend.app.deps import DbSession

router = APIRouter(tags=["exports"])
logger = logging.getLogger(__name__)


def _tenant(request: Request, tenant_id: str) -> None:
    try:
        assert_tenant_allowed(tenant_id, request.app.state.settings.default_tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


@router.get(
    "/tenants/{tenant_id}/exports/{export_id}/status",
    summary="export 상태",
    description="SQLite `exports` 테이블 기준. 없거나 테넌트가 다르면 **404**.",
)
def export_status(
    tenant_id: TenantId,
    export_id: ExportId,
    request: Request,
    db: DbSession,
) -> dict:
    _tenant(request, tenant_id)
    row = get_export(db, tenant_id, export_id)
    if row is None:
        raise HTTPException(status_code=404, detail="export not found")
    logger.debug(
        "export/status tenant=%s export_id=%s status=%s samples=%s",
        tenant_id,
        export_id,
        row.status,
        row.sample_count,
    )
    return {
        "status": row.status,
        "export_path": row.export_path,
        "sample_count": row.sample_count,
        "dataset_id": row.dataset_id,
        "tenant_id": row.tenant_id,
    }


def _split_file_len(export_dir: Path, split_name: str) -> int:
    p = export_dir / "splits" / f"{split_name}.json"
    if not p.is_file():
        return 0
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 0
    if isinstance(data, list):
        return len(data)
    return 0


@router.get(
    "/tenants/{tenant_id}/exports/{export_id}/summary",
    summary="export 결과 요약",
    description="""
`dataset_manifest.json`·`splits/*.json`을 읽어 MLOps 인계용 요약을 반환합니다.

- export가 **done**이 아니면 **409**.
- 디렉터리·manifest가 없으면 **404**.
""",
)
def export_summary(
    tenant_id: TenantId,
    export_id: ExportId,
    request: Request,
    db: DbSession,
) -> dict:
    _tenant(request, tenant_id)
    row = get_export(db, tenant_id, export_id)
    if row is None:
        raise HTTPException(status_code=404, detail="export not found")
    if row.status != "done":
        raise HTTPException(status_code=409, detail=f"export not ready: status={row.status}")

    repo_root: Path = request.app.state.repo_root.resolve()
    full = (repo_root / row.export_path).resolve()
    try:
        full.relative_to(repo_root)
    except ValueError:
        raise HTTPException(status_code=500, detail="invalid export path") from None
    if not full.is_dir():
        raise HTTPException(status_code=404, detail="export directory missing on disk")

    manifest_path = full / "dataset_manifest.json"
    if not manifest_path.is_file():
        raise HTTPException(status_code=404, detail="dataset_manifest.json missing")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"invalid dataset_manifest.json: {e}") from e

    split = {
        "train": _split_file_len(full, "train"),
        "val": _split_file_len(full, "val"),
        "test": _split_file_len(full, "test"),
    }

    logger.info(
        "export/summary tenant=%s export_id=%s dataset_id=%s sample_count=%s split=%s",
        tenant_id,
        export_id,
        row.dataset_id,
        manifest.get("sample_count", row.sample_count),
        split,
    )
    return {
        "export_id": row.id,
        "dataset_id": row.dataset_id,
        "tenant_id": row.tenant_id,
        "status": row.status,
        "sample_count": int(manifest.get("sample_count", row.sample_count)),
        "split": split,
        "tile_size": manifest.get("tile_size"),
        "expected_gsd_cm": manifest.get("expected_gsd_cm"),
        "mask_schema_version": manifest.get("mask_schema_version"),
        "created_at": manifest.get("created_at"),
        "export_path": row.export_path,
    }


@router.get(
    "/tenants/{tenant_id}/exports/{export_id}/download",
    summary="export ZIP 다운로드",
    description="export 디렉터리 전체를 임시 ZIP으로 묶어 반환. 완료된 export만 가능.",
)
def export_download(
    tenant_id: TenantId,
    export_id: ExportId,
    request: Request,
    db: DbSession,
) -> FileResponse:
    _tenant(request, tenant_id)
    row = get_export(db, tenant_id, export_id)
    if row is None:
        raise HTTPException(status_code=404, detail="export not found")
    if row.status != "done":
        raise HTTPException(status_code=409, detail=f"export not ready: status={row.status}")

    repo_root: Path = request.app.state.repo_root.resolve()
    full = (repo_root / row.export_path).resolve()
    try:
        full.relative_to(repo_root)
    except ValueError:
        raise HTTPException(status_code=500, detail="invalid export path") from None
    if not full.is_dir():
        raise HTTPException(status_code=404, detail="export directory missing on disk")

    fd, tmp_path = tempfile.mkstemp(prefix="export_dl_", suffix=".zip")
    os.close(fd)
    try:
        os.remove(tmp_path)
    except OSError:
        pass
    base = str(Path(tmp_path).with_suffix(""))
    zip_path = shutil.make_archive(base, "zip", root_dir=str(full))
    logger.info("export/download tenant=%s export_id=%s zip=%s", tenant_id, export_id, zip_path)
    cleanup = BackgroundTask(lambda p=zip_path: os.unlink(p) if os.path.isfile(p) else None)
    return FileResponse(
        zip_path,
        filename=f"{export_id}.zip",
        media_type="application/zip",
        background=cleanup,
    )
