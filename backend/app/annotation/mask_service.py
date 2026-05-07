"""class index mask PNG 및 value:length RLE (Fortran-order 평탄화)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


def save_mask_png(path: Path, mask: np.ndarray) -> None:
    """mask: uint8 HxW, values 0-255."""
    if mask.dtype != np.uint8:
        mask = mask.astype(np.uint8)
    if mask.ndim != 2:
        raise ValueError("mask must be 2D")
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(mask, mode="L").save(path)


def load_mask_png(path: Path) -> np.ndarray:
    img = Image.open(path)
    if img.mode != "L":
        img = img.convert("L")
    return np.array(img, dtype=np.uint8)


def encode_rle_vl(mask: np.ndarray) -> str:
    """행 우선(C-order) 평탄화 후 value:run_len 인코딩."""
    if mask.ndim != 2:
        raise ValueError("mask must be 2D")
    flat = mask.flatten(order="C")
    if flat.size == 0:
        return "0:0"
    v0 = int(flat[0])
    c = 1
    parts: list[str] = []
    for x in flat[1:]:
        if int(x) == v0:
            c += 1
        else:
            parts.append(f"{v0}:{c}")
            v0 = int(x)
            c = 1
    parts.append(f"{v0}:{c}")
    return ",".join(parts)


def decode_rle_vl(counts: str, height: int, width: int) -> np.ndarray:
    total = height * width
    flat_list: list[int] = []
    for seg in counts.split(","):
        seg = seg.strip()
        if not seg:
            continue
        v_str, ln_str = seg.split(":", 1)
        v, ln = int(v_str), int(ln_str)
        flat_list.extend([v] * ln)
    if len(flat_list) != total:
        raise ValueError(f"RLE total {len(flat_list)} != {total}")
    flat = np.array(flat_list, dtype=np.uint8)
    return flat.reshape((height, width), order="C")
