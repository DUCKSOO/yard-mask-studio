"""Step 5~6 미구현 엔드포인트 스텁 (501)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["stubs"])


@router.get("/tenants/{tenant_id}/review/queue")
def review_queue_stub() -> None:
    raise HTTPException(status_code=501, detail="Step 6: review queue not implemented")


@router.post("/tenants/{tenant_id}/datasets/{dataset_id}/tiles/{tile_id}/review/approve")
def review_approve_stub() -> None:
    raise HTTPException(status_code=501, detail="Step 6: review not implemented")


@router.post("/tenants/{tenant_id}/datasets/{dataset_id}/tiles/{tile_id}/review/reject")
def review_reject_stub() -> None:
    raise HTTPException(status_code=501, detail="Step 6: review not implemented")


@router.get("/tenants/{tenant_id}/exports/{export_id}/status")
def export_status_stub() -> None:
    raise HTTPException(status_code=501, detail="Step 5: export status not implemented")


@router.get("/tenants/{tenant_id}/exports/{export_id}/download")
def export_download_stub() -> None:
    raise HTTPException(status_code=501, detail="Step 5: export download not implemented")
