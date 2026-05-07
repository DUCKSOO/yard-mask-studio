"""TilingConfig 주입형 타일 윈도우 생성 (stride, padding, drop)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from backend.app.core.config_schema import TilingConfig
from backend.app.tiling.raster_source import RasterSource


@dataclass(frozen=True)
class TileWindow:
    row_off: int
    col_off: int
    data: np.ndarray  # (bands, H, W)
    padded_to: tuple[int, int]  # (tile_h, tile_w) after padding


def _pad_tile(data: np.ndarray, target_h: int, target_w: int, strategy: str) -> np.ndarray:
    _, h, w = data.shape
    if h == target_h and w == target_w:
        return data
    pad_h = target_h - h
    pad_w = target_w - w
    if pad_h < 0 or pad_w < 0:
        raise ValueError("target smaller than data")
    if strategy == "zero":
        out = np.zeros((data.shape[0], target_h, target_w), dtype=data.dtype)
        out[:, :h, :w] = data
        return out
    if strategy == "reflect":
        bands = []
        for i in range(data.shape[0]):
            bands.append(np.pad(data[i], ((0, pad_h), (0, pad_w)), mode="reflect"))
        return np.stack(bands, axis=0)
    raise ValueError(f"unknown padding {strategy}")


def iter_tile_windows(source: RasterSource, tiling: TilingConfig):
    ts = tiling.tile_size
    stride = ts - tiling.tile_overlap
    if stride <= 0:
        raise ValueError("tile_size - tile_overlap must be positive")

    for row_off in range(0, source.height, stride):
        for col_off in range(0, source.width, stride):
            win_h = min(ts, source.height - row_off)
            win_w = min(ts, source.width - col_off)
            if win_h <= 0 or win_w <= 0:
                continue
            if tiling.edge_padding_strategy == "drop" and (win_h < ts or win_w < ts):
                continue
            data = source.read_window(row_off, col_off, win_h, win_w)
            if tiling.edge_padding_strategy in ("zero", "reflect") and (win_h < ts or win_w < ts):
                data = _pad_tile(data, ts, ts, tiling.edge_padding_strategy)
            yield TileWindow(row_off=row_off, col_off=col_off, data=data, padded_to=(ts, ts))
