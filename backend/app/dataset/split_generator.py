"""train / val / test 분할 — LabelingConfig.dataset.split_ratio 기준."""

from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path

from backend.app.core.config_schema import SplitRatio

# 같은 원본이 train/val/test에 서로 겹치지 않게 묶어 나누려면 원본 종류 수가 적어도 3개 이상이어야 하는 경우가 많음 (빈 split 방지 포함)
DEFAULT_MIN_SOURCES_FOR_GROUP_SPLIT = 3


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


def assign_splits_by_source(
    tile_metas: list[dict],
    split_ratio: SplitRatio,
    *,
    seed: int | None = None,
) -> dict:
    """원본 단위 그룹(`source_image_id`)으로 분할. 같은 원본의 타일은 단일 split에만 속한다.

    tile_metas 항목은 최소한 `tile_id`, `source_image_id` 포함.

    Returns:
        train / val / test tile id 리스트, source_image_id 목록,
        그리고 source_groups: { "<source_image_id>": {"source_image_name": str|None, "tiles": [...]} }
    """
    groups: dict[str, list[tuple[str, str | None]]] = defaultdict(list)
    for meta in tile_metas:
        tid = meta["tile_id"]
        sid = meta.get("source_image_id")
        if not sid:
            sid = "unknown"
        nm = meta.get("source_image_name")
        groups[sid].append((tid, nm))

    # source_groups 빌드: 타일 목록과 대표 이름(첫 non-null)
    source_groups_flat: dict[str, dict[str, object]] = {}
    for sid, tuples in groups.items():
        tiles_sorted = sorted({t for t, _ in tuples})
        name: str | None = None
        for _, nm in tuples:
            if nm:
                name = nm
                break
        source_groups_flat[sid] = {
            "source_image_name": name,
            "tiles": tiles_sorted,
        }

    group_ids = sorted(groups.keys(), key=lambda x: (x == "unknown", x))
    rng = random.Random(seed)
    rng.shuffle(group_ids)

    n = len(group_ids)
    if n == 0:
        return {
            "strategy": "group_by_source_image",
            "train": [],
            "val": [],
            "test": [],
            "source_groups": {},
            "train_source_ids": [],
            "val_source_ids": [],
            "test_source_ids": [],
        }

    n_train = max(1, int(n * split_ratio.train))
    n_val = int(n * split_ratio.val)
    n_test = n - n_train - n_val
    if n_test < 0:
        n_val += n_test
        n_test = 0
    if n_val < 0:
        n_val = 0
        n_test = n - n_train

    train_ids_g = group_ids[:n_train]
    val_ids_g = group_ids[n_train : n_train + n_val]
    test_ids_g = group_ids[n_train + n_val :]

    def flatten(gids: list[str]) -> list[str]:
        tiles: list[str] = []
        for g in gids:
            tiles.extend(sorted({t for t, _ in groups[g]}))
        return tiles

    return {
        "strategy": "group_by_source_image",
        "train": flatten(train_ids_g),
        "val": flatten(val_ids_g),
        "test": flatten(test_ids_g),
        "source_groups": source_groups_flat,
        "train_source_ids": train_ids_g,
        "val_source_ids": val_ids_g,
        "test_source_ids": test_ids_g,
    }


def write_split_files(
    export_dir: Path,
    splits: dict,
    *,
    strategy: str = "random",
    source_groups_nested: dict | None = None,
) -> None:
    """train/val/test JSON 과 source_groups.json 기록."""
    split_dir = export_dir / "splits"
    split_dir.mkdir(parents=True, exist_ok=True)

    for name in ("train", "val", "test"):
        payload: dict = {
            "split_strategy": strategy,
            "items": splits[name],
        }
        src_key = f"{name}_source_ids"
        if strategy == "group_by_source_image" and src_key in splits:
            payload["source_image_ids"] = splits[src_key]

        path = split_dir / f"{name}.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    sg = (
        source_groups_nested
        if source_groups_nested is not None
        else splits.get("source_groups")
    )
    if sg:
        (split_dir / "source_groups.json").write_text(
            json.dumps(sg, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
