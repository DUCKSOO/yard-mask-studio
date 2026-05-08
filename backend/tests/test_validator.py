"""export validator 단위 테스트."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from backend.app.dataset.validator import validate_export


def _write_pair(base: Path, name: str, h: int, w: int, mask_val: int = 1) -> None:
    (base / "images").mkdir(parents=True, exist_ok=True)
    (base / "masks").mkdir(parents=True, exist_ok=True)
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    Image.fromarray(rgb, mode="RGB").save(base / "images" / f"{name}.png")
    m = np.full((h, w), mask_val, dtype=np.uint8)
    Image.fromarray(m, mode="L").save(base / "masks" / f"{name}.png")


def test_validate_export_ok(tmp_path: Path) -> None:
    root = tmp_path / "ex"
    _write_pair(root, "tile_a", 8, 8)
    (root / "dataset_manifest.json").write_text(json.dumps({"sample_count": 1}), encoding="utf-8")
    (root / "splits").mkdir()
    (root / "splits" / "train.json").write_text(json.dumps(["tile_a"]), encoding="utf-8")
    (root / "splits" / "val.json").write_text(json.dumps([]), encoding="utf-8")
    (root / "splits" / "test.json").write_text(json.dumps([]), encoding="utf-8")
    assert validate_export(root) == []


def test_validate_export_size_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "ex"
    _write_pair(root, "tile_a", 8, 8)
    # overwrite mask with wrong size
    m = np.zeros((4, 4), dtype=np.uint8)
    Image.fromarray(m, mode="L").save(root / "masks" / "tile_a.png")
    (root / "dataset_manifest.json").write_text("{}", encoding="utf-8")
    (root / "splits").mkdir()
    for s in ("train", "val", "test"):
        (root / "splits" / f"{s}.json").write_text(json.dumps(["tile_a"] if s == "train" else []))
    errs = validate_export(root)
    assert any("size mismatch" in e for e in errs)
