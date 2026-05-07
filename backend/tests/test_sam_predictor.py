"""SAM predictor mock."""

from __future__ import annotations

import numpy as np
import pytest

from backend.app.sam.prompt_handler import parse_prompts
from backend.app.sam.sam_predictor import LazySam2Predictor, SamUnavailableError, StubSegmentationBackend


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
