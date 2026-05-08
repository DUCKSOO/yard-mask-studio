"""split_generator 단위 테스트."""

from __future__ import annotations

from backend.app.core.config_schema import SplitRatio
from backend.app.dataset.split_generator import assign_splits


def test_assign_splits_counts_and_sum() -> None:
    sr = SplitRatio(train=0.7, val=0.15, test=0.15)
    tiles = [f"t{i:03d}" for i in range(10)]
    out = assign_splits(tiles, sr, seed=0)
    assert len(out["train"]) + len(out["val"]) + len(out["test"]) == 10
    assert set(out["train"]) | set(out["val"]) | set(out["test"]) == set(tiles)
    assert not (set(out["train"]) & set(out["val"]))
    assert len(out["train"]) >= 1


def test_assign_splits_single_tile_goes_train() -> None:
    sr = SplitRatio(train=0.7, val=0.15, test=0.15)
    out = assign_splits(["only_one"], sr, seed=0)
    assert out["train"] == ["only_one"]
    assert out["val"] == []
    assert out["test"] == []
