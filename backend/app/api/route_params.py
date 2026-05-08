"""OpenAPI(Swagger)용 공통 Path 파라미터 타입."""

from __future__ import annotations

from typing import Annotated

from fastapi import Path

TenantId = Annotated[
    str,
    Path(
        description="테넌트 ID. 서버 `.env`의 `DEFAULT_TENANT_ID`와 같아야 합니다. 다르면 403 또는 422.",
        examples=["default"],
    ),
]

DatasetId = Annotated[
    str,
    Path(
        description="데이터셋 ID. `POST /api/tenants/{tenant_id}/datasets`로 등록할 때 지정한 값.",
        examples=["step3_e2e"],
    ),
]

TileId = Annotated[
    str,
    Path(
        description="타일 ID. 타일 생성 시 부여된 문자열(예: 원본 픽셀 오프셋 기반 `tile_000000_000000`).",
        examples=["tile_000000_000000"],
    ),
]

ConfigSnapshotId = Annotated[
    int,
    Path(
        description="설정 변경 스냅샷 ID. `GET /api/config/snapshots` 목록의 `id` 필드.",
        ge=1,
        examples=[1],
    ),
]

ExportId = Annotated[
    str,
    Path(
        description="Export 작업 ID(Step 5 예정).",
        examples=["export_001"],
    ),
]
