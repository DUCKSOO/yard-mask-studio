"""그리드 픽셀 크기 — GridConfig.to_pixels 단일 소스."""

from __future__ import annotations

from backend.app.core.config_schema import GridConfig


def grid_size_pixels(grid: GridConfig, gsd_x_cm: float, gsd_y_cm: float) -> tuple[int, int]:
    return grid.to_pixels(gsd_x_cm, gsd_y_cm)
