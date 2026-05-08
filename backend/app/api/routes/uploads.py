"""GeoTIFF 업로드 — `data/source/{tenant}/raw_geotiff/` 에 저장."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile

from backend.app.api.route_params import TenantId
from backend.app.core.tenant import assert_tenant_allowed
from backend.app.services import dataset_service

router = APIRouter(prefix="/tenants/{tenant_id}/uploads", tags=["uploads"])
logger = logging.getLogger(__name__)


def _tenant(request: Request, tenant_id: str) -> None:
    try:
        assert_tenant_allowed(tenant_id, request.app.state.settings.default_tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


def _safe_filename(name: str | None) -> str:
    base = Path(name or "").name
    if not base or base in (".", ".."):
        raise HTTPException(status_code=422, detail="invalid filename")
    suffix = Path(base).suffix.lower()
    if suffix not in (".tif", ".tiff"):
        raise HTTPException(status_code=422, detail="only .tif and .tiff are allowed")
    return base


@router.get(
    "/geotiff",
    summary="업로드된 GeoTIFF 목록",
    description="`data/source/{tenant_id}/raw_geotiff/` 아래의 .tif / .tiff 파일 목록.",
)
def list_geotiffs(tenant_id: TenantId, request: Request) -> list[dict]:
    _tenant(request, tenant_id)
    repo_root: Path = request.app.state.repo_root
    d = dataset_service.raw_geotiff_dir(repo_root, tenant_id)
    if not d.is_dir():
        return []
    out: list[dict] = []
    for p in sorted(d.iterdir()):
        if not p.is_file():
            continue
        suf = p.suffix.lower()
        if suf not in (".tif", ".tiff"):
            continue
        st = p.stat()
        out.append(
            {
                "filename": p.name,
                "size": st.st_size,
                "mtime": datetime.fromtimestamp(st.st_mtime, tz=UTC).isoformat(),
            }
        )
    return out


@router.post(
    "/geotiff",
    status_code=201,
    summary="GeoTIFF 업로드",
    description="multipart `file` 필드로 전송. `raw_geotiff/` 에 저장(동일 이름이면 덮어쓰기).",
)
async def upload_geotiff(
    tenant_id: TenantId,
    request: Request,
    file: UploadFile = File(..., description="GeoTIFF 파일"),
) -> dict:
    _tenant(request, tenant_id)
    safe_name = _safe_filename(file.filename)
    repo_root: Path = request.app.state.repo_root
    dest_dir = dataset_service.raw_geotiff_dir(repo_root, tenant_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / safe_name
    size = 0
    try:
        with dest.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                out.write(chunk)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"failed to write file: {e}") from e
    finally:
        await file.close()

    logger.info("geotiff uploaded tenant=%s filename=%s size=%s", tenant_id, safe_name, size)
    return {"filename": safe_name, "size": size}


@router.delete(
    "/geotiff/{filename}",
    status_code=204,
    summary="GeoTIFF 파일 삭제",
    description="`raw_geotiff/` 에서 해당 파일을 제거합니다.",
)
def delete_geotiff(tenant_id: TenantId, filename: str, request: Request) -> Response:
    _tenant(request, tenant_id)
    if "/" in filename or "\\" in filename:
        raise HTTPException(status_code=422, detail="invalid filename")
    base = Path(filename).name
    if not base or base in (".", ".."):
        raise HTTPException(status_code=422, detail="invalid filename")
    suffix = Path(base).suffix.lower()
    if suffix not in (".tif", ".tiff"):
        raise HTTPException(status_code=422, detail="only .tif and .tiff are allowed")
    repo_root: Path = request.app.state.repo_root
    path = dataset_service.raw_geotiff_path(repo_root, tenant_id, base)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    try:
        path.unlink()
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    logger.info("geotiff deleted tenant=%s filename=%s", tenant_id, base)
    return Response(status_code=204)
