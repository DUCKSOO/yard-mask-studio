"""U-Net 학습용 데이터셋 export — 라벨된 타일만 복사·분할·검증."""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import yaml
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.db import AnnotationRow, ExportRow
from backend.app.dataset.split_generator import (
    DEFAULT_MIN_SOURCES_FOR_GROUP_SPLIT,
    assign_splits,
    assign_splits_by_source,
    write_split_files,
)
from backend.app.dataset.validator import build_validation_report, validate_export
from backend.app.services import dataset_service


def export_dir_for(repo_root: Path, tenant_id: str, dataset_id: str, export_id: str) -> Path:
    return repo_root / "data" / "exports" / tenant_id / dataset_id / export_id


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def _load_tile_meta(meta_path: Path) -> dict:
    if not meta_path.is_file():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _foreground_ratio(mask_arr: np.ndarray) -> float:
    total = mask_arr.size
    if total == 0:
        return 0.0
    return float(np.count_nonzero(mask_arr)) / total


def export_unet_dataset(
    session: Session,
    repo_root: Path,
    tenant_id: str,
    dataset_id: str,
    *,
    split_seed: int | None = None,
) -> str:
    """라벨된 annotation + 디스크상 image/mask가 있는 타일만 export. export UUID를 반환."""
    repo_root = repo_root.resolve()
    dr = dataset_service.get_dataset(session, tenant_id, dataset_id)
    if dr is None:
        raise KeyError("dataset not found")

    cfg = dataset_service.get_dataset_labeling_config(session, tenant_id, dataset_id)
    ddir = dataset_service.dataset_dir(repo_root, tenant_id, dataset_id)

    stmt = select(AnnotationRow).where(
        AnnotationRow.tenant_id == tenant_id,
        AnnotationRow.dataset_id == dataset_id,
    )
    rows = list(session.scalars(stmt))

    labeled_tile_ids: list[str] = []
    for row in rows:
        try:
            payload = json.loads(row.annotation_json)
        except json.JSONDecodeError:
            continue
        if payload.get("status") != "labeled":
            continue
        tile_id = row.tile_id
        img_p = ddir / "images" / f"{tile_id}.png"
        mask_p = ddir / "masks" / f"{tile_id}.png"
        if not img_p.is_file() or not mask_p.is_file():
            continue
        labeled_tile_ids.append(tile_id)

    if not labeled_tile_ids:
        raise ValueError("no labeled tiles with image and mask on disk to export")

    export_id = str(uuid.uuid4())
    out = export_dir_for(repo_root, tenant_id, dataset_id, export_id)
    if out.exists():
        shutil.rmtree(out)
    (out / "images").mkdir(parents=True)
    (out / "masks").mkdir(parents=True)

    measured_x = float(cfg.geo.expected_gsd_cm)
    measured_y = float(cfg.geo.expected_gsd_cm)
    gsd_src = "expected"

    # 원본 목록 및 SHA-256 → ID는 (digest, 이름) 순으로 정렬되어 export 마다 같은 파일 세트면 동일 순서 가능
    all_source_names: list[str] = []
    name_to_digest: dict[str, str | None] = {}

    for tile_id in labeled_tile_ids:
        meta = _load_tile_meta(ddir / "metadata" / f"{tile_id}.json")
        src = meta.get("source_image") or ""
        if isinstance(src, str) and src.strip() and src not in all_source_names:
            all_source_names.append(src)

    all_source_names.sort(key=lambda nm: nm.lower())
    for nm in all_source_names:
        tpath = dataset_service.raw_geotiff_path(repo_root, tenant_id, nm)
        name_to_digest[nm] = _sha256_file(tpath)

    sorted_for_ids = sorted(
        all_source_names,
        key=lambda nm: (
            name_to_digest.get(nm) or "",
            nm.lower(),
        ),
    )
    source_id_map: dict[str, str] = {
        nm: f"source_{i:04d}" for i, nm in enumerate(sorted_for_ids)
    }

    catalog: dict[str, dict[str, str | None]] = {}
    for nm in sorted_for_ids:
        sid = source_id_map[nm]
        catalog[sid] = {
            "source_image_name": nm,
            "source_image_hash": name_to_digest.get(nm),
        }

    tile_metas_list: list[dict] = []
    for tile_id in labeled_tile_ids:
        shutil.copy2(ddir / "images" / f"{tile_id}.png", out / "images" / f"{tile_id}.png")

        raw_mask = np.array(Image.open(ddir / "masks" / f"{tile_id}.png"))
        binary_mask = (raw_mask > 0).astype(np.uint8) * 255
        Image.fromarray(binary_mask, mode="L").save(out / "masks" / f"{tile_id}.png")

        meta = _load_tile_meta(ddir / "metadata" / f"{tile_id}.json")
        src_name = meta.get("source_image")
        if isinstance(src_name, str) and not src_name.strip():
            src_name = None

        fg_ratio = _foreground_ratio(raw_mask)
        sid = None
        if src_name:
            sid = source_id_map.get(src_name)

        digest: str | None = None
        if src_name:
            digest = name_to_digest.get(src_name)

        tile_metas_list.append(
            {
                "tile_id": tile_id,
                "image_path": f"images/{tile_id}.png",
                "mask_path": f"masks/{tile_id}.png",
                "source_image_id": sid,
                "source_image_name": src_name,
                "source_image_hash": digest,
                "x": meta.get("x"),
                "y": meta.get("y"),
                "width": meta.get("tile_size"),
                "height": meta.get("tile_size"),
                "overlap": meta.get("overlap"),
                "has_foreground": fg_ratio > 0,
                "foreground_ratio": round(fg_ratio, 6),
                "measured_gsd_x_cm": meta.get("measured_gsd_x_cm"),
                "measured_gsd_y_cm": meta.get("measured_gsd_y_cm"),
                "gsd_source": meta.get("gsd_source"),
            }
        )

        if gsd_src == "expected" and meta.get("measured_gsd_x_cm"):
            measured_x = float(meta["measured_gsd_x_cm"])
            measured_y = float(meta.get("measured_gsd_y_cm", measured_x))
            gsd_src = meta.get("gsd_source", "metadata")

    (out / "tiles_manifest.json").write_text(
        json.dumps(tile_metas_list, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    if catalog:
        (out / "sources_catalog.json").write_text(
            json.dumps(catalog, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    mask_schema = {
        "task_type": "binary_segmentation",
        "mask_encoding": "binary_0_255",
        "background_value": 0,
        "foreground_value": 255,
        "ignore_value": None,
        "note": (
            "Exported masks remap class-index masks: 0 → background (0); "
            ">0 → foreground (255). "
            "source_image_id is assigned per-export from SHA-256+name sorting; "
            "use sources_catalog.json/source_image_hash for stable cross-export identity."
        ),
    }
    (out / "mask_schema.json").write_text(
        json.dumps(mask_schema, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    export_classes = {
        "schema_version": cfg.classes.schema_version,
        "definitions": [
            {
                "id": d.id,
                "name": d.name,
                "mask_value": 0 if d.id == 0 else 255,
            }
            for d in cfg.classes.definitions
            if d.id != 255
        ],
        "ignore_value": None,
    }
    (out / "classes.json").write_text(
        json.dumps(export_classes, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    (out / "config_snapshot.yaml").write_text(
        yaml.safe_dump(cfg.model_dump(mode="json"), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    fg_by_tile = {m["tile_id"]: float(m["foreground_ratio"]) for m in tile_metas_list}

    fg_ratios = [m["foreground_ratio"] for m in tile_metas_list]
    fg_mean = round(float(np.mean(fg_ratios)), 6) if fg_ratios else 0.0
    fg_std = round(float(np.std(fg_ratios)), 6) if len(fg_ratios) > 1 else 0.0
    fg_min = round(float(np.min(fg_ratios)), 6) if fg_ratios else 0.0
    fg_max = round(float(np.max(fg_ratios)), 6) if fg_ratios else 0.0

    distinct_named_sources = len(all_source_names)
    has_source_info = any(isinstance(m.get("source_image_name"), str) and m["source_image_name"] for m in tile_metas_list)
    requested = "group_by_source_image" if has_source_info else "random"

    splits: dict
    split_warning: str | None = None
    split_valid_group_leak_prevention = False

    if requested == "group_by_source_image" and distinct_named_sources >= DEFAULT_MIN_SOURCES_FOR_GROUP_SPLIT:
        splits = assign_splits_by_source(tile_metas_list, cfg.dataset.split_ratio, seed=split_seed)
        write_split_files(out, splits, strategy="group_by_source_image")
        split_valid_group_leak_prevention = True
        actual = "group_by_source_image"
    elif requested == "group_by_source_image":
        splits = assign_splits(labeled_tile_ids, cfg.dataset.split_ratio, seed=split_seed)
        write_split_files(
            out,
            {"train": splits["train"], "val": splits["val"], "test": splits["test"]},
            strategy="random",
        )
        actual = "random"
        split_warning = (
            f"requested group_by_source_image but distinct source_image_name count "
            f"({distinct_named_sources}) < {DEFAULT_MIN_SOURCES_FOR_GROUP_SPLIT}: "
            f"fallback to tile-level random split (cannot isolate train/val/test by raster without enough sources)."
        )
    else:
        splits = assign_splits(labeled_tile_ids, cfg.dataset.split_ratio, seed=split_seed)
        write_split_files(
            out,
            {"train": splits["train"], "val": splits["val"], "test": splits["test"]},
            strategy="random",
        )
        actual = "random"

    def _mean_fg(ids: list[str]) -> float | None:
        vals = [fg_by_tile[t] for t in ids if t in fg_by_tile]
        return round(float(np.mean(vals)), 6) if vals else None

    train_fg_mean = _mean_fg(list(splits.get("train", [])))
    val_fg_mean = _mean_fg(list(splits.get("val", [])))
    test_fg_mean = _mean_fg(list(splits.get("test", [])))

    same_source_may_span = actual == "random" and distinct_named_sources >= 1

    gw, gh = cfg.grid.to_pixels(measured_x, measured_y)

    manifest = {
        "dataset_id": dataset_id,
        "tenant_id": tenant_id,
        "export_id": export_id,
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "tile_size": cfg.tiling.tile_size,
        "tile_overlap": cfg.tiling.tile_overlap,
        "expected_gsd_cm": cfg.geo.expected_gsd_cm,
        "measured_gsd_x_cm": measured_x,
        "measured_gsd_y_cm": measured_y,
        "manual_gsd_cm": cfg.geo.manual_gsd_cm,
        "gsd_source": gsd_src,
        "georeferencing": "full",
        "grid_size_meters": cfg.grid.size_meters,
        "grid_size_pixels_x": gw,
        "grid_size_pixels_y": gh,
        "mask_schema_version": cfg.classes.schema_version,
        "mask_schema_path": "mask_schema.json",
        "tiles_manifest_path": "tiles_manifest.json",
        "sources_catalog_path": ("sources_catalog.json" if catalog else None),
        "requested_split_strategy": requested,
        "actual_split_strategy": actual,
        "split_valid_group_leak_prevention": split_valid_group_leak_prevention,
        "same_source_may_span_train_val_test": same_source_may_span,
        "split_warning": split_warning,
        "min_sources_required_for_group_split": DEFAULT_MIN_SOURCES_FOR_GROUP_SPLIT,
        "distinct_source_images_count": distinct_named_sources,
        "foreground_ratio_mean": fg_mean,
        "foreground_ratio_std": fg_std,
        "foreground_ratio_min": fg_min,
        "foreground_ratio_max": fg_max,
        "train_foreground_ratio_mean": train_fg_mean,
        "val_foreground_ratio_mean": val_fg_mean,
        "test_foreground_ratio_mean": test_fg_mean,
        "sample_count": len(labeled_tile_ids),
        "source_image_count": distinct_named_sources,
        "dataset_config_snapshot_id": dr.config_snapshot_id,
        "config_snapshot_path": "config_snapshot.yaml",
        "validation_report_path": "validation_report.json",
    }
    # 하위 호환
    manifest["split_strategy"] = manifest["actual_split_strategy"]

    (out / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    vr = build_validation_report(out)
    vr["exported_at_manifest"] = manifest["created_at"]
    (out / "validation_report.json").write_text(
        json.dumps(vr, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    verrors = validate_export(out)
    if verrors:
        shutil.rmtree(out)
        raise RuntimeError("export validation failed: " + "; ".join(verrors))

    now = datetime.now(UTC).isoformat()
    rel = out.relative_to(repo_root).as_posix()
    er = ExportRow(
        id=export_id,
        tenant_id=tenant_id,
        dataset_id=dataset_id,
        status="done",
        export_path=rel,
        sample_count=len(labeled_tile_ids),
        created_at=now,
        error_detail=None,
    )
    session.add(er)
    session.commit()

    return export_id


def get_export(session: Session, tenant_id: str, export_id: str) -> ExportRow | None:
    row = session.get(ExportRow, export_id)
    if row is None or row.tenant_id != tenant_id:
        return None
    return row
