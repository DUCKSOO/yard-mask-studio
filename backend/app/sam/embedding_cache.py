"""SAM2 image embedding LRU — 타일 키별로 set_image 결과를 재사용."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any


def snapshot_predictor_embedding(predictor: Any) -> dict[str, Any]:
    """SAM2ImagePredictor._features / _orig_hw 스냅샷 (텐서는 clone)."""
    feats = predictor._features
    if feats is None:
        raise RuntimeError("predictor has no features to snapshot")
    return {
        "features": {
            "image_embed": feats["image_embed"].clone(),
            "high_res_feats": [t.clone() for t in feats["high_res_feats"]],
        },
        "orig_hw": list(predictor._orig_hw),
    }


def restore_predictor_embedding(predictor: Any, snap: dict[str, Any]) -> None:
    """스냅샷을 predictor에 복원 (predict가 in-place로 바꿔도 캐시 원본은 유지)."""
    feats = snap["features"]
    predictor._features = {
        "image_embed": feats["image_embed"].clone(),
        "high_res_feats": [t.clone() for t in feats["high_res_feats"]],
    }
    predictor._orig_hw = list(snap["orig_hw"])
    predictor._is_image_set = True
    predictor._is_batch = False


class TileEmbeddingLRU:
    """타일 embedding_cache_key → SAM2 feature 스냅샷, 최대 max_entries개."""

    def __init__(self, max_entries: int) -> None:
        self._max_entries = max(1, int(max_entries))
        self._entries: OrderedDict[str, dict[str, Any]] = OrderedDict()

    @property
    def max_entries(self) -> int:
        return self._max_entries

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, key: str) -> dict[str, Any] | None:
        if key not in self._entries:
            return None
        self._entries.move_to_end(key)
        return self._entries[key]

    def put(self, key: str, snap: dict[str, Any]) -> None:
        if key in self._entries:
            del self._entries[key]
        self._entries[key] = snap
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def clear(self) -> None:
        self._entries.clear()
