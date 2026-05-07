"""입력 래스터 추상화 — 1차 GeoTIFF (rasterio)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import numpy as np
import rasterio
from rasterio.windows import Window


@runtime_checkable
class RasterSource(Protocol):
    @property
    def width(self) -> int: ...
    @property
    def height(self) -> int: ...
    @property
    def count(self) -> int: ...
    @property
    def crs(self) -> Any: ...
    @property
    def transform(self) -> Any: ...
    def nodata_for_band(self, band_idx: int) -> float | None: ...

    def read_window(self, row_off: int, col_off: int, win_h: int, win_w: int) -> np.ndarray:
        """Shape (bands, win_h, win_w), float or original dtype."""
        ...


class GeoTiffRasterSource:
    def __init__(self, path: Path):
        self._path = path
        self._ds = rasterio.open(path)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def width(self) -> int:
        return int(self._ds.width)

    @property
    def height(self) -> int:
        return int(self._ds.height)

    @property
    def count(self) -> int:
        return int(self._ds.count)

    @property
    def crs(self):
        return self._ds.crs

    @property
    def transform(self):
        return self._ds.transform

    def nodata_for_band(self, band_idx: int) -> float | None:
        if band_idx < 1 or band_idx > self.count:
            return None
        vals = getattr(self._ds, "nodatavals", None)
        if vals is None or band_idx - 1 >= len(vals):
            return None
        return vals[band_idx - 1]

    def read_window(self, row_off: int, col_off: int, win_h: int, win_w: int) -> np.ndarray:
        window = Window(col_off, row_off, win_w, win_h)
        return self._ds.read(window=window)

    def close(self) -> None:
        self._ds.close()

    def __enter__(self) -> GeoTiffRasterSource:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
