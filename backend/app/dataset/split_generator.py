"""train / val / test 분할 — LabelingConfig.dataset.split_ratio 기준."""

from __future__ import annotations

import json
import random
from pathlib import Path

from backend.app.core.config_schema import SplitRatio


def assign_splits(
    tile_ids: list[str],
    split_ratio: SplitRatio,
    *,
    seed: int | None = None,
) -> dict[str, list[str]]:
    """타일 ID 목록을 섞은 뒤 비율에 따라 train/val/test 리스트로 나눈다."""
    ids = list(tile_ids)
    rng = random.Random(seed)
    rng.shuffle(ids)
    n = len(ids)
    if n == 0:
        return {"train": [], "val": [], "test": []}

    n_train = int(n * split_ratio.train)
    n_val = int(n * split_ratio.val)
    n_test = n - n_train - n_val
    if n > 0:
        if n_train == 0:
            n_train = 1
            n_test = n - n_train - n_val
        if n_test < 0:
            n_val += n_test
            n_test = 0
        if n_val < 0:
            n_val = 0
            n_test = n - n_train

    train = ids[:n_train]
    val = ids[n_train : n_train + n_val]
    test = ids[n_train + n_val :]
    return {"train": train, "val": val, "test": test}


def write_split_files(export_dir: Path, splits: dict[str, list[str]]) -> None:
    """`splits/train.json` 등 — 각 파일은 타일 ID 문자열 배열."""
    split_dir = export_dir / "splits"
    split_dir.mkdir(parents=True, exist_ok=True)
    for name in ("train", "val", "test"):
        path = split_dir / f"{name}.json"
        path.write_text(json.dumps(splits[name], indent=2), encoding="utf-8")
