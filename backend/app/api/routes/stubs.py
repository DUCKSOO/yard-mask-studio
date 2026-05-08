"""향후 Step 6+ 스텁 전용 라우터(현재 등록된 엔드포인트 없음)."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["stubs"])
