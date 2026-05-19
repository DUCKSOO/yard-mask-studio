"""SAM predictor mock."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
import torch

from backend.app.sam.prompt_handler import PointPrompt, parse_prompts
from backend.app.sam.sam_predictor import (
    LazySam2Predictor,
    SamUnavailableError,
    StubSegmentationBackend,
    build_tile_embedding_cache_key,
)


def test_stub_predict() -> None:
    b = StubSegmentationBackend()
    im = np.zeros((64, 64, 3), dtype=np.uint8)
    masks = b.predict(im, [])
    assert len(masks) >= 1


def test_lazy_sam_missing_checkpoint() -> None:
    p = LazySam2Predictor(None, None)
    with pytest.raises(SamUnavailableError):
        p.predict(np.zeros((8, 8, 3), dtype=np.uint8), [])


def test_parse_prompts_clamp() -> None:
    pts = parse_prompts([{"type": "point", "x": -5, "y": 999, "label": "positive"}], 10, 10)
    assert pts[0].x == 0
    assert pts[0].y == 9


def test_build_tile_embedding_cache_key_changes_with_mtime(tmp_path: Path) -> None:
    img = tmp_path / "tile.png"
    img.write_bytes(b"a")
    k1 = build_tile_embedding_cache_key("t", "d", "tile_0", img)
    img.write_bytes(b"ab")
    k2 = build_tile_embedding_cache_key("t", "d", "tile_0", img)
    assert k1 != k2


def test_lazy_sam_embedding_cache_skips_set_image(tmp_path: Path) -> None:
    ckpt = tmp_path / "fake.pt"
    ckpt.write_bytes(b"x")
    lazy = LazySam2Predictor(str(ckpt), "sam2.1_hiera_tiny", embedding_cache_max=4)
    mock_pred = MagicMock()
    masks = np.zeros((3, 16, 16), dtype=bool)
    mock_pred.predict.return_value = (masks, np.array([0.9, 0.8, 0.7]), None)

    def _fake_set_image(image: np.ndarray) -> None:
        mock_pred._features = {  # noqa: SLF001
            "image_embed": torch.zeros(1, 4, 4, 4),
            "high_res_feats": [torch.zeros(1, 4, 2, 2)],
        }
        mock_pred._orig_hw = [image.shape[:2]]  # noqa: SLF001
        mock_pred._is_image_set = True  # noqa: SLF001
        mock_pred._is_batch = False  # noqa: SLF001

    mock_pred.set_image.side_effect = _fake_set_image
    lazy._predictor = mock_pred  # noqa: SLF001

    im = np.zeros((16, 16, 3), dtype=np.uint8)
    prompts = [PointPrompt(x=4, y=4, label="positive")]
    key_a = "tenant/ds/tile_a:123:456"
    key_b = "tenant/ds/tile_b:123:456"

    lazy.predict(im, prompts, embedding_cache_key=key_a)
    lazy.predict(im, prompts, embedding_cache_key=key_a)
    lazy.predict(im, prompts, embedding_cache_key=key_b)
    lazy.predict(im, prompts, embedding_cache_key=key_b)

    assert mock_pred.set_image.call_count == 2
    assert mock_pred.predict.call_count == 4


def test_lazy_sam_lru_evicts_third_tile(tmp_path: Path) -> None:
    ckpt = tmp_path / "fake.pt"
    ckpt.write_bytes(b"x")
    lazy = LazySam2Predictor(str(ckpt), "sam2.1_hiera_tiny", embedding_cache_max=2)
    mock_pred = MagicMock()
    masks = np.zeros((3, 8, 8), dtype=bool)
    mock_pred.predict.return_value = (masks, np.array([0.9, 0.8, 0.7]), None)

    def _fake_set_image(image: np.ndarray) -> None:
        mock_pred._features = {  # noqa: SLF001
            "image_embed": torch.zeros(1, 2, 2, 2),
            "high_res_feats": [],
        }
        mock_pred._orig_hw = [image.shape[:2]]  # noqa: SLF001
        mock_pred._is_image_set = True  # noqa: SLF001
        mock_pred._is_batch = False  # noqa: SLF001

    mock_pred.set_image.side_effect = _fake_set_image
    lazy._predictor = mock_pred  # noqa: SLF001

    im = np.zeros((8, 8, 3), dtype=np.uint8)
    prompts = [PointPrompt(x=1, y=1, label="positive")]

    for key in ("k1", "k2", "k3", "k1"):
        lazy.predict(im, prompts, embedding_cache_key=key)

    # k1, k2 set_image; k3 evicts k1 → set_image; k1 miss again → 4 set_image total
    assert mock_pred.set_image.call_count == 4
