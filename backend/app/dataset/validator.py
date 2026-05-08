"""export 디렉터리 무결성 검증."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image


def _read_split_items(data: object) -> list[str] | None:
    """split JSON 에서 tile_id 배열을 추출한다.
    구 포맷: ["tile_id", ...]
    신 포맷: {"split_strategy": "...", "items": ["tile_id", ...]}
    반환값이 None이면 포맷 자체가 잘못된 것.
    """
    if isinstance(data, list):
        return data  # 구 포맷
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return data["items"]  # 신 포맷
    return None


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
            raw = json.loads(sp.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"invalid JSON splits/{split_name}.json: {e}")
            continue
        items = _read_split_items(raw)
        if items is None:
            errors.append(
                f"splits/{split_name}.json must be a JSON array or "
                f'an object with an "items" array'
            )
            continue
        for tid in items:
            if not isinstance(tid, str):
                errors.append(f"splits/{split_name}.json items must be strings")
                break
            if tid not in common:
                errors.append(f"split lists tile_id not in image/mask intersection: {tid!r}")

    return errors


def build_validation_report(export_dir: Path) -> dict:
    """학습 전 점검용 요약 (export 성공 여부와 무관하게 생성 가능)."""
    images_dir = export_dir / "images"
    masks_dir = export_dir / "masks"

    img_paths = list(images_dir.glob("*.png")) if images_dir.is_dir() else []
    mask_paths_list = list(masks_dir.glob("*.png")) if masks_dir.is_dir() else []
    img_stems = {p.stem for p in img_paths}
    mask_stems = {p.stem for p in mask_paths_list}

    missing_masks = sorted(img_stems - mask_stems)
    missing_images = sorted(mask_stems - img_stems)
    common = sorted(img_stems & mask_stems)

    invalid_mask_values: list[str] = []
    invalid_image_modes: list[str] = []
    invalid_mask_modes: list[str] = []

    for stem in common:
        try:
            ip = images_dir / f"{stem}.png"
            mp = masks_dir / f"{stem}.png"
            im_i = Image.open(ip)
            im_m = Image.open(mp)
            if im_i.mode != "RGB":
                invalid_image_modes.append(f"{stem}.png:{im_i.mode}")
            if im_m.mode != "L":
                invalid_mask_modes.append(f"{stem}.png:{im_m.mode}")
            else:
                arr = np.array(im_m)
                u = np.unique(arr)
                if not np.all(np.isin(u, [0, 255])):
                    invalid_mask_values.append(f"{stem}.png:{u.tolist()[:10]!s}")
            im_i.close()
            im_m.close()
        except OSError:
            continue

    # split 중복 검사 + tile → source 매핑 (있을 때)
    split_tiles: dict[str, list[str]] = {}
    for split_name in ("train", "val", "test"):
        sp = export_dir / "splits" / f"{split_name}.json"
        if sp.is_file():
            try:
                raw = json.loads(sp.read_text(encoding="utf-8"))
                split_tiles[split_name] = _read_split_items(raw) or []
            except (json.JSONDecodeError, TypeError):
                split_tiles[split_name] = []
        else:
            split_tiles[split_name] = []

    assigned: dict[str, str] = {}
    split_duplicates: list[str] = []
    for split_name in ("train", "val", "test"):
        for tid in split_tiles.get(split_name, []):
            if tid in assigned and assigned[tid] != split_name:
                dup = f"{tid!r}:{assigned[tid]}+{split_name}"
                if dup not in split_duplicates:
                    split_duplicates.append(dup)
            assigned[tid] = split_name

    # manifest에서 split 신뢰도
    same_source_can_span_splits = False
    actual_strategy = ""
    manifest_path = export_dir / "dataset_manifest.json"
    if manifest_path.is_file():
        try:
            m = json.loads(manifest_path.read_text(encoding="utf-8"))
            actual_strategy = str(m.get("actual_split_strategy", ""))
            same_source_can_span_splits = bool(
                m.get("same_source_may_span_train_val_test", False)
            )
        except (json.JSONDecodeError, OSError):
            pass

    tm_path = export_dir / "tiles_manifest.json"
    tile_to_src: dict[str, str | None] = {}
    if tm_path.is_file():
        try:
            tl = json.loads(tm_path.read_text(encoding="utf-8"))
            if isinstance(tl, list):
                for row in tl:
                    if isinstance(row, dict) and "tile_id" in row:
                        tile_to_src[row["tile_id"]] = row.get("source_image_id")
        except (json.JSONDecodeError, TypeError):
            pass

    # 동일 source_image_id가 여러 split에 분산되었는지
    source_to_splits: defaultdict[str, set[str]] = defaultdict(set)
    for split_name in ("train", "val", "test"):
        for tid in split_tiles.get(split_name, []):
            sid = tile_to_src.get(tid)
            if sid is None:
                sid = "unknown"
            source_to_splits[sid].add(split_name)

    source_ids_spanning = sorted(
        sid for sid, sts in source_to_splits.items() if len(sts) > 1 and sid != "unknown"
    )
    # group_by_source_image 적용 시 같은 원본은 한 split에만 있어야 함
    split_leakage_by_source_detected = bool(
        actual_strategy == "group_by_source_image" and source_ids_spanning
    )

    train_ids = split_tiles.get("train") or []

    train_foreground_ratios_list: list[float] | None = None
    if tm_path.is_file() and train_ids:
        try:
            tl = json.loads(tm_path.read_text(encoding="utf-8"))
            if isinstance(tl, list):
                tile_to_fg = {}
                for row in tl:
                    if isinstance(row, dict) and "tile_id" in row:
                        tile_to_fg[row["tile_id"]] = row.get("foreground_ratio", 0.0)
                train_foreground_ratios_list = [
                    float(tile_to_fg.get(t, 0.0)) for t in train_ids if t in tile_to_fg
                ]
        except (json.JSONDecodeError, TypeError, ValueError):
            train_foreground_ratios_list = None

    return {
        "image_count": len(img_paths),
        "mask_count": len(mask_paths_list),
        "pair_count": len(common),
        "missing_masks": missing_masks,
        "missing_images": missing_images,
        "invalid_mask_values": invalid_mask_values,
        "invalid_image_modes": invalid_image_modes,
        "invalid_mask_modes": invalid_mask_modes,
        "split_duplicates": split_duplicates,
        "source_ids_spanned_across_splits": source_ids_spanning,
        "split_leakage_by_source_detected": split_leakage_by_source_detected,
        "same_source_may_span_train_val_test": same_source_can_span_splits,
        "train_tile_count": len(train_ids),
        "train_foreground_ratio_mean": (
            float(sum(train_foreground_ratios_list) / len(train_foreground_ratios_list))
            if train_foreground_ratios_list
            else None
        ),
    }
