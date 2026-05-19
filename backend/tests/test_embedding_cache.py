"""SAM embedding LRU."""

from __future__ import annotations

from backend.app.sam.embedding_cache import TileEmbeddingLRU


def test_lru_get_moves_to_end() -> None:
    lru = TileEmbeddingLRU(2)
    lru.put("a", {"v": 1})
    lru.put("b", {"v": 2})
    assert lru.get("a") == {"v": 1}
    lru.put("c", {"v": 3})
    assert lru.get("a") == {"v": 1}
    assert lru.get("b") is None


def test_lru_max_entries() -> None:
    lru = TileEmbeddingLRU(2)
    lru.put("k1", {})
    lru.put("k2", {})
    lru.put("k3", {})
    assert len(lru) == 2
    assert lru.get("k1") is None
    assert lru.get("k2") is not None
    assert lru.get("k3") is not None
