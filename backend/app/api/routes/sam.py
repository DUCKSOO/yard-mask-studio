"""SAM predict API."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import numpy as np
from fastapi import APIRouter, Body, HTTPException, Request
from PIL import Image

from backend.app.api.route_params import DatasetId, TenantId, TileId
from backend.app.api.schemas import SamPredictRequest
from backend.app.core.tenant import assert_tenant_allowed
from backend.app.deps import DbSession
from backend.app.sam import prompt_handler
from backend.app.sam.sam_predictor import SamUnavailableError, SegmentationBackend
from backend.app.services import dataset_service
from backend.app.tiling import tile_index

router = APIRouter(
    prefix="/tenants/{tenant_id}/datasets/{dataset_id}/tiles/{tile_id}/sam",
    tags=["sam"],
)
logger = logging.getLogger(__name__)


def _tenant(request: Request, tenant_id: str) -> None:
    try:
        assert_tenant_allowed(tenant_id, request.app.state.settings.default_tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


@router.post(
    "/predict",
    summary="SAM 세그멘테이션 예측",
    description="""
타일 PNG와 프롬프트(점/박스)를 받아 세그멘테이션 백엔드를 호출합니다.

- **현재 응답**은 후보 개수·첫 마스크 shape 위주이며, 픽셀 마스크 배열은 본문에 포함하지 않을 수 있습니다.
- 체크포인트 미설정·미구현 시 **503** (`SamUnavailableError`).
""",
)
def sam_predict(
    tenant_id: TenantId,
    dataset_id: DatasetId,
    tile_id: TileId,
    request: Request,
    db: DbSession,
    body: SamPredictRequest = Body(
        ...,
        description="프롬프트 목록 및 선택적 multimask_output.",
    ),
) -> dict:
    _tenant(request, tenant_id)
    if tile_index.get_tile(db, tenant_id, dataset_id, tile_id) is None:
        raise HTTPException(status_code=404, detail="tile not found")
    repo_root: Path = request.app.state.repo_root
    img_path = dataset_service.dataset_dir(repo_root, tenant_id, dataset_id) / "images" / f"{tile_id}.png"
    if not img_path.is_file():
        raise HTTPException(status_code=404, detail="tile image missing")
    im = Image.open(img_path).convert("RGB")
    arr = np.array(im, dtype=np.uint8)
    h, w = arr.shape[:2]
    try:
        prompts = prompt_handler.parse_prompts(body.prompts, w, h)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    backend: SegmentationBackend = request.app.state.sam_predictor
    logger.info(
        "sam/predict tenant=%s dataset_id=%s tile_id=%s prompts=%s",
        tenant_id,
        dataset_id,
        tile_id,
        len(body.prompts),
    )
    t0 = time.perf_counter()
    try:
        masks = backend.predict(arr, prompts)
    except SamUnavailableError as e:
        logger.warning("sam/predict unavailable tenant=%s tile_id=%s: %s", tenant_id, tile_id, e)
        raise HTTPException(status_code=503, detail=str(e)) from e
    elapsed_ms = (time.perf_counter() - t0) * 1000
    logger.info(
        "sam/predict done tenant=%s tile_id=%s candidates=%s elapsed_ms=%.1f",
        tenant_id,
        tile_id,
        len(masks),
        elapsed_ms,
    )
    return {
        "tile_id": tile_id,
        "candidates": len(masks),
        "mask_shape": list(masks[0].shape) if masks else [],
    }
