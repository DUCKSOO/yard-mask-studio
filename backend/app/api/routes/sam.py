"""SAM predict API."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from fastapi import APIRouter, HTTPException, Request
from PIL import Image

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


def _tenant(request: Request, tenant_id: str) -> None:
    try:
        assert_tenant_allowed(tenant_id, request.app.state.settings.default_tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


@router.post("/predict")
def sam_predict(
    tenant_id: str,
    dataset_id: str,
    tile_id: str,
    body: SamPredictRequest,
    request: Request,
    db: DbSession,
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
    try:
        masks = backend.predict(arr, prompts)
    except SamUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    return {
        "tile_id": tile_id,
        "candidates": len(masks),
        "mask_shape": list(masks[0].shape) if masks else [],
    }
