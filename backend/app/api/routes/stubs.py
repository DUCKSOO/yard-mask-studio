"""Step 5~6 미구현 엔드포인트 스텁 (501)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.api.route_params import DatasetId, ExportId, TenantId, TileId

router = APIRouter(tags=["stubs"])


@router.get(
    "/tenants/{tenant_id}/review/queue",
    summary="검수 큐 (미구현)",
    description="Step 6 예정. **501**.",
)
def review_queue_stub(tenant_id: TenantId) -> None:
    raise HTTPException(status_code=501, detail="Step 6: review queue not implemented")


@router.post(
    "/tenants/{tenant_id}/datasets/{dataset_id}/tiles/{tile_id}/review/approve",
    summary="검수 승인 (미구현)",
    description="Step 6 예정. **501**.",
)
def review_approve_stub(
    tenant_id: TenantId,
    dataset_id: DatasetId,
    tile_id: TileId,
) -> None:
    raise HTTPException(status_code=501, detail="Step 6: review not implemented")


@router.post(
    "/tenants/{tenant_id}/datasets/{dataset_id}/tiles/{tile_id}/review/reject",
    summary="검수 거부 (미구현)",
    description="Step 6 예정. **501**.",
)
def review_reject_stub(
    tenant_id: TenantId,
    dataset_id: DatasetId,
    tile_id: TileId,
) -> None:
    raise HTTPException(status_code=501, detail="Step 6: review not implemented")


@router.get(
    "/tenants/{tenant_id}/exports/{export_id}/status",
    summary="export 상태 (미구현)",
    description="Step 5 예정. **501**.",
)
def export_status_stub(
    tenant_id: TenantId,
    export_id: ExportId,
) -> None:
    raise HTTPException(status_code=501, detail="Step 5: export status not implemented")


@router.get(
    "/tenants/{tenant_id}/exports/{export_id}/download",
    summary="export 다운로드 (미구현)",
    description="Step 5 예정. **501**.",
)
def export_download_stub(
    tenant_id: TenantId,
    export_id: ExportId,
) -> None:
    raise HTTPException(status_code=501, detail="Step 5: export download not implemented")
