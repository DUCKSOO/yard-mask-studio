"""tile_generator — 소형 GeoTIFF."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_origin

from backend.app.core.config_schema import TilingConfig
from backend.app.tiling.raster_source import GeoTiffRasterSource
from backend.app.tiling.tile_generator import iter_tile_windows


def _write_test_geotiff(path: Path, h: int, w: int) -> None:
    data = np.zeros((3, h, w), dtype=np.uint8)
    transform = from_origin(0, 1_000_000, 0.02, -0.02)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=h,
        width=w,
        count=3,
        dtype="uint8",
        crs=CRS.from_epsg(5186),
        transform=transform,
    ) as dst:
        dst.write(data)


def test_tile_windows_counts(tmp_path: Path) -> None:
    path = tmp_path / "x.tif"
    _write_test_geotiff(path, 300, 250)
    tiling = TilingConfig(
        tile_size=128,
        tile_overlap=32,
        nodata_skip_threshold=0.8,
        edge_padding_strategy="zero",
    )
    with GeoTiffRasterSource(path) as src:
        wins = list(iter_tile_windows(src, tiling))
    stride = 96
    exp_rows = (300 + stride - 1) // stride
    exp_cols = (250 + stride - 1) // stride
    assert len(wins) == exp_rows * exp_cols
    for w in wins:
        assert w.data.shape == (3, 128, 128)


@pytest.mark.parametrize("tile_size", [512, 1024, 2048])
def test_tile_size_padding_drop(tmp_path: Path, tile_size: int) -> None:
    path = tmp_path / f"s{tile_size}.tif"
    h, w = tile_size + 50, tile_size + 40
    _write_test_geotiff(path, h, w)
    tiling = TilingConfig(
        tile_size=tile_size,
        tile_overlap=0,
        nodata_skip_threshold=0.8,
        edge_padding_strategy="zero",
    )
    with GeoTiffRasterSource(path) as src:
        wins = list(iter_tile_windows(src, tiling))
    assert all(w.data.shape[1] == tile_size and w.data.shape[2] == tile_size for w in wins)
