"""mask_service PNG 및 RLE."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from backend.app.annotation import mask_service


def test_rle_vl_roundtrip() -> None:
    m = np.array([[0, 1, 1], [255, 255, 0]], dtype=np.uint8)
    s = mask_service.encode_rle_vl(m)
    out = mask_service.decode_rle_vl(s, m.shape[0], m.shape[1])
    np.testing.assert_array_equal(out, m)


def test_png_roundtrip(tmp_path: Path) -> None:
    m = np.arange(12, dtype=np.uint8).reshape(3, 4)
    p = tmp_path / "m.png"
    mask_service.save_mask_png(p, m)
    loaded = mask_service.load_mask_png(p)
    np.testing.assert_array_equal(loaded, m)
