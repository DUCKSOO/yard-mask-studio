"""grid_calculator."""

from __future__ import annotations

from backend.app.core.config_schema import GridConfig
from backend.app.grid.grid_calculator import grid_size_pixels


def test_grid_15m_at_2cm() -> None:
    g = GridConfig(size_meters=15.0, origin="source_image_top_left")
    assert grid_size_pixels(g, 2.0, 2.0) == (750, 750)
