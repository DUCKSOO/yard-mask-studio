"""export 디렉터리 무결성 검증."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image


def validate_export(export_dir: Path) -> list[str]:
    """문제가 있으면 사람이 읽을 수 있는 메시지 문자열 리스트를 반환. 비어 있으면 통과."""
    errors: list[str] = []
    manifest = export_dir / "dataset_manifest.json"
    if not manifest.is_file():
        errors.append("missing dataset_manifest.json")

    images_dir = export_dir / "images"
    masks_dir = export_dir / "masks"
    if not images_dir.is_dir():
        errors.append("missing images/ directory")
    if not masks_dir.is_dir():
        errors.append("missing masks/ directory")

    img_stems = {p.stem for p in images_dir.glob("*.png")} if images_dir.is_dir() else set()
    mask_stems = {p.stem for p in masks_dir.glob("*.png")} if masks_dir.is_dir() else set()
    only_img = img_stems - mask_stems
    only_mask = mask_stems - img_stems
    if only_img:
        errors.append(f"images without matching mask: {sorted(only_img)[:5]!r}...")
    if only_mask:
        errors.append(f"masks without matching image: {sorted(only_mask)[:5]!r}...")

    common = sorted(img_stems & mask_stems)
    for stem in common:
        ip = images_dir / f"{stem}.png"
        mp = masks_dir / f"{stem}.png"
        try:
            im_i = Image.open(ip)
            im_m = Image.open(mp)
            if im_m.mode != "L":
                errors.append(f"mask {stem}.png must be mode L, got {im_m.mode}")
            w_i, h_i = im_i.size
            w_m, h_m = im_m.size
            if (w_i, h_i) != (w_m, h_m):
                errors.append(f"size mismatch {stem}: image {w_i}x{h_i} vs mask {w_m}x{h_m}")
        except OSError as e:
            errors.append(f"failed to open {stem}: {e}")

    for split_name in ("train", "val", "test"):
        sp = export_dir / "splits" / f"{split_name}.json"
        if not sp.is_file():
            errors.append(f"missing splits/{split_name}.json")
            continue
        try:
            data = json.loads(sp.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"invalid JSON splits/{split_name}.json: {e}")
            continue
        if not isinstance(data, list):
            errors.append(f"splits/{split_name}.json must be a JSON array")
            continue
        for tid in data:
            if not isinstance(tid, str):
                errors.append(f"splits/{split_name}.json entries must be strings")
                break
            if tid not in common:
                errors.append(f"split lists tile_id not in image/mask intersection: {tid!r}")

    return errors
