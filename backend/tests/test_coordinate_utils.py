"""coordinate_utils 수치 검증."""

from __future__ import annotations

from rasterio.crs import CRS
from rasterio.transform import from_origin

from backend.app.tiling.coordinate_utils import gsd_cm_from_geotransform, pixels_for_meters


def test_gsd_projected_meters() -> None:
    # 0.02 m = 2 cm per pixel
    transform = from_origin(0, 1_000_000, 0.02, -0.02)
    crs = CRS.from_epsg(5186)
    gx, gy, src = gsd_cm_from_geotransform(transform, crs)
    assert src == "geotiff_transform"
    assert gx == 2.0
    assert gy == 2.0


def test_pixels_for_meters() -> None:
    assert pixels_for_meters(15.0, 2.0) == 750
